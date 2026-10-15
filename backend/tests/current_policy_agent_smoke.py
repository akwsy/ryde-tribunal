"""Small current-policy agent smoke using only synthetic in-memory trip records.

Expected results stay in this file's evaluation metadata and are never added to filings,
reader records, prompts, or precedent. The configured PostgreSQL DSNs are always blanked.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.container import build_container
from app.persistence.reader import (
    AppEvent, ChatLog, FareBreakdown, FareComponent, GpsSample, GpsSamples,
    Profile, RideRecord, RouteRecord,
)
from app.persistence.store import ResultStore
from app.providers.factory import build_provider
from app.settings import Settings
from tests.fixtures.reader import FixtureReader


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "database/seed/policy/ryde-policy-1.1.0.json"
AS_OF = datetime.now(timezone.utc).replace(microsecond=0)


CASES = [
    {"key": "route-longer-same-quoted-fare", "category": "route_deviation",
     "expected_status": "resolved", "expected_ruling": "no_action", "expected_amount": 0,
     "route_km": (5.0, 9.4), "quoted": 1800, "charged": 1800,
     "description": "The route was longer than expected, but the receipt matches the quoted fare."},
    {"key": "route-unitemized-excess", "category": "route_deviation",
     "expected_status": "escalated", "expected_ruling": None, "expected_amount": None,
     "route_km": (5.0, 9.4), "quoted": 1800, "charged": 2050,
     "description": "The final charge exceeds the quote and no itemized reason is recorded."},
    {"key": "fare-ledger-reconciles", "category": "fare_calculation",
     "expected_status": "resolved", "expected_ruling": "no_action", "expected_amount": 0,
     "quoted": 1800, "charged": 1800, "components": [("trip fare", 1600), ("platform fee", 200)],
     "description": "The verified itemized fare components add up to the recorded payment."},
    {"key": "fare-ledger-conflict", "category": "fare_calculation",
     "expected_status": "escalated", "expected_ruling": None, "expected_amount": None,
     "quoted": 1800, "charged": 1800, "components": [("trip fare", 1600), ("platform fee", 350)],
     "description": "The itemized components do not reconcile with the recorded payment."},
    {"key": "no-show-rider-cancel-window", "category": "no_show_charge",
     "expected_status": "resolved", "expected_ruling": "refund", "expected_amount": 661,
     "fee_type": "rider_cancellation", "actor": "rider", "cancel_seconds": 180,
     "cancellation_fee": 661,
     "description": "A rider cancellation charge was recorded exactly at the three-minute boundary."},
    {"key": "no-show-nonstandard-rider-charge", "category": "no_show_charge",
     "expected_status": "escalated", "expected_ruling": None, "expected_amount": None,
     "fee_type": "rider_cancellation", "actor": "rider", "cancel_seconds": 240,
     "cancellation_fee": 450,
     "description": "The verified timeline is complete, but the amount does not match the published rider cancellation charge."},
    {"key": "cancellation-voucher-window", "category": "other_cancellation_fee",
     "expected_status": "resolved", "expected_ruling": "refund", "expected_amount": 661,
     "fee_type": "rider_cancellation", "actor": "rider", "cancel_seconds": 120,
     "cancellation_fee": 661,
     "description": "A verified rider cancellation charge meets the published waiver conditions."},
    {"key": "waiting-fee-voucher-window", "category": "other_cancellation_fee",
     "expected_status": "resolved", "expected_ruling": "refund", "expected_amount": 500,
     "fee_type": "rider_waiting", "wait_seconds": 180, "waiting_fee": 500,
     "description": "The recorded rider waiting charge is at the three-minute boundary."},
    {"key": "driver-payout-is-not-rider-refund", "category": "other_cancellation_fee",
     "expected_status": "escalated", "expected_ruling": None, "expected_amount": None,
     "fee_type": "driver_payout", "actor": "driver", "cancel_seconds": 240,
     "cancellation_fee": 450,
     "description": "The disputed amount is a driver payout, not a rider cancellation charge."},
]


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_reader(spec: dict, index: int) -> FixtureReader:
    reader = FixtureReader()
    ride_id = f"RIDE-{970001 + index:06d}"
    rider_id, driver_id = f"USR-R-{index+1:06d}", f"USR-D-{index+1:06d}"
    start = AS_OF - timedelta(hours=2)
    cancelled = spec.get("actor") is not None
    cancel_at = start + timedelta(seconds=spec.get("cancel_seconds", 240))
    completed_at = None if cancelled else start + timedelta(minutes=35)
    wait = spec.get("wait_seconds")
    ride_status = "cancelled" if cancelled else "completed"
    reader.rides[ride_id] = RideRecord(
        ride_id=ride_id, rider_id=rider_id, driver_id=driver_id,
        booked_at=timestamp(start - timedelta(minutes=20)), accepted_at=timestamp(start),
        completed_at=timestamp(completed_at) if completed_at else None,
        status=ride_status, quoted_fare_cents=spec.get("quoted", 1800),
        charged_fare_cents=spec.get("charged", 1800), currency="SGD", service_tier="RydeX",
        cancellation_timestamp=timestamp(cancel_at) if cancelled else None,
        cancellation_actor=spec.get("actor"), driver_waited_seconds=wait,
        verification_status="verified", synthetic=True,
    )
    route_km = spec.get("route_km", (5.0, 5.0))
    reader.routes[ride_id] = RouteRecord(
        ride_id=ride_id, planned_distance_km=route_km[0], actual_distance_km=route_km[1],
        planned_duration_s=1200, actual_duration_s=1500,
        driver_arrival_at=timestamp(start + timedelta(seconds=60)) if cancelled and spec.get("actor") == "driver" else None,
        driver_wait_seconds=wait, verification_status="verified", synthetic=True,
    )
    reader.gps[ride_id] = GpsSamples(
        ride_id=ride_id, min_distance_to_pickup_m=8.0,
        samples=[GpsSample(seq=1, lat=1.30, lon=103.85, at=timestamp(start + timedelta(seconds=60)),
                           accuracy_m=5, verification_status="verified", synthetic=True)],
    )
    components = spec.get("components", [("trip fare", spec.get("charged", 1800))])
    reader.fares[ride_id] = FareBreakdown(
        ride_id=ride_id, currency="SGD",
        components=[FareComponent(name=name, amount_cents=amount) for name, amount in components],
        total_fare_cents=sum(amount for _, amount in components),
        cancellation_fee_cents=spec.get("cancellation_fee", 0),
        waiting_fare_cents=spec.get("waiting_fee", 0),
        verification_status="verified", synthetic=True,
    )
    reader.chats[ride_id] = ChatLog(ride_id=ride_id, messages=[])
    reader.profiles[rider_id] = Profile(user_id=rider_id, synthetic=True)
    reader.profiles[driver_id] = Profile(user_id=driver_id, synthetic=True)
    if cancelled:
        reader.app_events[ride_id] = [AppEvent(
            event_id=f"EV-{index+970001:06d}", ride_id=ride_id, sequence_no=1,
            event_at=timestamp(cancel_at), event_type=f"{spec['actor']}_cancelled",
            details="Synthetic verified cancellation event", verification_status="verified", synthetic=True,
        )]
    return reader


class ProviderRecorder:
    """Capture role and summary metadata, never prompts, credentials, or raw model input."""
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls: list[dict] = []

    @property
    def meta(self):
        return self.delegate.meta

    def complete(self, prompt, response_schema):
        role = str(prompt.get("role", "unknown"))
        record = {
            "role": role,
            "judge_checks_present": bool(prompt.get("judge_case_checks")),
            "advocate_checks_present": bool(prompt.get("advocate_case_checks")),
            "completed": False,
            "usage": None,
        }
        self.calls.append(record)
        try:
            completion = self.delegate.complete(prompt, response_schema)
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            raise
        record["completed"] = True
        record["usage"] = dict(completion.usage) if completion.usage else None
        return completion


def run(output: Path, *, live: bool, env_file: Path | None, model: str) -> dict:
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Smoke reports must be stored outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=str(env_file) if live and env_file else None,
        model_provider="openai_compatible" if live else "deterministic_mock",
        model_name=model if live else "current-policy-smoke-mock",
        policy_version="ryde-policy-1.1.0", policy_path=str(POLICY),
        read_database_dsn="", tribunal_database_dsn="", currency="SGD",
        escalation_confidence_threshold=0.70,
    )
    provider = ProviderRecorder(build_provider(settings))
    rows = []
    for index, spec in enumerate(CASES):
        reader = make_reader(spec, index)
        ride_id = f"RIDE-{970001 + index:06d}"
        app = create_app(build_container(reader=reader, settings=settings,
                                         provider=provider, store=ResultStore()))
        client = TestClient(app)
        headers = {"X-Reviewer-Id": "REV-CURRENT-POLICY-SMOKE"}
        filing = {
            "category": spec["category"], "ride_id": ride_id, "filed_by": "rider",
            "subject": "Synthetic policy verification", "description": spec["description"],
            "category_details": ({"fee_type": spec["fee_type"]} if spec.get("fee_type") else {}),
        }
        filed = client.post("/api/v1/disputes", headers=headers, json=filing)
        if filed.status_code != 201:
            raise RuntimeError(f"Synthetic filing failed for {spec['key']}: HTTP {filed.status_code}")
        case_id = filed.json()["case_id"]
        call_start = len(provider.calls)
        started = time.monotonic()
        response = client.post(f"/api/v1/disputes/{case_id}/adjudicate", headers=headers)
        latency = time.monotonic() - started
        if response.status_code != 200:
            raise RuntimeError(f"Adjudication failed for {spec['key']}: HTTP {response.status_code}")
        body = response.json()
        trace = body.get("trace", [])
        judge = body.get("judge") or {}
        action = judge.get("recommended_action") or {}
        amount = (action.get("amount") or {}).get("amount_cents", 0)
        calls = provider.calls[call_start:]
        judge_called = any(call["role"] == "judge" for call in calls)
        proposal = body.get("model_proposed_ruling")
        validation_summaries = [event.get("summary", "") for event in trace
                    if event.get("actor") == "independent_validator" and event.get("event") == "final_validation"]
        validator_errors = [summary for summary in validation_summaries
                            if not summary.startswith("Policy citations, evidence references")]
        expected_matches = (
            body.get("status") == spec["expected_status"]
            and (spec["expected_ruling"] is None or judge.get("ruling_type") == spec["expected_ruling"])
            and (spec["expected_amount"] is None or amount == spec["expected_amount"])
        )
        rows.append({
            "key": spec["key"], "category": spec["category"],
            "description": spec["description"], "policy_version": body.get("policy_version"),
            "expected_status": spec["expected_status"], "actual_status": body.get("status"),
            "expected_ruling": spec["expected_ruling"], "actual_ruling": judge.get("ruling_type"),
            "expected_amount_cents": spec["expected_amount"], "actual_amount_cents": amount,
            "expected_match": expected_matches,
            "agent_calls": calls, "judge_call_count": sum(c["role"] == "judge" for c in calls),
            "non_judge_provider_call_count": sum(c["role"] != "judge" for c in calls),
            "judge_provider": judge.get("provider"), "judge_proposal": proposal,
            "validator_summaries": validation_summaries,
            "validator_errors": validator_errors,
            "fallback": any(event.get("event") == "fallback" for event in trace),
            "repair_rounds": sum(event.get("actor") == "judge" and event.get("event") == "review_round" for event in trace),
            "trace": trace, "latency_seconds": round(latency, 3),
        })
        (output / f"{spec['key']}.json").write_text(json.dumps(body, indent=2))

    judge_calls = sum(row["judge_call_count"] for row in rows)
    report = {
        "suite": "current-policy-agent-smoke-v1", "policy_version": "ryde-policy-1.1.0",
        "live_provider": live, "configured_model": model if live else "deterministic-mock",
        "configured_provider_identity": {
            "kind": provider.meta.kind, "model": provider.meta.model,
            "display_name": provider.meta.display_name,
        },
        "cases": len(rows), "outcome_accuracy": sum(row["expected_match"] for row in rows) / len(rows),
        "judge_provider_calls": judge_calls,
        "non_judge_provider_calls": sum(row["non_judge_provider_call_count"] for row in rows),
        "judge_path_exercised": judge_calls > 0,
        "fallback_count": sum(row["fallback"] for row in rows),
        "validator_error_count": sum(len(row["validator_errors"]) for row in rows),
        "agent_role_call_counts": dict(Counter(call["role"] for row in rows for call in row["agent_calls"])),
        "p95_latency_seconds": sorted(row["latency_seconds"] for row in rows)[math.ceil(.95 * len(rows)) - 1],
        "provider_reported_usage": {
            key: sum(call["usage"].get(key, 0) for row in rows for call in row["agent_calls"]
                     if call.get("usage") and isinstance(call["usage"].get(key), int))
            for key in sorted({key for row in rows for call in row["agent_calls"]
                               if call.get("usage") for key in call["usage"]})
        } or None,
        "database_connected": False,
        "expected_labels_sent_to_app": False,
        "rows": rows,
        "limitations": [
            "Synthetic smoke only; not a prevalence estimate or benchmark result.",
            "The smoke provider wrapper records role counts and provider-reported token counters but does not retain full prompts.",
            "A successful Judge-path verification requires at least one eligible Judge call and a validated live proposal.",
        ],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    args = parser.parse_args()
    result = run(args.output, live=args.live, env_file=args.env_file, model=args.model)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
