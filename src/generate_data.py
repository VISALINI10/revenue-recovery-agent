"""
Synthetic Payment Transaction Generator
----------------------------------------
Generates a realistic stream of payment transactions across multiple
segments (payment_method x bank/issuer x gateway), with a NORMAL baseline
failure rate, and deliberately injects a handful of "degradation events"
(sudden spikes in failure rate for a specific segment over a time window).

This gives us ground truth to later measure our detector's precision/recall.

Output: data/transactions.csv, data/ground_truth_events.csv
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json

np.random.seed(42)

# ---------------------------------------------------------------------------
# Config: the "world" we're simulating
# ---------------------------------------------------------------------------

SIM_START = datetime(2026, 8, 25, 0, 0, 0)
SIM_HOURS = 24
TX_PER_MINUTE_BASE = 30  # avg transactions per minute across all segments
# (raised from 8 -- with 30 bank-segments x 6-8 method/bank/gateway combos,
# 8/min left each segment with only ~2-3 tx per 10-min window, too sparse
# for a statistically meaningful failure-rate comparison. 30/min gives each
# segment enough volume for the detector to actually work.)

PAYMENT_METHODS = ["upi", "credit_card", "debit_card", "netbanking", "wallet"]
BANKS = ["HDFC", "ICICI", "SBI", "AXIS", "KOTAK", "YES_BANK"]
GATEWAYS = ["gw_primary", "gw_secondary", "gw_backup"]

# Baseline failure rate per payment method (real-world-ish figures)
BASE_FAIL_RATE = {
    "upi": 0.04,
    "credit_card": 0.06,
    "debit_card": 0.05,
    "netbanking": 0.07,
    "wallet": 0.03,
}

# Error codes mapped loosely to root-cause "flavors" we'll use later
# (the diagnoser in Day 2 will re-derive cause from these + latency,
# it does NOT get to see this mapping directly)
ERROR_CODES_NORMAL = ["INSUFFICIENT_FUNDS", "USER_CANCELLED", "INVALID_OTP"]
ERROR_CODES_GATEWAY_TIMEOUT = ["GATEWAY_TIMEOUT", "CONN_RESET"]
ERROR_CODES_ISSUER_DECLINE = ["ISSUER_DECLINED", "RISK_BLOCK", "DO_NOT_HONOR"]
ERROR_CODES_BANK_DOWNTIME = ["BANK_SERVER_ERROR", "BANK_UNREACHABLE"]
ERROR_CODES_NETWORK = ["NETWORK_ERROR", "DNS_FAIL"]

AMOUNT_RANGE = (150, 45000)  # INR

# ---------------------------------------------------------------------------
# Degradation events we will INJECT (this is our ground truth)
# Each event: a specific segment (method+bank or method+gateway) gets an
# elevated failure rate for a window of time, with a specific error pattern
# that corresponds to a root cause.
# ---------------------------------------------------------------------------

DEGRADATION_EVENTS = [
    {
        "event_id": "EVT001",
        "start_offset_min": 180,   # 3 hours in
        "duration_min": 25,
        "segment_type": "bank",
        "segment_value": "HDFC",
        "payment_method": "upi",
        "root_cause": "bank_downtime",
        "elevated_fail_rate": 0.55,
        "error_codes": ERROR_CODES_BANK_DOWNTIME,
    },
    {
        "event_id": "EVT002",
        "start_offset_min": 420,   # 7 hours in
        "duration_min": 15,
        "segment_type": "gateway",
        "segment_value": "gw_primary",
        "payment_method": "credit_card",
        "root_cause": "gateway_timeout",
        "elevated_fail_rate": 0.65,
        "error_codes": ERROR_CODES_GATEWAY_TIMEOUT,
    },
    {
        "event_id": "EVT003",
        "start_offset_min": 600,   # 10 hours in
        "duration_min": 40,
        "segment_type": "bank",
        "segment_value": "AXIS",
        "payment_method": "debit_card",
        "root_cause": "issuer_decline_spike",
        "elevated_fail_rate": 0.45,
        "error_codes": ERROR_CODES_ISSUER_DECLINE,
    },
    {
        "event_id": "EVT004",
        "start_offset_min": 800,   # ~13.3 hours in
        "duration_min": 20,
        "segment_type": "gateway",
        "segment_value": "gw_secondary",
        "payment_method": "netbanking",
        "root_cause": "network_issue",
        "elevated_fail_rate": 0.50,
        "error_codes": ERROR_CODES_NETWORK,
    },
    {
        "event_id": "EVT005",
        "start_offset_min": 1000,  # ~16.7 hours in
        "duration_min": 30,
        "segment_type": "bank",
        "segment_value": "SBI",
        "payment_method": "upi",
        "root_cause": "bank_downtime",
        "elevated_fail_rate": 0.60,
        "error_codes": ERROR_CODES_BANK_DOWNTIME,
    },
    {
        # Deliberately AMBIGUOUS event: the failures here are a genuine
        # mix of error codes from three different root-cause families, so
        # no single cause should dominate the diagnoser's vote. This is
        # meant to trigger the confidence gate in the recovery engine and
        # route to human escalation rather than an automated action --
        # demonstrating the "don't act automatically when unsure" safety
        # rail, not just describing it.
        "event_id": "EVT006",
        "start_offset_min": 1200,  # ~20 hours in
        "duration_min": 35,
        "segment_type": "bank",
        "segment_value": "ICICI",
        "payment_method": "wallet",
        "root_cause": "unclear_mixed_signals",
        "elevated_fail_rate": 0.55,
        "error_codes": ERROR_CODES_ISSUER_DECLINE + ERROR_CODES_NETWORK + ERROR_CODES_BANK_DOWNTIME,
    },
]


def in_active_event(minute_offset, method, bank, gateway):
    """Return the active degradation event dict if this transaction's
    segment + time falls inside an injected event window, else None."""
    for evt in DEGRADATION_EVENTS:
        if not (evt["start_offset_min"] <= minute_offset < evt["start_offset_min"] + evt["duration_min"]):
            continue
        if evt["payment_method"] != method:
            continue
        if evt["segment_type"] == "bank" and evt["segment_value"] == bank:
            return evt
        if evt["segment_type"] == "gateway" and evt["segment_value"] == gateway:
            return evt
    return None


def generate_transactions():
    rows = []
    total_minutes = SIM_HOURS * 60

    for minute in range(total_minutes):
        n_tx = np.random.poisson(TX_PER_MINUTE_BASE)
        for _ in range(n_tx):
            method = np.random.choice(PAYMENT_METHODS)
            bank = np.random.choice(BANKS)
            gateway = np.random.choice(GATEWAYS)
            amount = round(np.random.uniform(*AMOUNT_RANGE), 2)

            evt = in_active_event(minute, method, bank, gateway)
            base_rate = BASE_FAIL_RATE[method]
            fail_rate = evt["elevated_fail_rate"] if evt else base_rate

            is_failure = np.random.random() < fail_rate

            if is_failure:
                if evt:
                    error_code = np.random.choice(evt["error_codes"])
                    latency_ms = int(np.random.normal(3500, 800)) if ("TIMEOUT" in error_code or "UNREACHABLE" in error_code or "BANK_SERVER_ERROR" in error_code) else int(np.random.normal(1200, 300))
                else:
                    error_code = np.random.choice(ERROR_CODES_NORMAL)
                    latency_ms = int(np.random.normal(800, 200))
                outcome = "failed"
            else:
                error_code = None
                latency_ms = int(np.random.normal(700, 150))
                outcome = "success"

            latency_ms = max(latency_ms, 50)
            ts = SIM_START + timedelta(minutes=minute, seconds=int(np.random.uniform(0, 60)))

            rows.append({
                "timestamp": ts.isoformat(),
                "minute_offset": minute,
                "payment_method": method,
                "bank": bank,
                "gateway": gateway,
                "amount": amount,
                "error_code": error_code,
                "latency_ms": latency_ms,
                "outcome": outcome,
                "injected_event_id": evt["event_id"] if evt else None,  # ground truth, NOT for detector to see
            })

    df = pd.DataFrame(rows)
    return df


def main():
    print("Generating synthetic transaction stream...")
    df = generate_transactions()
    df.to_csv("data/transactions.csv", index=False)
    print(f"Wrote {len(df)} transactions to data/transactions.csv")

    # Ground truth file — used ONLY for scoring your detector later,
    # never fed into the detection/diagnosis logic itself.
    gt = pd.DataFrame(DEGRADATION_EVENTS)
    gt.to_csv("data/ground_truth_events.csv", index=False)
    print(f"Wrote {len(gt)} ground-truth degradation events to data/ground_truth_events.csv")

    # Quick sanity summary
    total_amount = df["amount"].sum()
    failed_amount = df[df["outcome"] == "failed"]["amount"].sum()
    print(f"\nTotal transaction volume: Rs.{total_amount:,.2f}")
    print(f"Total failed volume:      Rs.{failed_amount:,.2f}")
    print(f"Overall failure rate:     {(df['outcome']=='failed').mean():.2%}")
    print(f"Injected events:          {len(DEGRADATION_EVENTS)}")


if __name__ == "__main__":
    main()
