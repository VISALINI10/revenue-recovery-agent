"""
Root-Cause Diagnoser
----------------------
For each degradation event flagged by the detector, look at the actual
failed transactions inside that event's window/segment, and classify
WHY they failed based on the pattern of error_codes and latency.

This is deliberately RULE-BASED (not a black-box ML classifier) so that
every diagnosis comes with a plain-English justification we can show in
the audit trail and defend in a pitch.

Input:  outputs/detected_events.csv, data/transactions.csv
Output: outputs/diagnosed_events.csv
"""

import pandas as pd
import ast
import json

# Error-code -> root-cause family lookup.
# NOTE: the diagnoser does NOT know the generator's injected root_cause
# label -- it only sees error_code and latency_ms, same as a real system
# would. This mapping is our domain knowledge of what each code usually
# means, not a lookup into the ground truth.
ERROR_CODE_MAP = {
    "GATEWAY_TIMEOUT": "gateway_timeout",
    "CONN_RESET": "gateway_timeout",
    "BANK_SERVER_ERROR": "bank_downtime",
    "BANK_UNREACHABLE": "bank_downtime",
    "ISSUER_DECLINED": "issuer_decline_spike",
    "RISK_BLOCK": "issuer_decline_spike",
    "DO_NOT_HONOR": "issuer_decline_spike",
    "NETWORK_ERROR": "network_issue",
    "DNS_FAIL": "network_issue",
    # "normal" everyday failure reasons -- if these dominate an event,
    # it's likely NOT a real infra degradation, more like a user-behavior
    # blip, which we surface as "unclear" rather than force-fitting it.
    "INSUFFICIENT_FUNDS": "user_related",
    "USER_CANCELLED": "user_related",
    "INVALID_OTP": "user_related",
}

HIGH_LATENCY_THRESHOLD_MS = 2500  # above this, "slow failure" -- supports timeout/downtime diagnosis
CONFIDENCE_DOMINANCE_THRESHOLD = 0.5  # winning cause must explain >=50% of failures to be confident


def load_detected_events():
    df = pd.read_csv("outputs/detected_events.csv")
    df["affected_tx_ids"] = df["affected_tx_ids"].apply(ast.literal_eval)
    return df


def diagnose_event(event_row, transactions_df):
    """Look at the failed transactions for one detected event and vote
    on the most likely root cause based on error_code patterns."""
    tx_ids = list(set(event_row["affected_tx_ids"]))  # de-dupe (window overlap can double-count)
    failed_tx = transactions_df.loc[transactions_df.index.isin(tx_ids)]

    if failed_tx.empty:
        return {
            "root_cause": "unknown",
            "confidence": 0.0,
            "reasoning": "No matching failed transactions found for this event.",
            "n_failures_analyzed": 0,
            "avg_latency_ms": None,
        }

    # Vote: count how many failures map to each root-cause family
    cause_votes = failed_tx["error_code"].map(ERROR_CODE_MAP).value_counts(dropna=True)
    total = cause_votes.sum()

    if total == 0:
        return {
            "root_cause": "unknown",
            "confidence": 0.0,
            "reasoning": "Failed transactions had no recognizable error codes.",
            "n_failures_analyzed": len(failed_tx),
            "avg_latency_ms": round(failed_tx["latency_ms"].mean(), 1),
        }

    top_cause = cause_votes.index[0]
    top_count = cause_votes.iloc[0]
    confidence = round(top_count / total, 2)
    avg_latency = round(failed_tx["latency_ms"].mean(), 1)

    # Latency is a secondary confirming signal, not a deciding one:
    # timeout/downtime causes should show elevated latency. If the top
    # cause is timeout/downtime but latency is actually LOW, that's a
    # mismatch worth flagging -- lower our confidence and say so.
    latency_consistent = True
    if top_cause in ("gateway_timeout", "bank_downtime") and avg_latency < HIGH_LATENCY_THRESHOLD_MS:
        latency_consistent = False
        confidence = round(confidence * 0.7, 2)  # penalize the mismatch

    if confidence < CONFIDENCE_DOMINANCE_THRESHOLD:
        final_cause = "unclear_mixed_signals"
    else:
        final_cause = top_cause

    reasoning = (
        f"{top_count}/{total} failures ({confidence:.0%}) matched error codes "
        f"associated with '{top_cause}'. Avg latency during event: {avg_latency}ms "
        f"({'consistent' if latency_consistent else 'INCONSISTENT'} with expected pattern for this cause)."
    )

    return {
        "root_cause": final_cause,
        "confidence": confidence,
        "reasoning": reasoning,
        "n_failures_analyzed": int(len(failed_tx)),
        "avg_latency_ms": avg_latency,
        "error_code_breakdown": cause_votes.to_dict(),
    }


def main():
    events = load_detected_events()
    transactions = pd.read_csv("data/transactions.csv")
    print(f"Diagnosing {len(events)} detected events...\n")

    results = []
    for _, event in events.iterrows():
        diagnosis = diagnose_event(event, transactions)
        result = {
            "segment_type": event["segment_type"],
            "payment_method": event["payment_method"],
            "segment_value": event["segment_value"],
            "window_start_min": event["window_start_min"],
            "window_end_min": event["window_end_min"],
            "amount_at_risk": event["amount_at_risk"],
            **diagnosis,
        }
        results.append(result)

        print(f"[{event['payment_method']} / {event['segment_value']}] "
              f"window {event['window_start_min']}-{event['window_end_min']}min")
        print(f"  -> Diagnosis: {diagnosis['root_cause']} (confidence {diagnosis['confidence']:.0%})")
        print(f"  -> {diagnosis['reasoning']}\n")

    out_df = pd.DataFrame(results)
    # error_code_breakdown is a dict -- store as JSON string for CSV safety
    out_df["error_code_breakdown"] = out_df["error_code_breakdown"].apply(
        lambda d: json.dumps(d) if isinstance(d, dict) else "{}"
    )
    out_df.to_csv("outputs/diagnosed_events.csv", index=False)
    print(f"Wrote diagnoses for {len(out_df)} events to outputs/diagnosed_events.csv")


if __name__ == "__main__":
    main()
