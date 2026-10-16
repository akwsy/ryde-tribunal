"""Deterministic first pass for the source-backed Ryde policy.

This module only resolves cases when the published rule and verified source records
leave exactly one supported outcome. Anything outside these narrow cases is returned
as uncertain for the advocate repair loop and, ultimately, model review.
"""
from __future__ import annotations

from typing import Any

from app.policy.official import factual_values
from app.policy.loader import is_source_backed_policy


def clear_ruling(category: str, facts: dict[str, Any], evidence: list, filed_at: str,
                 policy) -> dict[str, Any] | None:
    if not is_source_backed_policy(policy.policy_version):
        return None
    ride = facts.get("ride") or {}
    fare = facts.get("fare") or {}
    route = facts.get("route") or {}
    values = factual_values(facts, filed_at)
    if ride.get("verification_status") != "verified":
        return None
    verified = [item for item in evidence if item.verification.status.value == "verified"]
    if not verified:
        return None
    rule_ids = policy.rule_ids()

    if category == "route_deviation":
        quoted, charged = ride.get("quoted_fare_cents"), ride.get("charged_fare_cents")
        if (quoted is None or charged is None or charged > quoted
                or route.get("verification_status") != "verified"):
            return None
        decisive = [
            {"fact": "The recorded charge did not exceed the quoted fare.",
             "evidence_references": _supporting_ids(evidence, "charged_fare_cents") +
                                   _supporting_ids(evidence, "quoted_fare_cents")},
        ]
        if not all(item["evidence_references"] for item in decisive):
            return None
        return _ruling("no_action", "none", None, 0.96,
                       "The verified fare record matches the quoted fare. Ryde’s published guidance does not establish a refund from route length alone.",
                       decisive, evidence, rule_ids)

    if category == "fare_calculation":
        ledger_total = fare.get("total_fare_cents")
        charged = ride.get("charged_fare_cents")
        parts = fare.get("components") or []
        adjustments = fare.get("adjustments") or []
        all_parts = [*parts, *adjustments]
        amounts = [part.get("amount_cents") for part in all_parts if isinstance(part, dict)]
        if (fare.get("verification_status") != "verified" or not parts
                or ledger_total is None or charged is None
                or len(amounts) != len(all_parts) or sum(amounts) != ledger_total
                or charged != ledger_total):
            return None
        refs = sorted(set(_supporting_ids(evidence, "charged_fare_cents") +
                          _supporting_ids(evidence, "total_fare_cents") +
                          _supporting_ids(evidence, "components")))
        if not refs:
            return None
        return _ruling("no_action", "none", None, 0.96,
                       "The verified payment total matches the itemised fare ledger and its listed components. No unsupported refund amount was inferred.",
                       [{"fact": "The verified payment total equals the sum of the fare ledger components.",
                         "evidence_references": refs}], evidence, rule_ids)

    if category not in {"no_show_charge", "other_cancellation_fee"}:
        return None
    if category == "other_cancellation_fee":
        fee_type = (facts.get("filing") or {}).get("category_details", {}).get("fee_type")
        if fee_type == "rider_waiting":
            wait_fee = fare.get("waiting_fare_cents")
            wait = values.get("driver_waited_seconds")
            age = values.get("days_since_trip")
            if (ride.get("status") not in {"completed", "complete"}
                    or not ride.get("completed_at")
                    or fare.get("verification_status") != "verified"
                    or (ride.get("driver_waited_seconds") is None
                        and (route.get("verification_status") != "verified"
                             or route.get("driver_wait_seconds") is None))
                    or wait_fee != 500 or wait is None or age is None or age < 0):
                return None
            refs = sorted(set(_supporting_ids(evidence, "waiting_fare_cents") +
                              _supporting_ids(evidence, "driver_waited_seconds") +
                              _supporting_ids(evidence, "completed_at")))
            if not refs:
                return None
            if age > 30:
                return _ruling("no_action", "none", None, 0.94,
                               "The published 30-day waiting-fee waiver window has passed.",
                               [{"fact": "The waiver request was filed more than 30 days after the trip.",
                                 "evidence_references": refs}], evidence, rule_ids)
            if wait <= 180:
                return _ruling("refund", "voucher", {"amount_cents": 500, "currency": "SGD"},
                               0.94,
                               "The verified completed-trip record shows no more than the published three-minute waiting period. The eligible waiver is a S$5 voucher, not cash.",
                               [{"fact": "The verified wait did not exceed 180 seconds.",
                                 "evidence_references": refs}], evidence, rule_ids)
            return _ruling("no_action", "none", None, 0.93,
                           "The verified completed-trip record shows a wait beyond the published three-minute threshold for the S$5 waiting charge.",
                           [{"fact": "The verified wait exceeded 180 seconds.",
                             "evidence_references": refs}], evidence, rule_ids)
        if fee_type != "rider_cancellation":
            return None
    service = values.get("service_tier")
    if service not in {"RydeX", "RydeXL", "RydePET", "RydePOOL", "RydeFLASH", "RydeHIRE", "RydeSEND"}:
        return None
    fee = fare.get("cancellation_fee_cents")
    age = values.get("days_since_trip")
    actor = values.get("cancellation_actor")
    if fee != 661 or age is None or age < 0 or not actor:
        return None

    # The published 30-day waiver deadline makes a later request ineligible even
    # when the original cancellation fell inside the free window. Resolve that
    # narrow, fully evidenced case without asking a model to restate the deadline.
    if age > 30:
        refs = sorted(set(_supporting_ids(evidence, "cancellation_fee_cents") +
                          _supporting_ids(evidence, "cancellation_timestamp") +
                          _supporting_ids(evidence, "event_at") +
                          _supporting_ids(evidence, "driver_waited_seconds")))
        if not refs:
            return None
        return _ruling("no_action", "none", None, 0.94,
                       "The verified trip and filing dates show the waiver request was made after the published 30-day deadline.",
                       [{"fact": "The waiver request was filed more than 30 days after the trip.",
                         "evidence_references": refs}], evidence, rule_ids)

    invalid_fee = False
    deciding_label = "The verified trip facts support the cancellation fee under the published policy."
    if actor == "rider":
        elapsed = values.get("seconds_after_matching")
        if elapsed is None:
            return None
        before = values.get("seconds_before_schedule")
        if values.get("scheduled_at"):
            before_match = values.get("seconds_before_schedule_at_match")
            if before is None or before_match is None or before == 900:
                return None
            invalid_fee = before > 900 or (before < 900 and before_match < 900 and elapsed <= 180)
        else:
            invalid_fee = elapsed <= 180
        deciding_label = ("The rider cancelled within the published free-cancellation window."
                          if invalid_fee else "The rider cancelled outside the published free-cancellation window.")
    elif actor == "driver":
        wait = values.get("driver_waited_seconds")
        if wait is None or not values.get("arrival_button_recorded"):
            return None
        gps = facts.get("gps") or {}
        if not gps.get("samples") or gps.get("min_distance_to_pickup_m") is None:
            return None
        invalid_fee = wait <= 180
        deciding_label = ("The verified arrival and wait records show the driver waited no longer than the published free-waiting window."
                          if invalid_fee else "The verified arrival and wait records show the driver waited beyond the published free-waiting window.")
    else:
        return None

    if invalid_fee:
        refs = sorted(set(_supporting_ids(evidence, "cancellation_fee_cents") +
                          _supporting_ids(evidence, "cancellation_timestamp") +
                          _supporting_ids(evidence, "event_at") +
                          _supporting_ids(evidence, "driver_waited_seconds")))
        if not refs:
            return None
        decisive = [{"fact": deciding_label, "evidence_references": refs}]
        return _ruling("refund", "voucher", {"amount_cents": 661, "currency": "SGD"},
                       0.94, "The published waiver process supports a S$6.61 voucher when the cancellation fee was charged inside the free window and the request is made within 30 days.",
                       decisive, evidence, rule_ids)
    refs = sorted(set(_supporting_ids(evidence, "cancellation_fee_cents") +
                      _supporting_ids(evidence, "cancellation_actor") +
                      _supporting_ids(evidence, "driver_waited_seconds") +
                      _supporting_ids(evidence, "seconds_after_matching")))
    if not refs:
        return None
    return _ruling("no_action", "none", None, 0.93,
                   "The verified trip facts place the cancellation outside the published free window. The charge is not eligible for the published waiver.",
                   [{"fact": deciding_label, "evidence_references": refs}], evidence, rule_ids)


def _relevant_source_fields(payload, category, prefix=""):
    """Keep the source citation intact while omitting administrative/profile fields."""
    groups = {
        "route_deviation": ("charged_fare_cents", "quoted_fare_cents", "actual_distance_km", "planned_distance_km", "total_fare_cents", "service_tier"),
        "fare_calculation": ("charged_fare_cents", "total_fare_cents", "quoted_fare_cents", "cancellation_fee_cents", "waiting_fare_cents", "service_tier"),
        "no_show_charge": ("cancellation_fee_cents", "cancellation_actor", "accepted_at", "cancellation_timestamp", "driver_waited_seconds", "driver_arrival_at", "arrival_at", "arrival_button_recorded", "min_distance_to_pickup_m", "service_tier", "scheduled_at", "completed_at"),
        "other_cancellation_fee": ("cancellation_fee_cents", "waiting_fare_cents", "cancellation_actor", "accepted_at", "cancellation_timestamp", "driver_waited_seconds", "completed_at", "service_tier"),
    }
    fields = groups.get(category, tuple(dict.fromkeys(field for group in groups.values() for field in group)))
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if key.startswith("_"):
            continue
        if isinstance(value, dict):
            yield from _relevant_source_fields(value, category, path)
        elif key in fields and value is not None and not isinstance(value, list):
            yield fields.index(key), path, value


def _readable_source_value(field, value):
    if field.endswith("_cents") and isinstance(value, (int, float)):
        return f"S${value / 100:.2f}"
    if field.endswith("_seconds") and isinstance(value, (int, float)):
        minutes, seconds = divmod(int(value), 60)
        return f"{minutes} min {seconds} sec" if minutes else f"{seconds} sec"
    if field.endswith("_km"):
        return f"{value} km"
    if field.endswith("_m"):
        return f"{value} m"
    if isinstance(value, bool):
        return "recorded" if value else "not recorded"
    return str(value).replace("_", " ")


def rule_advocate(party: str, evidence: list, policy_ids: list[str], gaps: list[str] | None = None,
                  *, category: str = "", facts: dict[str, Any] | None = None,
                  policy_version: str = "") -> dict[str, Any]:
    """Produce a source-only advocate summary for the deterministic first pass."""
    from app.domain import visible_to

    from app.evidence.citation import CitationValidator
    from app.evidence.models import Citation

    visible = [item for item in evidence if visible_to(item.visibility, party)]
    verified = [item for item in visible if item.verification.status.value == "verified"]
    verified_ids = [item.evidence_id for item in verified]
    label = "rider" if party == "rider" else "driver"
    claims = []
    cited_ids = set()
    validator = CitationValidator(verified[0].case_id, {item.evidence_id: item for item in verified}) if verified else None
    readable = {
        "quoted_fare_cents": "quoted fare", "charged_fare_cents": "charged fare",
        "cancellation_fee_cents": "cancellation fee", "cancellation_actor": "cancelling party",
        "cancellation_timestamp": "cancellation time", "service_tier": "service type",
        "actual_distance_km": "recorded route distance", "planned_distance_km": "planned route distance",
        "driver_waited_seconds": "driver wait time", "min_distance_to_pickup_m": "distance from pickup",
    }
    candidates = [(priority, item, field, value) for item in verified
                  for priority, field, value in _relevant_source_fields(item.payload, category)]
    candidates.sort(key=lambda row: row[0])
    for _, item, field, value in candidates:
        name = field.rsplit(".", 1)[-1]
        label_text = readable.get(name, name.replace("_", " "))
        citation = Citation(evidence_id=item.evidence_id, field_path=field,
                            observed_value=value, supports=f"Recorded {label_text}")
        result = validator.validate(citation, party)
        if not result.valid:
            continue
        claims.append({"text": f"The source record shows {label_text}: {_readable_source_value(name, value)}.",
                       "citations": [{"evidence_id": item.evidence_id, "field_path": field,
                                      "observed_value": value, "supports": citation.supports,
                                      "valid": True}]})
        cited_ids.add(item.evidence_id)
        if len(claims) >= 12:
            break
    facts = facts or {}
    ride = facts.get("ride") or {}
    route = facts.get("route") or {}
    fare = facts.get("fare") or {}
    amount = lambda value: f"S${value / 100:.2f}" if isinstance(value, (int, float)) else "not recorded"
    if category == "route_deviation":
        actual = route.get("actual_distance_km", "not recorded")
        planned = route.get("planned_distance_km", "not recorded")
        charged = amount(ride.get("charged_fare_cents"))
        quoted = amount(ride.get("quoted_fare_cents"))
        variant = int(abs(float(actual)) * 10 + abs(float(planned)) * 7) % 5 if isinstance(actual, (int, float)) and isinstance(planned, (int, float)) else 0
        rider_openers = (
            "The rider disputes a possible overcharge",
            "The rider asks the Tribunal to examine the longer route",
            "The rider's concern is the route recorded for this trip",
            "The rider requests a fare review after the route difference",
            "The rider challenges the trip's fare calculation",
        )
        driver_openers = (
            "The driver asks that the completed trip record guide the review",
            "The driver's response relies on the recorded journey and fare",
            "The driver submits that distance should be assessed with the fare record",
            "The driver points to the trip's route and quoted price together",
            "The driver's position is to compare the route and fare records as a whole",
        )
        if party == "rider":
            argument = (f"{rider_openers[variant]}: {actual} km recorded versus {planned} km planned; "
                        f"the ledger lists {charged} charged against {quoted} quoted. The rider asks whether "
                        "the difference is valid under the fare policy.")
        else:
            argument = (f"{driver_openers[variant]}: {actual} km recorded, {planned} km planned, "
                        f"{charged} charged, and {quoted} quoted. Route distance alone does not establish "
                        "an automatic refund under Ryde's published guidance.")
    elif category == "no_show_charge":
        from app.policy.official import factual_values
        values = factual_values(facts, (facts.get("filing") or {}).get("filed_at"))
        fee = amount(fare.get("cancellation_fee_cents"))
        actor = values.get("cancellation_actor", "not recorded")
        elapsed = values.get("seconds_after_matching")
        wait = values.get("driver_waited_seconds")
        gps = facts.get("gps") or {}
        distance = gps.get("min_distance_to_pickup_m")
        proximity = f"GPS records {distance} metres from pickup" if distance is not None else "pickup proximity is unrecorded"
        messages = (facts.get("chat") or {}).get("messages", []) or []
        contact_recorded = any(message.get("kind") == "call_attempt" or
                               message.get("contact_attempt_recorded") is True for message in messages)
        contact = "a driver contact attempt appears in the platform log" if contact_recorded else "no driver contact attempt appears in the platform log"
        contact_summary = "platform log includes a driver contact attempt" if contact_recorded else "platform log contains no driver contact attempt"
        timing = f"{elapsed} seconds after matching" if elapsed is not None else "no verified match interval"
        waiting = f"{wait} seconds" if wait is not None else "no verified wait duration"
        wait_assessment = (
            "the recorded wait exceeds the published three-minute period"
            if isinstance(wait, (int, float)) and wait > 180
            else "the recorded wait does not exceed the published three-minute period"
            if isinstance(wait, (int, float))
            else "the wait cannot be compared with the published three-minute period"
        )
        variant = int((int(elapsed or 0) + int(wait or 0) + int(fare.get("cancellation_fee_cents", 0) or 0)) % 5)
        rider_openers = (
            "The rider disputes whether the cancellation fee was valid",
            "The rider asks for a review of the no-show charge",
            "The rider's case focuses on the cancellation timeline",
            "The rider contests the fee using the recorded trip events",
            "The rider seeks review of the charge and its timing",
        )
        driver_openers = (
            "The driver grounds the response in the arrival record",
            "The driver's account turns on the recorded wait duration",
            "The driver points to the pickup and cancellation events",
            "The driver's position relies on the trip's arrival and wait data",
            "The driver asks that the pickup timeline be considered",
        )
        if party == "rider":
            argument = (f"{rider_openers[variant]} ({fee}): the recorded actor is {actor} and cancellation was "
                        f"{timing}; the recorded wait is {waiting}; {proximity}. {contact_summary.capitalize()}. Here, {wait_assessment}. The rider asks whether the fee may be invalid "
                        "under the published free-window rule.")
        else:
            argument = (f"{driver_openers[variant]}: the disputed fee is {fee}; the driver waited {waiting}; the recorded cancelling party "
                        f"is {actor}; {proximity}, and {contact}. The records show that {wait_assessment}; "
                        "contact messages do not replace the verified timing evidence.")
    else:
        argument = (f"The {label} asks the Judge to assess the dispute from verified source records and the applicable policy.")
    focus = " Requested checks: " + "; ".join(gaps) if gaps else ""
    argument += focus + f" The submission cites {len(claims)} verified source facts and does not infer intent."
    return {
        "argument": argument,
        "claims": claims,
        "policy_references": list(policy_ids),
        "rejected_evidence": [],
        "invalid_citation_count": 0,
        "invalid_citation_rate": 0.0,
        "provider": {"kind": "rules-engine", "model": "ryde-policy-rules-1",
                     "display_name": "rules-based review", "policy_version": policy_version},
        "_synthetic": False,
        "_cited_evidence_ids": sorted(cited_ids),
    }


def verify_rule_advocates(rider: dict, driver: dict, evidence: list) -> list[dict[str, str]]:
    """Independently verify every rule-first advocate citation against stored records."""
    from app.evidence.citation import CitationValidator
    from app.evidence.models import Citation

    by_id = {item.evidence_id: item for item in evidence}
    findings = []
    for party, advocate in (("rider", rider), ("driver", driver)):
        validator = CitationValidator(
            next(iter(by_id.values())).case_id if by_id else "", by_id
        )
        for claim in advocate.get("claims", []):
            for citation_data in claim.get("citations", []):
                citation = Citation(**{key: citation_data[key] for key in
                                       ("evidence_id", "field_path", "observed_value", "supports")})
                result = validator.validate(citation, party)
                if not result.valid or citation_data.get("valid") is not True:
                    findings.append({
                        "party": party, "claim": claim.get("text", ""),
                        "reason": result.reason if not result.valid else "citation was not marked valid",
                    })
    return findings


def _supporting_ids(evidence: list, key: str) -> list[str]:
    return [item.evidence_id for item in evidence
            if item.verification.status.value == "verified" and _contains(item.payload, key)]


def _contains(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains(child, key) for child in value)
    return False


def _ruling(kind: str, delivery: str, amount: dict | None, confidence: float,
            reasoning: str, decisive: list[dict], evidence: list, policy_ids: list[str]) -> dict:
    refs = sorted({ref for fact in decisive for ref in fact["evidence_references"]})
    return {
        "ruling_type": kind,
        "recommended_action": {"description": reasoning, "delivery": delivery, "amount": amount},
        "confidence": confidence,
        "reasoning": reasoning,
        "evidence_references": refs,
        "policy_references": policy_ids,
        "measurements": {},
        "decisive_facts": decisive,
        "provider": {"kind": "rules-engine", "model": "ryde-policy-rules-1"},
        "_synthetic": False,
    }
