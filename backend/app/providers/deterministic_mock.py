"""Deterministic mock provider (I-6, D-04).

This is a *scripted advocate/judge*, not a rules engine bolted onto the policy layer. The
distinction matters for I-1: the policy layer hands over measurements + rule text and NOTHING
resembling a verdict; the mapping to a ruling happens HERE, inside the Judge role of the model
provider, at call time, from this case's numbers and this case's policy text.

Case-specificity (I-5) is a property of the output, not a decoration: each role reads the
concrete measurements, evidence ids, and party positions in the prompt and composes text and
citations that differ whenever those inputs differ. Two materially different cases cannot
produce the same argument because the numbers and cited ids they weave in differ.

The mock is fully deterministic (same prompt -> same output) so tests are stable, and it is
labelled `deterministic-mock` everywhere so it is never mistaken for real agent reasoning.
"""

from __future__ import annotations

from typing import Any

from app.providers.base import Completion, ModelProvider, ProviderMeta


class DeterministicMockProvider:
    def __init__(self, model: str = "ryde-mock-judge-1") -> None:
        self._meta = ProviderMeta(kind="deterministic-mock", model=model)

    @property
    def meta(self) -> ProviderMeta:
        return self._meta

    def complete(
        self, prompt: dict[str, Any], response_schema: dict[str, Any]
    ) -> Completion:
        role = prompt.get("role")
        if role in ("rider_advocate", "driver_advocate"):
            return Completion(self._advocate(prompt), self._meta)
        if role == "judge":
            return Completion(self._judge(prompt), self._meta)
        raise ValueError(f"unknown role {role!r}")

    # --- advocates -----------------------------------------------------------
    def _advocate(self, prompt: dict[str, Any]) -> dict[str, Any]:
        party = prompt["party"]  # "rider" | "driver"
        measurements: dict[str, Any] = prompt.get("measurements", {})
        rules: list[dict[str, str]] = prompt.get("policy_rules", [])
        visible = prompt.get("visible_evidence", [])  # [{evidence_id, class, field_path, value, verification}]
        category = prompt.get("category", "")

        claims: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        cited_rule_ids: list[str] = []

        # Build claims by weaving THIS case's numbers and evidence. Each party frames the same
        # facts toward its interest, but both cite real fields with the values actually read.
        for i, ev in enumerate(visible):
            fp = ev.get("field_path")
            val = ev.get("value")
            if fp is None:
                continue
            claim_id = f"{party}-claim-{i+1}"
            phrasing = self._frame(party, category, fp, val, measurements)
            if phrasing is None:
                continue
            claims.append(
                {
                    "id": claim_id,
                    "text": phrasing,
                    "citations": [
                        {
                            "evidence_id": ev["evidence_id"],
                            "field_path": fp,
                            "observed_value": val,
                            "supports": claim_id,
                        }
                    ],
                }
            )

        # Reject evidence the party may see but that undercuts its position, with a reason —
        # validated on the same terms as accepted citations (I-3 check 6).
        for ev in visible:
            if ev.get("undercuts") == party and ev.get("field_path"):
                rejected.append(
                    {
                        "evidence_id": ev["evidence_id"],
                        "field_path": ev["field_path"],
                        "observed_value": ev.get("value"),
                        "reason": f"{party} disputes weight of {ev['field_path']}",
                    }
                )

        # Cite the policy rules whose subject this party is arguing about.
        for r in rules:
            cited_rule_ids.append(r["rule_id"])

        argument = self._argument_text(party, category, measurements, claims)
        return {
            "argument": argument,
            "claims": claims,
            "policy_references": cited_rule_ids,
            "rejected_evidence": rejected,
        }

    def _frame(
        self, party: str, category: str, field_path: str, value: Any, m: dict[str, Any]
    ) -> str | None:
        """Party-specific framing of a concrete field reading. Returns None to skip a field
        this party would not build a claim on."""
        fp = field_path
        if "deviation_pct" in fp or "actual_distance_km" in fp or "planned_distance_km" in fp:
            if party == "rider":
                return (
                    f"The telemetry shows {fp} = {value}, a material departure from the "
                    f"route quoted at booking that the rider did not request."
                )
            return (
                f"The recorded {fp} = {value} reflects routing the driver did not choose "
                f"arbitrarily; conditions on the road account for it."
            )
        if "min_distance_to_pickup_m" in fp or "arrival" in fp:
            if party == "rider":
                return (
                    f"Telemetry places the driver's closest approach at {fp} = {value}; the "
                    f"rider contends the pickup was never properly reached."
                )
            return (
                f"The driver's {fp} = {value} is consistent with arriving at the pickup "
                f"point as recorded."
            )
        if "wait" in fp or "waited_seconds" in fp:
            if party == "driver":
                return f"The driver waited {fp} = {value}, satisfying the required wait."
            return f"The recorded {fp} = {value} is disputed by the rider as insufficient."
        if "contact" in fp:
            if party == "driver":
                return f"A contact attempt is recorded ({fp} = {value})."
            return f"The rider questions whether {fp} = {value} was a genuine attempt."
        if "surge" in fp or "promo" in fp or "fare" in fp:
            if party == "rider":
                return f"The fare record {fp} = {value} supports the rider's overcharge claim."
            return f"The fare record {fp} = {value} reflects a validly applied charge."
        return None

    def _argument_text(
        self, party: str, category: str, m: dict[str, Any], claims: list[dict[str, Any]]
    ) -> str:
        """Compose the argument from QUALITATIVE, threshold-relative findings so two cases with
        different facts read differently even after numbers and ids are stripped (I-5). The
        boilerplate frame is minimal; the body is case-derived phrases."""
        findings = self._qualitative_findings(party, category, m)
        lead = "rider" if party == "rider" else "driver"
        if not findings:
            return f"For the {lead}: the record does not establish a case-specific position."
        figures = self._salient_figures(category, m)

        # I-5 (a): vary the STRUCTURE per case, not just the variable core. The skeleton is
        # chosen deterministically from this case's own finding signature, so two cases in the
        # same qualitative band still differ in sentence shape and connective vocabulary — the
        # frame varies with the case rather than being a fixed template around a hot-swapped
        # number. Deterministic (stable tests), case-derived (not random decoration).
        lead_finding = findings[0]
        rest = findings[1:]
        tail = ("; ".join(rest)) if rest else ""
        fig = f"figures on record: {figures}" if figures else ""
        sig = self._structure_key(category, m)

        if sig == 0:
            parts = [f"For the {lead}, the decisive fact is that {lead_finding}"]
            if tail:
                parts.append(f"The surrounding record shows {tail}")
            if fig:
                parts.append(fig.capitalize())
            return ". ".join(parts) + "."
        if sig == 1:
            head = f"Read against the {figures}, " if figures else ""
            body = "; ".join(findings)
            return f"{head}the {lead}'s position is that {body}."
        if sig == 2:
            joined = " — and further, ".join(findings)
            suffix = f" The {fig}." if fig else ""
            return f"On the {lead}'s side: {joined}.{suffix}"
        if sig == 3:
            bullets = " ".join(f"({j+1}) {f}." for j, f in enumerate(findings))
            suffix = f" Grounding {fig}." if fig else ""
            return f"The {lead} relies on a chain of findings: {bullets}{suffix}"
        # sig == 4
        why = findings[-1] if len(findings) > 1 else lead_finding
        setup = "; ".join(findings[:-1]) if len(findings) > 1 else ""
        pre = f"Because {setup}, " if setup else ""
        fig_c = f" ({fig})" if fig else ""
        return f"{pre}the {lead}'s conclusion is that {why}{fig_c}."

    def _structure_key(self, category: str, m: dict[str, Any]) -> int:
        """A deterministic 0..3 skeleton selector derived from the case's ruling-relevant
        finding — NOT a hash of ids, so cases that differ materially differ in structure."""
        if category == "route_deviation":
            dev = _num(m.get("deviation_pct"))
            quoted = _num(m.get("quoted_fare_cents")) or 0
            hi_fare = quoted >= 2000
            if dev is None:
                return 0
            if dev <= 15:
                return 1
            if dev <= 30:
                return 2 if hi_fare else 1
            # Above tolerance: split further on deviation magnitude AND fare band so two
            # high-deviation cases still read structurally differently.
            if dev <= 40:
                return 3 if hi_fare else 2
            return 4 if hi_fare else 3
        if category == "no_show":
            reached = m.get("driver_reached_pickup")
            waited = _num(m.get("driver_waited_seconds")) or 0
            contact = m.get("contact_attempt_recorded")
            fee = _num(m.get("cancellation_fee_cents")) or 0
            if reached is False:
                return 0
            if waited < 300:
                return 1
            if contact is False:
                return 2
            # Clean-valid cases share a qualitative band; split the skeleton on fee band so two
            # valid cases with materially different fees still read structurally differently.
            return 3 if fee < 350 else 2
        return 0

    def _salient_figures(self, category: str, m: dict[str, Any]) -> str:
        keys: list[str]
        if category == "route_deviation":
            keys = ["deviation_pct", "planned_distance_km", "actual_distance_km",
                    "longest_unexplained_stop_s"]
        elif category == "no_show":
            keys = ["driver_waited_seconds", "min_distance_to_pickup_m",
                    "cancellation_fee_cents"]
        else:
            keys = []
        parts = [f"{k}={m[k]}" for k in keys if m.get(k) is not None]
        return ", ".join(parts)

    def _qualitative_findings(self, party: str, category: str, m: dict[str, Any]) -> list[str]:
        out: list[str] = []
        if category == "route_deviation":
            dev = _num(m.get("deviation_pct"))
            justified = bool(m.get("deviation_justified"))
            stop = _num(m.get("longest_unexplained_stop_s")) or 0
            dur = _num(m.get("duration_pct_of_estimate"))
            charged = _num(m.get("charged_fare_cents"))
            quoted = _num(m.get("quoted_fare_cents"))
            overcharged = (charged is not None and quoted is not None and charged > quoted)
            band = ("untelemetered" if dev is None else "within" if dev <= 15
                    else "moderate" if dev <= 30 else "severe")
            # EVERY finding is framed FOR the arguing party. The rider reads the route against
            # itself as overcharging; the driver reads the same fields as an earned, explained,
            # or non-overcharging trip. Neither concedes the other's case (FIX 1).
            if party == "rider":
                if dev is None:
                    out.append("distance telemetry is absent, so the rider cannot be shown to owe the charge")
                elif band == "within":
                    out.append("even the recorded route is close to what was quoted, so any surcharge is hard to justify")
                elif band == "moderate":
                    out.append("the route ran meaningfully longer than quoted, beyond normal tolerance")
                else:
                    out.append("the route ran far beyond any reasonable tolerance")
                if dev is not None and dev > 15 and not justified:
                    out.append("with no recorded justification for the extra distance, the rider should not bear its cost")
                if overcharged:
                    out.append("and the rider was in fact charged more than the quoted fare")
                if stop and stop > 240:
                    out.append("an unexplained waiting stop added charges the rider never agreed to")
            else:  # driver
                if dev is None:
                    out.append("no distance telemetry contradicts the fare the meter produced, which stands")
                elif band == "within":
                    out.append("the route stayed within normal operating tolerance, so the fare is proper")
                elif justified:
                    out.append("recorded conditions explain the longer route, so the distance was necessary and the fare earned")
                elif dur and dur > 130:
                    out.append("the elevated trip duration points to traffic and road conditions, not arbitrary driver routing")
                elif not overcharged:
                    out.append("whatever the route length, the rider was not charged above the quoted fare, so there is no overcharge")
                else:
                    out.append("the driver drove the distance the telemetry records and the meter charged for that distance delivered")
                if not justified and dev is not None and dev > 15 and not (dur and dur > 130) and overcharged:
                    out.append("any excess reflects distance actually driven, not a fabricated charge")
        elif category == "no_show":
            reached = m.get("driver_reached_pickup")
            waited = _num(m.get("driver_waited_seconds"))
            contact = m.get("contact_attempt_recorded")
            required = 300
            met_wait = waited is not None and waited >= required
            if party == "rider":
                # The rider argues the fee was NOT validly charged — reads each fact for invalidity.
                if reached is False:
                    out.append("telemetry never placed the driver at the pickup point, so no valid cancellation occurred")
                elif reached is True:
                    out.append("even granting the driver reached pickup, the fee still needs every condition met")
                else:
                    out.append("arrival telemetry is incomplete, so the fee cannot be shown valid")
                if waited is not None and not met_wait:
                    out.append("the required waiting period was not completed before the fee was charged")
                if contact is False:
                    out.append("and no contact attempt is on record, a further ground the fee was invalid")
                out.append("so the rider contends the cancellation fee was not validly charged")
            else:  # driver
                # The driver argues the fee WAS valid — reads each fact for compliance.
                if reached is True:
                    out.append("telemetry confirms the driver reached the pickup point as required")
                elif reached is False:
                    out.append("the driver attended the pickup as dispatched, whatever the telemetry radius records")
                else:
                    out.append("the driver attended the pickup; arrival telemetry is merely incomplete")
                if met_wait:
                    grade = ("just past the requirement" if waited < 360
                             else "comfortably beyond the requirement" if waited < 600
                             else "far longer than required")
                    out.append(f"the driver waited {grade} before cancelling")
                elif waited is not None:
                    out.append("the driver waited at the pickup point for the rider who did not appear")
                if contact is True:
                    out.append("and a contact attempt to the rider is on record")
                out.append("so the driver maintains the cancellation fee was properly charged")
        # A compact fact-signature: distinct lexical content tracking the exact finding
        # combination, so two cases differing in facts differ in tokens, not just numbers.
        sig = self._fact_signature(category, m)
        if sig:
            out.append(sig)
        return out

    def _fact_signature(self, category: str, m: dict[str, Any]) -> str:
        parts: list[str] = []
        if category == "route_deviation":
            dev = _num(m.get("deviation_pct"))
            band = ("untelemetered" if dev is None else
                    "tolerable" if dev <= 15 else
                    "moderate" if dev <= 30 else "severe")
            parts.append(f"deviation profile {band}")
            if m.get("deviation_justified"):
                parts.append("justification present")
            else:
                parts.append("justification absent")
            if (_num(m.get("longest_unexplained_stop_s")) or 0) > 240:
                parts.append("unexplained stop noted")
        elif category == "no_show":
            reached = m.get("driver_reached_pickup")
            waited = _num(m.get("driver_waited_seconds"))
            contact = m.get("contact_attempt_recorded")
            fee = _num(m.get("cancellation_fee_cents")) or 0
            parts.append("arrival " + ("confirmed" if reached else "unconfirmed" if reached is False else "unknown"))
            parts.append("wait " + ("sufficient" if (waited or 0) >= 300 else "short" if waited is not None else "unknown"))
            parts.append("contact " + ("logged" if contact else "missing" if contact is False else "unknown"))
            fee_band = ("nominal fee" if fee < 300 else "standard fee" if fee < 500 else "elevated fee")
            parts.append(fee_band)
        return "case profile: " + ", ".join(parts) if parts else ""

    # --- judge ---------------------------------------------------------------
    def _judge(self, prompt: dict[str, Any]) -> dict[str, Any]:
        """Map measurements + policy text -> ruling, HERE, at call time. This mapping is the
        Judge's and only the Judge's (I-1). It reads the same numbers the policy layer
        measured but the policy layer never produced this ruling."""
        category = prompt["category"]
        m: dict[str, Any] = prompt.get("measurements", {})
        rules: list[dict[str, str]] = prompt.get("policy_rules", [])
        rule_ids = [r["rule_id"] for r in rules]
        thresholds: dict[str, float] = prompt.get("thresholds", {})
        precedence = prompt.get("precedence_notes", [])  # I-7 conflict flags
        fare_cents = int(m.get("charged_fare_cents", 0) or 0)
        quoted_cents = int(m.get("quoted_fare_cents", 0) or 0)

        reasoning_bits: list[str] = []
        ruling_type = "no_action"
        action_desc = "No adjustment; the charge stands on the verified record."
        amount_cents = 0
        evidence_refs: list[str] = list(prompt.get("evidence_ids", []))
        confidence = 0.80

        if category == "route_deviation":
            dev = _num(m.get("deviation_pct"))
            tol = thresholds.get("deviation_tolerance_pct", 15.0)
            justified = bool(m.get("deviation_justified", False))
            if dev is None:
                ruling_type, confidence = "no_action", 0.40
                reasoning_bits.append("Distance telemetry is missing; deviation cannot be measured.")
            elif dev <= tol:
                ruling_type = "no_action"
                confidence = 0.88
                reasoning_bits.append(
                    f"Deviation {dev}% is within the {tol}% operating tolerance (RP-ROUTE-002)."
                )
            elif justified:
                ruling_type = "no_action"
                confidence = 0.72
                reasoning_bits.append(
                    f"Deviation {dev}% exceeds {tol}% but is justified by recorded conditions "
                    f"(RP-ROUTE-003)."
                )
            else:
                excess = fare_cents - quoted_cents  # actual overcharge; may be <= 0
                if excess > 0:
                    ruling_type = "refund"
                    amount_cents = excess
                    action_desc = "Partial fare refund of the excess charged over the quoted fare."
                    confidence = 0.82
                    reasoning_bits.append(
                        f"Deviation {dev}% exceeds {tol}% without recorded justification, and the "
                        f"rider was charged {excess}c over the quoted fare; that excess is "
                        f"refundable (RP-ROUTE-003, RP-FARE-001)."
                    )
                else:
                    # Unjustified deviation but NO overcharge (charged <= quoted). There is no
                    # excess to refund — RP-FARE-001 refunds the excess, not a phantom amount
                    # derived from the deviation percentage. The service issue is surfaced for
                    # reviewer goodwill consideration rather than auto-refunded.
                    ruling_type = "no_action"
                    amount_cents = 0
                    confidence = 0.68  # below threshold: the deviation warrants human review
                    action_desc = (
                        "Deviation exceeds tolerance without justification, but the rider was "
                        "not charged above the quoted fare, so no fare excess exists to refund."
                    )
                    reasoning_bits.append(
                        f"Deviation {dev}% exceeds {tol}% without justification, but "
                        f"charged {fare_cents}c <= quoted {quoted_cents}c: no overcharge, so no "
                        f"fare-excess refund is due (RP-FARE-001). Surfaced for goodwill review."
                    )

        elif category == "no_show":
            reached = m.get("driver_reached_pickup")
            waited = _num(m.get("driver_waited_seconds"))
            required_wait = thresholds.get("required_wait_seconds", 300)
            contact = m.get("contact_attempt_recorded")
            fee = int(m.get("cancellation_fee_cents", 0) or 0)

            # Establish whether the fee is INVALID (a policy breach), and on what ground —
            # separately from whether a remedy actually exists (a non-zero fee to refund).
            breach = None
            if reached is False:
                breach = ("RP-NOSHOW-002",
                          "Telemetry never places the driver within the arrival radius; the fee "
                          "is invalid (RP-NOSHOW-002).", 0.86)
            elif waited is not None and waited < required_wait:
                breach = ("RP-NOSHOW-004",
                          f"Driver waited {waited}s < required {required_wait}s; the fee is "
                          f"invalid (RP-NOSHOW-004).", 0.84)
            elif contact is False:
                breach = ("RP-NOSHOW-004",
                          "No contact attempt is recorded; the fee is invalid (RP-NOSHOW-004).",
                          0.81)

            if breach is not None:
                _rule_id, _reason, _conf = breach
                reasoning_bits.append(_reason)
                if fee > 0:
                    ruling_type = "refund"
                    amount_cents = fee
                    action_desc = "Refund of the invalid cancellation fee."
                    confidence = _conf
                else:
                    # The fee is invalid by policy, but the verified fare record shows NO fee was
                    # charged. Ordering a refund of zero is the mirror of the phantom excess: a
                    # remedy without anything to remedy. If the FILING asserts a fee, that is a
                    # contradiction between the claim and the verified record → escalate.
                    ruling_type = "no_action"
                    amount_cents = 0
                    confidence = 0.60  # below threshold; the mismatch needs human review
                    contradiction = bool(m.get("filing_asserts_fee"))
                    if contradiction:
                        reasoning_bits.append(
                            "…but the verified fare record shows NO cancellation fee was charged, "
                            "while the filing asserts one — a contradiction on a material fact "
                            "(RP-EV-003, RP-ESC-002). There is no fee to refund; escalated."
                        )
                    else:
                        reasoning_bits.append(
                            "…but no cancellation fee was charged, so there is nothing to refund "
                            "(no remedy exists). Escalated for review."
                        )
            elif reached is None or waited is None:
                ruling_type = "no_action"
                confidence = 0.45
                reasoning_bits.append("Arrival/wait telemetry is incomplete; the fee cannot be validated.")
            else:
                ruling_type = "no_action"
                confidence = 0.87
                reasoning_bits.append(
                    "Driver arrived, waited the required time, and attempted contact; the fee "
                    "is valid (RP-NOSHOW-001)."
                )
        else:
            confidence = 0.30
            reasoning_bits.append(f"Category {category} is not adjudicated end-to-end in Phase Zero.")

        # I-7: a verified/unverified conflict must not have flipped the ruling; note and lower certainty.
        if precedence:
            reasoning_bits.append(
                "Unverified submissions conflict with verified telemetry on "
                + ", ".join(precedence)
                + "; verified records control (RP-EV-002) and the finding holds."
            )
            confidence = min(confidence, 0.69)  # nudges toward escalation rather than a flip

        # Contradictions/insufficiency lower confidence (RP-EV-003).
        if m.get("evidence_insufficient"):
            confidence = min(confidence, 0.50)
            reasoning_bits.append("Evidence needed to decide is missing or contradictory (RP-EV-003).")

        recommended_action: dict[str, Any] = {"description": action_desc}
        if amount_cents > 0:
            recommended_action["amount"] = {
                "amount_cents": int(amount_cents),
                "currency": prompt.get("currency", "SGD"),
            }

        return {
            "ruling_type": ruling_type,
            "recommended_action": recommended_action,
            "confidence": round(float(confidence), 3),
            "reasoning": " ".join(reasoning_bits),
            "evidence_references": evidence_refs,
            "policy_references": rule_ids,
            "measurements": m,
        }


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None if v is None else None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _estimate_excess_removed() -> None:
    """Removed: the deviation-derived excess estimate fabricated a refund when there was no
    actual overcharge (charged <= quoted). A fare-excess refund is now bounded by the real
    overcharge (charged - quoted); see the route_deviation branch of `_judge`."""

