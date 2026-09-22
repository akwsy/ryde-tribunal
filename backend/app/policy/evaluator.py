"""Policy evaluation: case facts -> PolicyContext (applicable rule ids + factual
measurements). This is the ONLY thing the policy layer produces, and it is structurally
incapable of producing a verdict (I-1). Computing `deviation_pct` is a MEASUREMENT; deciding
`refund` is the Judge's, and does not happen here.

The evaluator reads case facts assembled from the DB accessors and:
  * selects the policy rule ids whose SUBJECT is present in the case (a route case pulls the
    RP-ROUTE-* / RP-FARE-* / RP-EV-* rules), attaching each rule's text from the loaded doc, and
  * computes factual measurements from telemetry/fare data.

It never maps a measurement to a remedy.
"""

from __future__ import annotations

from typing import Any

from app.policy.context import Measurement, PolicyContext, PolicyRule
from app.policy.loader import PolicyDocument

# Which rule ids are in-subject for a category. These are SUBJECT groupings, not verdicts.
_CATEGORY_RULES: dict[str, list[str]] = {
    "route_deviation": [
        "RP-FARE-001", "RP-FARE-002", "RP-FARE-003",
        "RP-ROUTE-001", "RP-ROUTE-002", "RP-ROUTE-003", "RP-ROUTE-004", "RP-ROUTE-005",
        "RP-EV-001", "RP-EV-002", "RP-EV-003", "RP-EV-004",
        "RP-ESC-001", "RP-ESC-002", "RP-ESC-003", "RP-ESC-005",
    ],
    "no_show": [
        "RP-FARE-001",
        "RP-NOSHOW-001", "RP-NOSHOW-002", "RP-NOSHOW-003", "RP-NOSHOW-004", "RP-NOSHOW-005",
        "RP-EV-001", "RP-EV-002", "RP-EV-003", "RP-EV-004",
        "RP-ESC-001", "RP-ESC-002", "RP-ESC-003", "RP-ESC-005",
    ],
}


def evaluate(category: str, facts: dict[str, Any], policy: PolicyDocument) -> PolicyContext:
    rule_ids = _CATEGORY_RULES.get(category, [])
    rules: list[PolicyRule] = []
    for rid in rule_ids:
        doc = policy.rule(rid)
        if doc is not None:
            rules.append(PolicyRule(rule_id=doc.rule_id, text=doc.text))

    measurements = _measure(category, facts)
    return PolicyContext(
        policy_version=policy.version,
        category=category,
        applicable_rules=tuple(rules),
        measurements=tuple(measurements),
    )


def _measure(category: str, facts: dict[str, Any]) -> list[Measurement]:
    m: list[Measurement] = []

    def add(key: str, value: Any, unit: str | None = None, src: str | None = None) -> None:
        if value is not None:
            m.append(Measurement(key=key, value=value, unit=unit, source_field=src))

    route = facts.get("route") or {}
    fare = facts.get("fare") or {}
    ride = facts.get("ride") or {}
    gps = facts.get("gps") or {}
    chat = facts.get("chat") or {}

    add("quoted_fare_cents", ride.get("quoted_fare_cents"), "cents", "ride.quoted_fare_cents")
    add("charged_fare_cents", ride.get("charged_fare_cents"), "cents", "ride.charged_fare_cents")
    add("cancellation_fee_cents", fare.get("cancellation_fee_cents"), "cents", "fare.cancellation_fee_cents")
    add("surge_multiplier", fare.get("surge_multiplier"), "x", "fare.surge_multiplier")

    if category == "route_deviation":
        planned = route.get("planned_distance_km")
        actual = route.get("actual_distance_km")
        add("planned_distance_km", planned, "km", "route.planned_distance_km")
        add("actual_distance_km", actual, "km", "route.actual_distance_km")
        if planned and actual and planned > 0:
            dev = round((actual - planned) / planned * 100.0, 1)
            add("deviation_pct", dev, "%", "route.actual_distance_km|route.planned_distance_km")
        planned_dur = route.get("planned_duration_s")
        actual_dur = route.get("actual_duration_s")
        add("planned_duration_s", planned_dur, "s", "route.planned_duration_s")
        add("actual_duration_s", actual_dur, "s", "route.actual_duration_s")
        if planned_dur and actual_dur and planned_dur > 0:
            add("duration_pct_of_estimate", round(actual_dur / planned_dur * 100.0, 1), "%")
        # Longest unexplained stop (measurement, not a verdict).
        longest = 0
        for stop in route.get("stops", []) or []:
            if not stop.get("rider_requested", False):
                longest = max(longest, int(stop.get("duration_s", 0)))
        add("longest_unexplained_stop_s", longest, "s")
        # Whether a recognised justification is present in conditions data (a fact, not a ruling).
        add("deviation_justified",
            bool(route.get("rider_requested_change") or route.get("diversion_evidenced")))

    if category == "no_show":
        min_d = gps.get("min_distance_to_pickup_m")
        add("min_distance_to_pickup_m", min_d, "m", "gps.min_distance_to_pickup_m")
        if min_d is not None:
            add("driver_reached_pickup", bool(min_d <= 100.0))
        add("driver_waited_seconds", ride.get("driver_waited_seconds"), "s")
        # Contact attempt recorded? (a fact read from the chat log)
        msgs = chat.get("messages", []) or []
        contact = any(msg.get("kind") == "call_attempt"
                      or (msg.get("role") == "driver" and msg.get("kind") == "message")
                      for msg in msgs)
        if msgs or ride.get("driver_waited_seconds") is not None:
            add("contact_attempt_recorded", contact)

    return m
