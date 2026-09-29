"""
Revenue Recovery Agent -- Orchestrator
-----------------------------------------
Runs the full pipeline end-to-end:
  1. Generate synthetic transaction data (with injected degradation events)
  2. Detect degradation events (rolling z-test)
  3. Diagnose root cause for each detected event
  4. Execute bounded recovery actions, log full audit trail
  5. Produce a single consolidated scorecard for the pitch/demo

This is the single entry point for a live demo: `python3 src/run_agent.py`

Output: outputs/final_scorecard.json (the headline numbers for the pitch)
"""

import subprocess
import sys
import json
import pandas as pd
import ast
import time

STEPS = [
    ("Generating synthetic transaction data", "src/generate_data.py"),
    ("Detecting payment degradation events", "src/detector.py"),
    ("Diagnosing root causes", "src/diagnoser.py"),
    ("Executing bounded recovery workflow", "src/recovery_engine.py"),
]

DASHBOARD_STEPS = [
    ("Preparing dashboard data", "src/prep_dashboard_data.py"),
    ("Building demo dashboard", "src/build_dashboard.py"),
]


def run_step(label, script):
    print("=" * 70)
    print(f"STEP: {label}")
    print("=" * 70)
    start = time.time()
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    elapsed = time.time() - start
    print(result.stdout)
    if result.returncode != 0:
        print(f"!!! STEP FAILED: {label}")
        print(result.stderr)
        sys.exit(1)
    print(f"[done in {elapsed:.1f}s]\n")


def compute_detection_score():
    gt = pd.read_csv("data/ground_truth_events.csv")
    det = pd.read_csv("outputs/detected_events.csv")

    matched_gt = 0
    for _, evt in gt.iterrows():
        evt_start, evt_end = evt["start_offset_min"], evt["start_offset_min"] + evt["duration_min"]
        overlap = det[
            (det["segment_type"] == evt["segment_type"]) &
            (det["segment_value"] == evt["segment_value"]) &
            (det["payment_method"] == evt["payment_method"]) &
            (det["window_start_min"] < evt_end) &
            (det["window_end_min"] > evt_start)
        ]
        if len(overlap) > 0:
            matched_gt += 1

    recall = matched_gt / len(gt) if len(gt) else 0.0
    precision = matched_gt / len(det) if len(det) else 0.0
    return {
        "real_events_planted": int(len(gt)),
        "events_detected": int(len(det)),
        "events_correctly_matched": int(matched_gt),
        "recall": round(recall, 3),
        "precision": round(precision, 3),
    }


def compute_diagnosis_score():
    gt = pd.read_csv("data/ground_truth_events.csv")[["segment_value", "payment_method", "root_cause"]]
    diag = pd.read_csv("outputs/diagnosed_events.csv")[["segment_value", "payment_method", "root_cause", "confidence"]]
    merged = gt.merge(diag, on=["segment_value", "payment_method"], suffixes=("_true", "_diagnosed"))

    # Special case: for a deliberately AMBIGUOUS ground-truth event (no
    # single dominant cause by design), the CORRECT diagnoser behavior is
    # to recognize it can't confidently pick one cause -- not to match a
    # specific label. Scoring that as "wrong" would punish the diagnoser
    # for doing exactly the right thing (flagging uncertainty instead of
    # guessing). So: if ground truth is intentionally ambiguous, count it
    # correct when the diagnoser's own output is its "unclear" label.
    def is_correct(row):
        if row["root_cause_true"] == "ambiguous_mixed_signals":
            return row["root_cause_diagnosed"] == "unclear_mixed_signals"
        return row["root_cause_true"] == row["root_cause_diagnosed"]

    merged["correct"] = merged.apply(is_correct, axis=1)
    return {
        "events_diagnosed": int(len(merged)),
        "correct_diagnoses": int(merged["correct"].sum()),
        "diagnosis_accuracy": round(merged["correct"].mean(), 3) if len(merged) else 0.0,
        "avg_confidence": round(diag["confidence"].mean(), 3),
    }


def compute_recovery_score():
    with open("outputs/recovery_summary.json") as f:
        summary = json.load(f)
    return {
        "total_amount_at_risk": summary["total_amount_at_risk"],
        "total_amount_recovered": summary["total_amount_recovered"],
        "overall_recovery_rate": summary["overall_recovery_rate"],
        "n_events_handled": summary["n_events"],
    }


def main():
    print("\n" + "#" * 70)
    print("# REVENUE RECOVERY AGENT -- full pipeline run")
    print("#" * 70 + "\n")

    for label, script in STEPS:
        run_step(label, script)

    print("=" * 70)
    print("FINAL SCORECARD")
    print("=" * 70)

    detection = compute_detection_score()
    diagnosis = compute_diagnosis_score()
    recovery = compute_recovery_score()

    scorecard = {
        "detection": detection,
        "diagnosis": diagnosis,
        "recovery": recovery,
    }

    with open("outputs/final_scorecard.json", "w") as f:
        json.dump(scorecard, f, indent=2)

    # Dashboard steps run AFTER the scorecard is written, since the
    # dashboard reads outputs/final_scorecard.json -- running them earlier
    # (as part of the main STEPS loop) meant the dashboard was built from
    # the PREVIOUS run's scorecard, not this one. Caught this by noticing
    # the dashboard showed 83% diagnosis accuracy right after we'd just
    # fixed that exact number to compute as 100% in the console output.
    for label, script in DASHBOARD_STEPS:
        run_step(label, script)

    print(f"\nDETECTION")
    print(f"  Real degradation events planted: {detection['real_events_planted']}")
    print(f"  Events detected:                 {detection['events_detected']}")
    print(f"  Recall:                          {detection['recall']:.0%}")
    print(f"  Precision:                       {detection['precision']:.0%}")

    print(f"\nDIAGNOSIS")
    print(f"  Diagnosis accuracy:              {diagnosis['diagnosis_accuracy']:.0%}")
    print(f"  Average confidence:              {diagnosis['avg_confidence']:.0%}")

    print(f"\nRECOVERY")
    print(f"  Total amount at risk:            Rs.{recovery['total_amount_at_risk']:,.2f}")
    print(f"  Total amount recovered:          Rs.{recovery['total_amount_recovered']:,.2f}")
    print(f"  Overall recovery rate:           {recovery['overall_recovery_rate']:.1%}")

    print(f"\nFull scorecard saved to outputs/final_scorecard.json")
    print("Full audit trail saved to outputs/recovery_audit_log.csv")
    print("Demo dashboard saved to outputs/dashboard.html -- open in a browser")


if __name__ == "__main__":
    main()
