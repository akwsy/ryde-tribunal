"""Post-model rejection gates; no replacement ruling is generated."""
from app.policy.official import factual_values
from app.policy.loader import is_source_backed_policy


def model_review_blockers(
    gaps,
    *,
    precedence_notes=(),
    insufficient=False,
    decisive_evidence_present=True,
    contradiction_note=None,
    safety_signal=False,
    profile_flags=0,
):
    """Return reasons a model cannot safely resolve from the assembled case snapshot.

    These are abstention gates, not ruling rules. They route cases to a human when the
    unresolved issue is absent/conflicting source data, an explicit safety/risk signal, or
    a published-policy boundary that the model cannot fill in. Other interpretive questions
    remain eligible for one Judge model review.
    """
    blockers = []
    if safety_signal:
        blockers.append("A safety signal requires human review.")
    if profile_flags > 0:
        blockers.append("An explicit profile risk flag requires human review.")
    if contradiction_note:
        blockers.append(str(contradiction_note))
    if precedence_notes:
        blockers.append("Verified source records conflict on a material fact.")
    if insufficient or not decisive_evidence_present:
        blockers.append("Decisive source evidence is missing, malformed, or insufficient.")

    policy_boundary_phrases = (
        "service applicability is unknown or excluded",
        "additional fare requires review",
        "scheduled-trip boundary is ambiguous",
        "no published automated remedy supports",
        "policy boundary:",
    )
    source_gap_phrases = (
        "missing decisive fact",
        "records disagree",
        "source records disagree",
        "not established by a verified",
        "not established by verified",
        "lacks corroborating",
        "missing match time",
        "missing quoted or charged fare",
        "do not reconcile",
    )
    for gap in gaps or ():
        lowered = str(gap).lower()
        if any(phrase in lowered for phrase in policy_boundary_phrases):
            blockers.append(str(gap))
        elif any(phrase in lowered for phrase in source_gap_phrases):
            blockers.append(str(gap))
    # Preserve order while keeping the trace concise.
    return list(dict.fromkeys(blockers))


def model_review_reason_codes(reasons):
    """Stable, low-cardinality codes for routing metrics and trace filtering."""
    codes = []
    for reason in reasons or ():
        lowered = str(reason).lower()
        if "safety signal" in lowered:
            code = "safety_signal"
        elif "profile risk" in lowered:
            code = "profile_risk_flag"
        elif "conflict" in lowered or "disagree" in lowered or "contradict" in lowered:
            code = "source_conflict"
        elif "missing" in lowered or "insufficient" in lowered or "malformed" in lowered:
            code = "missing_or_insufficient_evidence"
        elif "service" in lowered and ("excluded" in lowered or "unknown" in lowered):
            code = "service_applicability"
        elif "scheduled-trip boundary" in lowered:
            code = "scheduled_trip_boundary"
        elif "fare" in lowered or "remedy" in lowered:
            code = "unsupported_remedy"
        else:
            code = "policy_boundary"
        if code not in codes:
            codes.append(code)
    return codes


def explain_gap_source_check(gap, facts, evidence):
    """Explain what the single read-only source check found for a review gap."""
    text = str(gap)
    lowered = text.lower()
    source_checks = {
        "route": ("route", "gps"),
        "fare": ("fare",),
        "cancellation": ("ride", "app_events", "fare"),
        "arrival": ("gps", "ride", "app_events"),
        "service": ("ride",),
        "profile": ("rider_profile", "driver_profile"),
        "chat": ("chat",),
    }
    selected = next((sources for keyword, sources in source_checks.items()
                     if keyword in lowered), tuple(facts.keys()))
    checked = [name for name in selected if name in facts]
    present = [name for name in checked if facts.get(name)]
    from app.policy.official import factual_values
    values = factual_values(facts, (facts.get("filing") or {}).get("filed_at"))
    field_names = (
        "cancellation_actor", "cancellation_timestamp", "seconds_after_matching",
        "seconds_before_schedule", "seconds_before_schedule_at_match", "days_since_trip",
        "arrival_at", "arrival_button_recorded", "driver_waited_seconds",
        "min_distance_to_pickup_m", "service_tier", "cancellation_fee_cents",
        "quoted_fare_cents", "charged_fare_cents", "actual_distance_km",
        "planned_distance_km", "total_fare_cents",
    )
    targeted = [field for field in field_names
                if field in lowered or field.replace("_", " ") in lowered]
    if not targeted and "decisive fact:" in lowered:
        raw = text.split(":", 1)[1].strip().rstrip(".")
        if raw in values:
            targeted = [raw]
    if not targeted:
        if "scheduled" in lowered:
            targeted = ["scheduled_at", "seconds_before_schedule", "seconds_before_schedule_at_match"]
        elif "arrival" in lowered or "pickup" in lowered:
            targeted = ["arrival_at", "arrival_button_recorded", "driver_waited_seconds", "min_distance_to_pickup_m"]
        elif "fare" in lowered or "charge" in lowered:
            targeted = ["quoted_fare_cents", "charged_fare_cents", "cancellation_fee_cents", "total_fare_cents"]
        elif "route" in lowered or "distance" in lowered:
            targeted = ["actual_distance_km", "planned_distance_km"]
        elif "service" in lowered:
            targeted = ["service_tier"]
    def contains_key(value, key):
        if isinstance(value, dict):
            return key in value or any(contains_key(child, key) for child in value.values())
        if isinstance(value, list):
            return any(contains_key(child, key) for child in value)
        return False
    checks = []
    matching_ids = []
    for field in targeted:
        value_present = values.get(field) is not None
        verified_sources = [item.evidence_id for item in evidence
                            if item.verification.status.value == "verified"
                            and contains_key(item.payload, field)]
        if verified_sources:
            matching_ids.extend(verified_sources)
            checks.append(f"{field}: verified record present")
        elif value_present:
            checks.append(f"{field}: value is assembled, but no verified evidence field supports it")
        else:
            checks.append(f"{field}: absent from the assembled facts and verified evidence")
    if any(token in lowered for token in ("missing", "not established", "unknown", "unrecorded")):
        outcome = "the required value is absent from the available source snapshot"
    elif "disagree" in lowered or "conflict" in lowered or "contradict" in lowered:
        outcome = "conflicting records remain; an advocate summary cannot reconcile them"
    elif any(token in lowered for token in ("policy", "remedy", "boundary", "requires review")):
        outcome = "the available policy does not establish an automatic outcome"
    else:
        outcome = "the source snapshot was checked; no additional record was retrieved"
    detail = "; ".join(checks) if checks else (
        f"checked source sections: {', '.join(checked) or 'no matching source'}; "
        f"{len(present)} section(s) contain records"
    )
    return (f"Gap: {text} Source check: {detail}; {outcome}.", list(dict.fromkeys(matching_ids)))

def review_gaps(category, facts, filed_at, judge, audit, advocates, *, official_policy=False):
    v = factual_values(facts, filed_at)
    gaps = []
    def missing(*keys):
        gaps.extend('Missing decisive fact: '+k for k in keys if v.get(k) is None)
    verified_actors = {str(e.get('event_type','')).split('_')[0]
        for e in facts.get('app_events',[]) if e.get('verification_status')=='verified'
        and e.get('event_type') in ('rider_cancelled','driver_cancelled')}
    header_actor = (facts.get('ride') or {}).get('cancellation_actor')
    if len(verified_actors | ({header_actor} if header_actor else set())) > 1:
        gaps.append('Verified cancellation records disagree about the cancelling party.')
    ride = facts.get('ride') or {}
    fare = facts.get('fare') or {}
    if ride.get('verification_status') != 'verified':
        gaps.append('Service and trip header are not established by verified source records.')
    if v.get('service_tier') not in {'RydeX','RydeXL','RydePET','RydePOOL','RydeFLASH','RydeHIRE','RydeSEND'}:
        gaps.append('Service applicability is unknown or excluded.')
    fee_type = (facts.get('filing') or {}).get('category_details', {}).get('fee_type')
    if category == 'no_show_charge' or (category == 'other_cancellation_fee' and fee_type == 'rider_cancellation'):
        missing('cancellation_actor', 'cancellation_timestamp', 'days_since_trip')
        recorded_cancellation_fee = fare.get('cancellation_fee_cents')
        if (official_policy and recorded_cancellation_fee is not None
                and recorded_cancellation_fee not in (0, 661)):
            gaps.append('Policy boundary: the recorded cancellation amount does not match the published S$6.61 rider charge.')
        if v.get('cancellation_actor') == 'rider':
            missing('seconds_after_matching')
        elif v.get('cancellation_actor') == 'driver':
            missing('arrival_at', 'driver_waited_seconds')
            if not v.get('arrival_button_recorded'):
                gaps.append('Pickup arrival button is not established by a verified event.')
            gps = facts.get('gps') or {}
            if not gps.get('samples') or gps.get('min_distance_to_pickup_m') is None:
                gaps.append('Pickup arrival lacks corroborating GPS records.')
        if v.get('scheduled_at'):
            missing('seconds_before_schedule', 'seconds_after_matching', 'seconds_before_schedule_at_match')
            if v.get('seconds_before_schedule') == 900:
                gaps.append('The exact 15-minute scheduled-trip boundary is ambiguous.')
        if v.get('days_since_trip', 0) < 0:
            gaps.append('Filing precedes the trip.')
    elif category == 'other_cancellation_fee' and fee_type == 'rider_waiting':
        missing('waiting_fare_cents', 'driver_waited_seconds', 'completed_at', 'days_since_trip')
        recorded_waiting_fee = fare.get('waiting_fare_cents')
        if official_policy and recorded_waiting_fee is not None and recorded_waiting_fee not in (0, 500):
            gaps.append('Policy boundary: the recorded waiting amount does not match the published S$5 rider charge.')
        if ride.get('status') not in {'completed', 'complete'}:
            gaps.append('The completed-trip condition for a waiting charge is not established.')
        if fare.get('verification_status') != 'verified':
            gaps.append('Waiting charge is not established by a verified fare record.')
        if v.get('days_since_trip', 0) < 0:
            gaps.append('Filing precedes the trip.')
    if category == 'route_deviation':
        if ride.get('quoted_fare_cents') is None or ride.get('charged_fare_cents') is None:
            gaps.append('Missing quoted or charged fare.')
        if (ride.get('charged_fare_cents') or 0) > (ride.get('quoted_fare_cents') or 0):
            gaps.append('Additional fare requires review: public sources do not define a distance refund formula.')
    if category == 'fare_calculation':
        parts = fare.get('components') or []
        adjustments = fare.get('adjustments') or []
        if ride.get('charged_fare_cents') is None:
            gaps.append('Missing decisive fact: charged_fare_cents.')
        if fare.get('total_fare_cents') is None:
            gaps.append('Missing decisive fact: total_fare_cents.')
        if not parts:
            gaps.append('Missing decisive fact: itemised fare components.')
        if fare.get('verification_status') != 'verified':
            gaps.append('Fare ledger is not established by a verified source record.')
        all_parts = [*parts, *adjustments]
        values = [item.get('amount_cents') for item in all_parts if isinstance(item, dict)]
        if parts and (len(values) != len(all_parts) or sum(values) != fare.get('total_fare_cents')):
            gaps.append('Verified fare components do not reconcile to the ledger total.')
        if (ride.get('charged_fare_cents') is not None and fare.get('total_fare_cents') is not None
                and ride.get('charged_fare_cents') != fare.get('total_fare_cents')):
            gaps.append('Verified payment and fare ledger records disagree.')
    if category == 'other_cancellation_fee':
        if fee_type not in {'rider_cancellation', 'rider_waiting'}:
            gaps.append('Policy boundary: driver payouts and other fee types require a human decision.')
    if category == 'no_show_charge' or (category == 'other_cancellation_fee' and fee_type == 'rider_cancellation'):
        elapsed = v.get('seconds_after_matching')
        wait = v.get('driver_waited_seconds')
        before = v.get('seconds_before_schedule')
        invalid_charge = False
        if v.get('cancellation_actor') == 'rider' and elapsed is not None:
            invalid_charge = elapsed <= 180 if before is None else before > 900 or (before < 900 and v.get('seconds_before_schedule_at_match',900) < 900 and elapsed <= 180)
        elif v.get('cancellation_actor') == 'driver' and wait is not None:
            invalid_charge = wait <= 180
        if judge.get('ruling_type') == 'refund' and not invalid_charge:
            gaps.append('Verified facts do not establish an invalid cancellation charge eligible for waiver.')
        if judge.get('ruling_type') == 'no_action' and invalid_charge and fare.get('cancellation_fee_cents') == 661 and 0 <= v.get('days_since_trip',31) <= 30:
            gaps.append('Proposal does not address the verified free-cancellation window and charged fee.')
    elif category == 'other_cancellation_fee' and fee_type == 'rider_waiting':
        wait = v.get('driver_waited_seconds')
        invalid_wait_charge = wait is not None and wait <= 180
        if judge.get('ruling_type') == 'refund' and not invalid_wait_charge:
            gaps.append('Verified facts do not establish an invalid waiting charge eligible for waiver.')
        if (judge.get('ruling_type') == 'no_action' and invalid_wait_charge
                and fare.get('waiting_fare_cents') == 500 and 0 <= v.get('days_since_trip',31) <= 30):
            gaps.append('Proposal does not address the verified waiting-fee waiver window and charge.')
    action = judge.get('recommended_action') or {}
    money = action.get('amount') or {}
    if judge.get('ruling_type') in ('refund', 'compensation'):
        if category not in {'no_show_charge', 'other_cancellation_fee'} or judge.get('ruling_type') != 'refund':
            gaps.append('No published automated remedy supports this recommendation.')
        else:
            expected_amount = 500 if category == 'other_cancellation_fee' and fee_type == 'rider_waiting' else 661
            recorded_fee = fare.get('waiting_fare_cents') if expected_amount == 500 else fare.get('cancellation_fee_cents')
            if money.get('amount_cents') != expected_amount or recorded_fee != expected_amount:
                gaps.append('Voucher amount or recorded fee differs from the source-backed policy.')
        if action.get('delivery') != 'voucher' or v.get('days_since_trip', 31) > 30:
            gaps.append('Voucher delivery or waiver filing window is not satisfied.')
    if any(a.get('invalid_citation_count', 0) for a in advocates):
        gaps.append('An advocate citation failed semantic validation.')
    if any(
        f.get('classification') != 'consistent'
        and f.get('materiality') in ('material', 'unknown')
        for f in audit
    ):
        gaps.append('An audit finding has material or unknown impact.')
    if not judge.get('decisive_facts'):
        gaps.append('The Judge did not identify supported decisive facts.')
    return gaps


def validate_final_output(category, facts, filed_at, judge, audit, advocates, evidence, policy):
    """Independent code check applied to both rules-first and model proposals."""
    from app.evidence.citation import CitationValidator
    from app.evidence.models import Citation

    gaps = list(review_gaps(category, facts, filed_at, judge, audit, advocates,
                            official_policy=is_source_backed_policy(policy.policy_version)))
    by_id = {item.evidence_id: item for item in evidence}
    for party, advocate in zip(("rider", "driver"), advocates):
        validator = CitationValidator(evidence[0].case_id if evidence else "", by_id)
        for claim in advocate.get("claims", []):
            for citation_data in claim.get("citations", []):
                try:
                    if not isinstance(citation_data, dict):
                        raise ValueError("citation must be an object")
                    citation = Citation(**{key: citation_data[key] for key in
                                           ("evidence_id", "field_path", "observed_value")})
                    valid = validator.validate(citation, party).valid
                except (KeyError, TypeError, ValueError):
                    valid = False
                if not valid or citation_data.get("valid") is not True:
                    gaps.append(f"Final validator found an invalid {party} advocate citation.")
                    break
    if any(rule_id not in policy.rule_ids() for rule_id in judge.get("policy_references", [])):
        gaps.append("Final validator found an inapplicable policy citation.")
    if not judge.get("policy_references"):
        gaps.append("Final validator found no policy citation.")
    for reference in judge.get("evidence_references", []):
        item = by_id.get(reference)
        if item is None or item.verification.status.value != "verified":
            gaps.append("Final validator found an unresolved or unverified evidence reference.")
            break
    for fact in judge.get("decisive_facts", []):
        references = fact.get("evidence_references", []) if isinstance(fact, dict) else []
        if not references or any(ref not in by_id or by_id[ref].verification.status.value != "verified"
                                 for ref in references):
            gaps.append("Final validator found a decisive fact without verified supporting evidence.")
            break
        if judge.get("provider", {}).get("kind") != "rules-engine":
            citations = fact.get("citations", [])
            if not citations:
                gaps.append("Final validator found a decisive fact without field-level citations.")
                break
            validator = CitationValidator(evidence[0].case_id if evidence else "", by_id)
            for citation_data in citations:
                try:
                    if not isinstance(citation_data, dict):
                        raise ValueError("citation must be an object")
                    citation = Citation(**{key: citation_data[key] for key in
                                           ("evidence_id", "field_path", "observed_value")})
                    valid = validator.validate(citation, "reviewer").valid
                except (KeyError, TypeError, ValueError):
                    valid = False
                if not valid or citation.evidence_id not in references:
                    gaps.append("Final validator found an invalid Judge evidence citation.")
                    break
    action = judge.get("recommended_action") or {}
    money = action.get("amount") or {}
    if judge.get("ruling_type") == "no_action" and action.get("amount") is not None:
        gaps.append("Final validator found an amount attached to a no-action ruling.")
    if judge.get("ruling_type") in {"refund", "compensation"}:
        fee_type = (facts.get("filing") or {}).get("category_details", {}).get("fee_type")
        expected_amount = 500 if category == "other_cancellation_fee" and fee_type == "rider_waiting" else 661
        if category not in {"no_show_charge", "other_cancellation_fee"} or judge.get("ruling_type") != "refund" or \
                money.get("amount_cents") != expected_amount or money.get("currency") != "SGD" or \
                action.get("delivery") != "voucher":
            gaps.append("Final validator found a remedy that is not supported by the published policy.")
    return list(dict.fromkeys(gaps))
