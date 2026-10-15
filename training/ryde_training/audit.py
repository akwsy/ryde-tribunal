"""Offline role-quality audit sample and confidence analysis for saved synthetic runs."""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

from .generate import outside_repository

SOURCE_POLICY = "ryde-policy-1.0.0"
BANDS = ((0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0000001))


def _calibration(rows):
    if not rows:
        return {"count": 0, "brier_score": None, "expected_calibration_error": None, "bands": []}
    bins = []
    for low, high in BANDS:
        selected = [row for row in rows if low <= row["confidence"] < high]
        if not selected:
            continue
        mean_confidence = sum(row["confidence"] for row in selected) / len(selected)
        accuracy = sum(row["correct"] for row in selected) / len(selected)
        bins.append({"range": f"{low:.1f}–{min(high, 1.0):.1f}", "count": len(selected),
                     "mean_confidence": round(mean_confidence, 4), "accuracy": round(accuracy, 4)})
    ece = sum(item["count"] / len(rows) * abs(item["mean_confidence"] - item["accuracy"])
              for item in bins)
    brier = sum((row["confidence"] - float(row["correct"])) ** 2 for row in rows) / len(rows)
    return {"count": len(rows), "brier_score": round(brier, 6),
            "expected_calibration_error": round(ece, 6), "bands": bins}


def analyze(report_path, output):
    destination = outside_repository(output)
    destination.mkdir(parents=True, exist_ok=False)
    source = Path(report_path).resolve()
    benchmark = json.loads(source.read_text())
    rows = benchmark.get("rows") or []
    if len(rows) != 120:
        raise ValueError(f"Expected the frozen 120-case report; found {len(rows)}")
    def bucket(row):
        key = row.get("key", "")
        if key.startswith("route-"):
            return "route"
        if key.startswith("no-show-"):
            return "no_show"
        if key.startswith("review-"):
            return "uncertainty_adversarial"
        raise ValueError(f"Unexpected benchmark case key: {key}")

    bucket_counts = Counter(bucket(row) for row in rows)
    if bucket_counts != Counter({"route": 50, "no_show": 50, "uncertainty_adversarial": 20}):
        raise ValueError(f"Unexpected benchmark stratification: {dict(bucket_counts)}")

    evaluated = []
    case_outputs = {}
    for row in rows:
        key = row["key"]
        case_path = source.parent / f"{key}.json"
        body = json.loads(case_path.read_text())
        if body.get("policy_version") != SOURCE_POLICY:
            raise ValueError(f"Expected diagnostic policy {SOURCE_POLICY}; found {body.get('policy_version')} for {key}")
        judge = body.get("judge") or {}
        confidence = judge.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError(f"Missing or invalid Judge confidence for {key}")
        expected = row["expected_outcome"]
        amount = ((judge.get("recommended_action") or {}).get("amount") or {}).get("amount_cents")
        output_correct = body.get("status") == expected["status"]
        if expected["ruling_type"] is not None:
            output_correct = output_correct and judge.get("ruling_type") == expected["ruling_type"]
        if expected["amount_cents"] is not None:
            actual_amount = 0 if amount is None and judge.get("ruling_type") == "no_action" else amount
            output_correct = output_correct and actual_amount == expected["amount_cents"]
        if output_correct != bool(row.get("correct")):
            raise ValueError(f"Saved response/report disagreement for {key}")
        evaluated.append({"key": key, "category": row["expected"]["category"], "bucket": bucket(row),
                          "confidence": float(confidence), "correct": output_correct,
                          "status": body.get("status"), "gemini_called": bool(row.get("gemini_called")),
                          "fallback": bool(row.get("fallback"))})
        case_outputs[key] = (row, body)

    resolved = [row for row in evaluated if row["status"] == "resolved"]
    by_category = {}
    for category in sorted(bucket_counts):
        group = [row for row in evaluated if row["bucket"] == category]
        by_category[category] = {"cases": len(group), "accuracy": round(sum(r["correct"] for r in group) / len(group), 4),
                                 "calibration": _calibration(group)}
    by_dispute_category = {}
    for category in sorted({row["category"] for row in evaluated}):
        group = [row for row in evaluated if row["category"] == category]
        by_dispute_category[category] = {"cases": len(group), "accuracy": round(sum(r["correct"] for r in group) / len(group), 4),
                                         "calibration": _calibration(group)}
    calibration = {
        "source_report": str(source),
        "source_policy_version": SOURCE_POLICY,
        "purpose": "diagnostic only; saved responses are not training labels and use an earlier policy snapshot",
        "label_definition": "Benchmark expected outcomes; status is checked for every row, while ruling and amount are checked only when the benchmark specifies them. A correct escalation is counted as the expected outcome.",
        "limits": ["Single synthetic stratified benchmark", "Historical policy 1.0.0 outputs", "Not a production accuracy or current-policy calibration claim"],
        "case_count": len(evaluated),
        "exact_outcome_accuracy": round(sum(row["correct"] for row in evaluated) / len(evaluated), 4),
        "gemini_cases": sum(row["gemini_called"] for row in evaluated),
        "fallback_cases": sum(row["fallback"] for row in evaluated),
        "current_escalation_threshold": 0.70,
        "all_case_confidence": _calibration(evaluated),
        "automatically_resolved_confidence": _calibration(resolved),
        "by_scenario_group": by_category,
        "by_dispute_category": by_dispute_category,
    }
    (destination / "confidence-calibration.json").write_text(json.dumps(calibration, indent=2) + "\n")

    role_rows = []
    for category in ("route", "no_show", "uncertainty_adversarial"):
        group = [row for row in evaluated if row["bucket"] == category]
        group.sort(key=lambda row: (row["confidence"], row["key"]))
        count = 10
        for index in range(count):
            selected_index = min(len(group) - 1, math.floor((index + 0.5) * len(group) / count))
            row = group[selected_index]
            report_row, body = case_outputs[row["key"]]
            for role, result_key in (("rider_advocate", "rider"), ("driver_advocate", "driver"), ("judge", "judge")):
                if role == "judge":
                    output_data = {"judge": body.get("judge"),
                                   "model_proposed_ruling": body.get("model_proposed_ruling")}
                else:
                    output_data = (body.get("advocates") or {}).get(result_key)
                role_rows.append({
                    "sample_key": row["key"], "scenario_family": report_row.get("scenario_family"),
                    "scenario_group": category, "category": row["category"],
                    "source_policy_version": SOURCE_POLICY,
                    "role": role, "confidence": row["confidence"] if role == "judge" else None,
                    "agent_output": output_data,
                    "ratings": {"evidence_use": None, "citation_accuracy": None,
                                "policy_use": None, "fairness": None, "unsupported_claims": None},
                    "reviewer": None, "rationale": None,
                })
    if len(role_rows) != 90 or len({(row["sample_key"], row["role"]) for row in role_rows}) != 90:
        raise ValueError("Role-quality audit sample must contain 30 distinct cases x three roles")
    (destination / "live-output-audit.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in role_rows))
    manifest = {"synthetic_only": True, "case_audit_count": 30, "role_review_rows": 90,
                "review_queue_count": 60, "core_roles": ["rider_advocate", "driver_advocate", "judge"],
                "policy_version_for_new_training_queue": "ryde-policy-1.1.0",
                "calibration_source_policy_version": SOURCE_POLICY,
                "benchmark_labels_in_review_workbook": False,
                "provider_calls_made": 0}
    (destination / "review-packet-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"output": str(destination), "case_audit_count": 30, "role_review_rows": len(role_rows),
            "calibration": calibration}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.report, args.output), indent=2))
