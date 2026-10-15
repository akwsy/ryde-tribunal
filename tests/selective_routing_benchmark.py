"""Independent synthetic benchmark for selective Gemini routing.

The authored case labels in this module are benchmark metadata only. The API reader
receives source records, never expected outcomes or routing labels. The stratified mix
is for routing verification and is not a production-prevalence estimate.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import time
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.container import build_container
from app.settings import Settings
from app.providers.factory import build_provider


VERSION = "selective-routing-v1"
MODEL_DEFAULT = "gemini-3.1-flash-lite"
_BASE_PATH = Path(__file__).with_name("submission_benchmark.py")
_BASE_SPEC = importlib.util.spec_from_file_location("submission_benchmark_harness", _BASE_PATH)
_BASE = importlib.util.module_from_spec(_BASE_SPEC)
assert _BASE_SPEC and _BASE_SPEC.loader
_BASE_SPEC.loader.exec_module(_BASE)


def cases() -> list[dict]:
    """Return 120 distinct routing scenarios with separate expected metadata."""
    items: list[dict] = []

    def add(key, group, category, route_expectation, *, status, ruling, cents, clear, **facts):
        items.append({
            "key": key, "scenario_family": f"{VERSION}-{group}-{key}",
            "routing_group": group, "category": category,
            "expected_route": route_expectation,
            "expected_outcome": {"status": status, "ruling_type": ruling, "amount_cents": cents},
            "clear_standard": clear, **facts,
        })

    # 30 ordinary cases; policy and verified records should decide without Gemini.
    for i in range(30):
        if i % 2 == 0:
            j = i // 2
            quote = 950 + j * 113
            add(f"clear-{i:02d}", "rules_clear", "route_deviation", "no_gemini",
                status="resolved", ruling="no_action", cents=0, clear=True,
                planned_km=3.2 + j * .37, actual_km=5.8 + j * .61,
                quoted_cents=quote, charged_cents=quote, route_verified=True)
        else:
            j = i // 2
            elapsed = (181, 240, 360, 600, 900)[j % 5]
            add(f"clear-{i:02d}", "rules_clear", "no_show_charge", "no_gemini",
                status="resolved", ruling="no_action", cents=0, clear=True,
                actor="rider", elapsed=elapsed, fee_cents=661,
                waiver_days=31 + j % 30, service_tier="RydeX")

    # 30 more no-call cases stress verified, case-specific facts and exact citations.
    for i in range(30):
        if i % 2 == 0:
            j = i // 2
            quote = 1000 + j * 97
            charge = quote - (25 + j * 3)
            add(f"evidence-{i:02d}", "verified_evidence", "route_deviation", "no_gemini",
                status="resolved", ruling="no_action", cents=0, clear=True,
                planned_km=4.1 + j * .29, actual_km=7.4 + j * .53,
                quoted_cents=quote, charged_cents=charge, route_verified=True,
                fare_verified=True)
        else:
            j = i // 2
            elapsed = 181 + (j * 41) % 690
            age = 31 + (j * 7) % 60
            add(f"evidence-{i:02d}", "verified_evidence", "no_show_charge", "no_gemini",
                status="resolved", ruling="no_action", cents=0, clear=True,
                actor="driver" if j % 2 else "rider", elapsed=elapsed,
                fee_cents=661, waiver_days=age, service_tier="RydeXL")

    # 30 source-complete but nonstandard-fee cases are deliberately model eligible:
    # policy specifies the standard fee, while the verified ledger has a different amount.
    for i in range(30):
        fee = 450 + (i * 13) % 205
        add(f"interpret-{i:02d}", "model_eligible", "no_show_charge", "gemini",
            status="escalated", ruling=None, cents=None, clear=False,
            actor="rider" if i % 2 == 0 else "driver",
            elapsed=181 + (i * 23) % 420, fee_cents=fee,
            waiver_days=i % 28, service_tier="RydeX")

    # 30 hard stops must go to human review without asking Gemini to invent facts/policy.
    for i in range(30):
        if i % 2 == 0:
            j = i // 2
            facts = {
                "planned_km": 4.0 + j * .43, "actual_km": 8.0 + j * .77,
                "quoted_cents": 1200 + j * 71, "charged_cents": 1200 + j * 71,
                "route_verified": True, "fare_verified": True,
            }
            if j % 3 == 0:
                facts["missing_route"] = True
            elif j % 3 == 1:
                facts["missing_quote"] = True
            else:
                facts["fare_verified"] = False
            add(f"hardstop-{i:02d}", "human_hard_stop", "route_deviation", "human",
                status="escalated", ruling=None, cents=None, clear=False, **facts)
        else:
            j = i // 2
            special = (
                {"missing_actor": True, "actor": None, "elapsed": 240},
                {"contradictory_actor": True, "actor": "rider", "elapsed": 240},
                {"schedule_boundary": True, "actor": "rider", "elapsed": 180},
                {"service_tier": "RydeTAXI", "actor": "rider", "elapsed": 240},
                {"missing_arrival_gps": True, "actor": "driver", "elapsed": 360},
            )[j % 5]
            facts = {"fee_cents": 661, "waiver_days": j % 25,
                     "service_tier": "RydeX", **special}
            add(f"hardstop-{i:02d}", "human_hard_stop", "no_show_charge", "human",
                status="escalated", ruling=None, cents=None, clear=False, **facts)
    return items


def select_cases(keys=None, limit=120):
    all_cases = cases()
    if keys:
        by_key = {item["key"]: item for item in all_cases}
        missing = set(keys) - by_key.keys()
        if missing:
            raise ValueError("Unknown selective-routing case keys: " + ", ".join(sorted(missing)))
        return [by_key[key] for key in keys]
    return all_cases[:limit]


def _percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(fraction * len(values)) - 1)]


def _routing_event(trace):
    if any(e.get("actor") == "judge" and e.get("event") == "gemini_escalation" for e in trace):
        return "gemini"
    if any(e.get("actor") == "judge" and e.get("event") == "model_escalation" for e in trace):
        return "offline_model"
    if any(e.get("actor") == "judge" and e.get("event") == "human_review_without_model" for e in trace):
        return "human"
    if any(e.get("actor") == "judge" and e.get("event") == "repair_satisfied" for e in trace):
        return "evidence_resolved"
    return "rules_clear"


def run(output, policy, *, live=False, limit=120, env_file=None, model=MODEL_DEFAULT, keys=None,
        policy_version="ryde-policy-1.0.0"):
    output = Path(output).resolve()
    if output.is_relative_to(Path(__file__).parents[1]):
        raise ValueError("Benchmark outputs must be stored outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=env_file or "", model_provider="openai_compatible" if live else "deterministic_mock",
        policy_version=policy_version, policy_path=str(policy), read_database_dsn="",
        tribunal_database_dsn="", model_name=model if live else "routing-benchmark-mock",
    )
    provider = _BASE.UsageCapturingProvider(build_provider(settings))
    rows = []
    selected = select_cases(keys, limit)
    for spec in selected:
        before_calls, before_usage, before_roles = provider.attempts, len(provider.usage), len(provider.roles)
        reader = _BASE.BenchmarkReader(spec)
        client = TestClient(create_app(build_container(reader=reader, settings=settings, provider=provider)))
        headers = {"X-Reviewer-Id": "REV-ROUTING-BENCHMARK"}
        filed = client.post("/api/v1/disputes", headers=headers, json={
            "category": spec["category"], "ride_id": "RIDE-090001", "filed_by": "rider",
            "subject": "Synthetic selective-routing benchmark case",
            "description": "Evaluate this dispute using recorded trip evidence and published policy.",
        })
        if filed.status_code != 201:
            raise RuntimeError(f"Filing {spec['key']} failed: HTTP {filed.status_code}: {filed.text[:300]}")
        case_id = filed.json()["case_id"]
        started = time.monotonic()
        response = client.post(f"/api/v1/disputes/{case_id}/adjudicate", headers=headers)
        elapsed = time.monotonic() - started
        body = response.json()
        judge = body.get("judge") or {}
        action = judge.get("recommended_action") or {}
        amount = (action.get("amount") or {}).get("amount_cents", 0)
        trace = body.get("trace", [])
        actual_route = _routing_event(trace)
        judge_calls = sum(role == "judge" for role in provider.roles[before_roles:]) if live else 0
        gemini_requested = bool(live and any(
            e.get("actor") == "judge" and e.get("event") == "gemini_escalation" for e in trace
        ))
        fallback_events = [e for e in trace if e.get("event") == "fallback"]
        gemini_response_received = bool(
            gemini_requested and not fallback_events and judge.get("provider", {}).get("kind") == "llm"
        )
        actual_outcome = {"status": body.get("status"), "ruling_type": judge.get("ruling_type"),
                          "amount_cents": amount}
        expected = spec["expected_outcome"]
        outcome_correct = response.status_code == 200 and all(
            expected[k] is None or actual_outcome[k] == expected[k]
            for k in ("status", "ruling_type", "amount_cents")
        )
        expected_route = spec["expected_route"]
        route_correct = (
            (expected_route == "gemini" and actual_route in {"gemini", "offline_model"})
            or (expected_route == "human" and actual_route == "human" and not gemini_requested)
            or (expected_route == "no_gemini" and not gemini_requested and body.get("status") == "resolved")
        )
        citations = [c for side in (body.get("advocates") or {}).values()
                     for claim in side.get("claims", []) for c in claim.get("citations", [])]
        validator_findings = [e.get("summary", "") for e in trace
                              if e.get("actor") == "independent_validator" and e.get("event") == "final_validation"
                              and not str(e.get("summary", "")).startswith("Policy citations, evidence references")]
        helpers = Counter(e.get("actor") for e in trace if e.get("actor") in
                          ("evidence_auditor", "evidence_verification", "fraud_detector"))
        model_proposal = body.get("model_proposed_ruling")
        row = {
            "key": spec["key"], "scenario_family": spec["scenario_family"],
            "routing_group": spec["routing_group"], "category": spec["category"],
            "expected_route": expected_route, "actual_route": actual_route,
            "route_correct": route_correct, "expected_outcome": expected,
            "actual_outcome": actual_outcome, "outcome_correct": outcome_correct,
            "latency_seconds": round(elapsed, 3), "provider": judge.get("provider"),
            "gemini_requested": gemini_requested,
            "gemini_response_received": gemini_response_received,
            "judge_provider_calls": judge_calls,
            "provider_completion_invocations": provider.attempts - before_calls,
            "provider_roles": provider.roles[before_roles:],
            "repair_rounds": sum(e.get("actor") == "judge" and e.get("event") == "review_round" for e in trace),
            "evidence_helper_agent_invocations": dict(helpers),
            "citation_count": len(citations),
            "invalid_advocate_citations": sum(not c.get("valid", False) for c in citations),
            "fallback": bool(fallback_events),
            "fallback_reason": fallback_events[0].get("summary") if fallback_events else None,
            "validator_findings": validator_findings,
            "proposal_validator_passed": gemini_response_received and not validator_findings,
            "invalid_judge_evidence_citation": any("invalid Judge evidence citation" in f for f in validator_findings),
            "gemini_output": model_proposal if gemini_response_received else None,
            "usage": _BASE.sum_usage(provider.usage[before_usage:]),
        }
        rows.append(row)
        (output / f"{spec['key']}.json").write_text(json.dumps(body, indent=2))
        print(spec["key"], actual_route, body.get("status"), "route_correct=" + str(route_correct), flush=True)

    groups = {}
    for group in sorted({row["routing_group"] for row in rows}):
        members = [row for row in rows if row["routing_group"] == group]
        groups[group] = {
            "cases": len(members), "expected_gemini": sum(r["expected_route"] == "gemini" for r in members),
            "actual_gemini_requests": sum(r["gemini_requested"] for r in members),
            "gemini_responses_received": sum(r["gemini_response_received"] for r in members),
            "proposal_validator_passes": sum(r["proposal_validator_passed"] for r in members),
            "route_accuracy": sum(r["route_correct"] for r in members) / len(members),
            "outcome_accuracy": sum(r["outcome_correct"] for r in members) / len(members),
        }
    cases_all = cases()
    total = len(rows)
    expected_positive = sum(row["expected_route"] == "gemini" for row in rows)
    true_positive = sum(row["expected_route"] == "gemini" and row["gemini_requested"] for row in rows)
    actual_calls = sum(row["gemini_requested"] for row in rows)
    safe_hardstops = [row for row in rows if row["routing_group"] == "human_hard_stop"]
    usage = _BASE.sum_usage([row["usage"] for row in rows if row["usage"]])
    report = {
        "benchmark_version": VERSION, "benchmark_type": "stratified selective-routing test; not prevalence estimate",
        "policy_version": policy_version,
        "cases": total, "scenario_family_count": len({item["scenario_family"] for item in cases_all}),
        "benchmark_sha256": hashlib.sha256(json.dumps(cases_all, sort_keys=True).encode()).hexdigest(),
        "live_provider": live,
        "configured_provider_model": model if live else "routing-benchmark-mock",
        "resulting_judge_provider_counts": dict(Counter(
            (row.get("provider") or {}).get("kind", "unknown") for row in rows
        )),
        "routing_groups": groups, "routing_accuracy": sum(r["route_correct"] for r in rows) / total if total else None,
        "outcome_accuracy": sum(r["outcome_correct"] for r in rows) / total if total else None,
        "outcome_accuracy_definition": (
            "Resolved cases match status, ruling, and amount; expected-escalation cases match the escalated status."
        ),
        "expected_gemini_share": expected_positive / total if total else None,
        "actual_gemini_request_share": actual_calls / total if total else None,
        "gemini_routing_precision": true_positive / actual_calls if actual_calls else None,
        "gemini_routing_recall": true_positive / expected_positive if expected_positive else None,
        "gemini_responses_received": sum(row["gemini_response_received"] for row in rows),
        "gemini_response_rate_on_expected_cases": (
            sum(row["gemini_response_received"] for row in rows if row["expected_route"] == "gemini")
            / expected_positive if expected_positive else None
        ),
        "no_call_rate_on_no_call_cases": sum(not r["gemini_requested"] for r in rows if r["expected_route"] == "no_gemini") / max(1, sum(r["expected_route"] == "no_gemini" for r in rows)),
        "hardstop_provider_safety_rate": sum(not r["gemini_requested"] and r["actual_route"] == "human" for r in safe_hardstops) / max(1, len(safe_hardstops)),
        "fallback_count": sum(row["fallback"] for row in rows),
        "invalid_advocate_citations": sum(row["invalid_advocate_citations"] for row in rows),
        "cases_with_invalid_judge_evidence_citations": sum(row["invalid_judge_evidence_citation"] for row in rows),
        "gemini_proposal_validator_pass_rate": (
            sum(row["proposal_validator_passed"] for row in rows)
            / max(1, sum(row["gemini_response_received"] for row in rows))
        ),
        "gemini_proposals_rejected_by_validator": sum(
            row["gemini_response_received"] and not row["proposal_validator_passed"] for row in rows
        ),
        "p95_latency_seconds": _percentile([row["latency_seconds"] for row in rows], .95),
        "provider_completion_invocations": sum(row["provider_completion_invocations"] for row in rows), "usage": usage,
        "cost": None, "rows": rows,
        "limitations": ["Synthetic stratified routing test; not a production accuracy or prevalence claim.",
                        "Expected routing labels are benchmark-only and are never passed to the API.",
                        "Cost is not estimated; usage is reported only when returned by the provider."],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--keys", nargs="+")
    parser.add_argument("--env-file")
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--policy-version", default="ryde-policy-1.0.0",
                        help="Policy version to evaluate (defaults to the frozen benchmark's original 1.0.0).")
    args = parser.parse_args()
    run(args.output, args.policy, live=args.live, limit=args.limit,
        env_file=args.env_file, model=args.model, keys=args.keys,
        policy_version=args.policy_version)
