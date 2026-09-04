"""
Recovery Policy Engine
------------------------
For each diagnosed degradation event, decide a BOUNDED recovery action
based on root cause, execute it (simulated) against the affected failed
transactions, respecting stopping rules (max retries, cooldown, confidence
gate), and log a full audit trail of what was tried and what happened.

Input:  outputs/detected_events.csv, outputs/diagnosed_events.csv,
        data/transactions.csv
Output: outputs/recovery_audit_log.csv, outputs/recovery_summary.json
"""

import pandas as pd
import numpy as np
import ast
import json

np.random.seed(7)  # separate seed from data generation, for the recovery simulation

# ---------------------------------------------------------------------------
# Policy table: root_cause -> action
# ---------------------------------------------------------------------------
ROOT_CAUSE_POLICY = {
    "gateway_timeout": "reroute_alternate_gateway",
    "network_issue": "reroute_alternate_gateway",
    "bank_downtime": "delayed_retry_same_route",
    "issuer_decline_spike": "suggest_alternate_method",
    "unclear_mixed_signals": "escalate_to_ops",
    "unknown": "escalate_to_ops",
    "user_related": "escalate_to_ops",  # not a real infra issue -- don't auto-act
}

# Stopping rules -- these are the hard bounds on automated action
CONFIDENCE_MIN_FOR_AUTO_ACTION = 0.5   # below this, force escalation regardless of policy table
RETRY_COOLDOWN_MIN = 3                 # minutes between retry attempts

# Max attempts PER ACTION TYPE -- not uniform. A technical reroute/retry
# genuinely can be attempted a few times (different gateway instances,
# or waiting for a bank to recover). But "suggest alternate method" is a
# single customer-facing nudge -- repeating the same nudge 3x in a row
# doesn't reflect how that action actually works, and was artificially
# inflating its measured recovery rate in our first run.
ACTION_MAX_ATTEMPTS = {
    "reroute_alternate_gateway": 3,
    "delayed_retry_same_route": 3,
    "suggest_alternate_method": 1,
    "escalate_to_ops": 0,
}

# Simulated success probabilities per action, per attempt.
# These represent: "if we take this action, what's the chance THIS
# attempt succeeds?" -- calibrated so that actions matched to the real
# cause of failure work well, and mismatched/blind actions don't.
ACTION_SUCCESS_PROB = {
    "reroute_alternate_gateway": 0.82,   # different gateway, unaffected by the original issue
    "delayed_retry_same_route": None,    # depends on whether the bank has recovered by retry time (computed dynamically)
    "suggest_alternate_method": 0.35,    # depends on customer actually switching methods, not guaranteed
    "escalate_to_ops": 0.0,              # no automated recovery -- human handles it, outside this system's scope
}


def load_data():
    transactions = pd.read_csv("data/transactions.csv")
    detected = pd.read_csv("outputs/detected_events.csv")
    detected["affected_tx_ids"] = detected["affected_tx_ids"].apply(ast.literal_eval)
    diagnosed = pd.read_csv("outputs/diagnosed_events.csv")
    return transactions, detected, diagnosed


def simulate_delayed_retry_success(attempt_minute, event_window_end):
    """For bank_downtime, success depends on whether the bank has actually
    recovered by the time we retry. If we retry AFTER the event's window
    has ended, the underlying issue has likely cleared -- high success.
    If we retry WHILE still inside the degradation window, it's still
    down -- low success. This reflects reality: retrying too early just
    wastes an attempt."""
    if attempt_minute >= event_window_end:
        return 0.78
    else:
        return 0.10


def execute_recovery_for_event(event, diagnosis, transactions):
    """Run the bounded recovery workflow for one degradation event's
    affected failed transactions. Returns per-transaction audit rows."""
    root_cause = diagnosis["root_cause"]
    confidence = diagnosis["confidence"]

    # --- Stopping rule #1: confidence gate ---
    if confidence < CONFIDENCE_MIN_FOR_AUTO_ACTION:
        action = "escalate_to_ops"
        escalation_reason = f"Diagnosis confidence {confidence:.0%} below auto-action threshold ({CONFIDENCE_MIN_FOR_AUTO_ACTION:.0%})"
    else:
        action = ROOT_CAUSE_POLICY.get(root_cause, "escalate_to_ops")
        escalation_reason = None

    tx_ids = list(set(event["affected_tx_ids"]))
    failed_tx = transactions.loc[transactions.index.isin(tx_ids)]

    audit_rows = []

    for tx_id, tx in failed_tx.iterrows():
        row_base = {
            "tx_id": tx_id,
            "segment_value": event["segment_value"],
            "payment_method": event["payment_method"],
            "amount": tx["amount"],
            "root_cause": root_cause,
            "diagnosis_confidence": confidence,
            "action": action,
        }

        if action == "escalate_to_ops":
            audit_rows.append({
                **row_base,
                "attempt_number": 0,
                "attempt_outcome": "escalated",
                "recovered": False,
                "recovered_amount": 0.0,
                "reasoning": escalation_reason or "Root cause requires human judgment (e.g. genuine decline pattern) -- not auto-actioned.",
            })
            continue

        # --- Bounded retry loop (Stopping rule #2: max attempts, #3: cooldown) ---
        max_attempts = ACTION_MAX_ATTEMPTS[action]
        recovered = False
        for attempt in range(1, max_attempts + 1):
            attempt_minute = tx["minute_offset"] + attempt * RETRY_COOLDOWN_MIN

            if action == "delayed_retry_same_route":
                success_prob = simulate_delayed_retry_success(attempt_minute, event["window_end_min"])
            else:
                success_prob = ACTION_SUCCESS_PROB[action]

            success = np.random.random() < success_prob
            recovered = success

            audit_rows.append({
                **row_base,
                "attempt_number": attempt,
                "attempt_outcome": "recovered" if success else "failed",
                "recovered": success,
                "recovered_amount": float(tx["amount"]) if success else 0.0,
                "reasoning": (
                    f"Attempt {attempt}/{max_attempts} via '{action}' "
                    f"(success prob {success_prob:.0%} at this point in time) -> "
                    f"{'succeeded' if success else 'failed'}."
                ),
            })

            if success:
                break  # stop retrying once recovered -- no point burning further attempts

        if not recovered:
            # --- Stopping rule #4: after exhausting retries, escalate rather than loop forever ---
            audit_rows.append({
                **row_base,
                "attempt_number": max_attempts + 1,
                "attempt_outcome": "escalated_after_max_retries",
                "recovered": False,
                "recovered_amount": 0.0,
                "reasoning": f"Exhausted {max_attempts} attempt(s) via '{action}' without success -- escalated to ops queue rather than retrying indefinitely.",
            })

    return audit_rows


def main():
    transactions, detected, diagnosed = load_data()

    # Merge detected (has affected_tx_ids, amount_at_risk) with diagnosed (has root_cause, confidence)
    merged = detected.merge(
        diagnosed[["segment_value", "payment_method", "window_start_min", "root_cause", "confidence", "reasoning"]],
        on=["segment_value", "payment_method", "window_start_min"],
        how="left",
    )

    all_audit_rows = []
    event_summaries = []

    print(f"Executing bounded recovery workflow for {len(merged)} events...\n")

    for _, event in merged.iterrows():
        diagnosis = {"root_cause": event["root_cause"], "confidence": event["confidence"]}
        rows = execute_recovery_for_event(event, diagnosis, transactions)
        all_audit_rows.extend(rows)

        tx_level = pd.DataFrame(rows)
        final_outcomes = tx_level.sort_values("attempt_number").groupby("tx_id").tail(1)
        n_tx = final_outcomes["tx_id"].nunique()
        n_recovered = final_outcomes["recovered"].sum()
        amount_at_risk = final_outcomes["amount"].sum()
        amount_recovered = final_outcomes["recovered_amount"].sum()

        action_used = rows[0]["action"]
        print(f"[{event['payment_method']} / {event['segment_value']}] root_cause={event['root_cause']} -> action={action_used}")
        print(f"  Transactions affected: {n_tx} | Recovered: {n_recovered} ({n_recovered/n_tx:.0%}) | "
              f"Amount at risk: Rs.{amount_at_risk:,.2f} | Amount recovered: Rs.{amount_recovered:,.2f}\n")

        event_summaries.append({
            "segment_value": event["segment_value"],
            "payment_method": event["payment_method"],
            "root_cause": event["root_cause"],
            "action": action_used,
            "n_transactions": int(n_tx),
            "n_recovered": int(n_recovered),
            "amount_at_risk": float(amount_at_risk),
            "amount_recovered": float(amount_recovered),
            "recovery_rate": round(n_recovered / n_tx, 3) if n_tx else 0.0,
        })

    audit_df = pd.DataFrame(all_audit_rows)
    audit_df.to_csv("outputs/recovery_audit_log.csv", index=False)

    total_at_risk = sum(e["amount_at_risk"] for e in event_summaries)
    total_recovered = sum(e["amount_recovered"] for e in event_summaries)

    summary = {
        "n_events": len(event_summaries),
        "total_amount_at_risk": round(total_at_risk, 2),
        "total_amount_recovered": round(total_recovered, 2),
        "overall_recovery_rate": round(total_recovered / total_at_risk, 3) if total_at_risk else 0.0,
        "events": event_summaries,
    }
    with open("outputs/recovery_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("=" * 60)
    print(f"TOTAL amount at risk:      Rs.{total_at_risk:,.2f}")
    print(f"TOTAL amount recovered:    Rs.{total_recovered:,.2f}")
    print(f"Overall recovery rate:     {total_recovered/total_at_risk:.1%}")
    print(f"Full audit trail: outputs/recovery_audit_log.csv ({len(audit_df)} log entries)")


if __name__ == "__main__":
    main()
