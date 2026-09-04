"""
Dashboard Data Prep
----------------------
Reads the pipeline outputs and shapes them into the JSON the dashboard
HTML needs: hourly failure-rate timeline (for the visual strip) and a
clean event ledger (segment, root cause, action, amounts, recovery rate).

Output: outputs/dashboard_data.json
"""

import pandas as pd
import json

def build_timeline(transactions):
    """Overall failure rate per 30-minute bucket across the whole day,
    for the visual timeline strip."""
    df = transactions.copy()
    df["bucket"] = (df["minute_offset"] // 30) * 30
    grouped = df.groupby("bucket")["outcome"].apply(lambda s: (s == "failed").mean())
    return [{"minute": int(b), "fail_rate": round(r, 4)} for b, r in grouped.items()]


def build_ledger(scorecard, recovery_summary):
    ledger = []
    for e in recovery_summary["events"]:
        ledger.append({
            "payment_method": e["payment_method"],
            "segment_value": e["segment_value"],
            "root_cause": e["root_cause"],
            "action": e["action"],
            "n_transactions": e["n_transactions"],
            "n_recovered": e["n_recovered"],
            "amount_at_risk": e["amount_at_risk"],
            "amount_recovered": e["amount_recovered"],
            "recovery_rate": e["recovery_rate"],
        })
    return ledger


def main():
    transactions = pd.read_csv("data/transactions.csv")
    detected = pd.read_csv("outputs/detected_events.csv")

    with open("outputs/final_scorecard.json") as f:
        scorecard = json.load(f)
    with open("outputs/recovery_summary.json") as f:
        recovery_summary = json.load(f)

    dashboard_data = {
        "scorecard": scorecard,
        "timeline": build_timeline(transactions),
        "events": [
            {
                "payment_method": row["payment_method"],
                "segment_value": row["segment_value"],
                "segment_type": row["segment_type"],
                "window_start_min": int(row["window_start_min"]),
                "window_end_min": int(row["window_end_min"]),
            }
            for _, row in detected.iterrows()
        ],
        "ledger": build_ledger(scorecard, recovery_summary),
    }

    with open("outputs/dashboard_data.json", "w") as f:
        json.dump(dashboard_data, f, indent=2)

    print("Wrote outputs/dashboard_data.json")
    print(f"Timeline buckets: {len(dashboard_data['timeline'])}")
    print(f"Events: {len(dashboard_data['events'])}")
    print(f"Ledger rows: {len(dashboard_data['ledger'])}")


if __name__ == "__main__":
    main()
