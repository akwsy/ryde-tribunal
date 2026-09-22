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
        body = " ".join(findings)
        # Cite the concrete figures this position rests on — an advocate argues from the
        # actual measured values, and these anchor the argument to THIS case (I-5).
        figures = self._salient_figures(category, m)
        fig_clause = f" Key figures: {figures}." if figures else ""
        return f"For the {lead}: {body}.{fig_clause}"

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
            if dev is None:
                out.append("distance telemetry is absent so the route cannot be characterised")
            elif dev <= 15:
                out.append("the route stayed within normal operating tolerance")
            elif dev <= 30:
                out.append("the route ran moderately beyond tolerance")
            else:
                out.append("the route ran far beyond any reasonable tolerance")
            if dev is not None:
                excess_grade = ("a slight excess" if dev <= 20 else
                                "a pronounced excess" if dev <= 40 else
                                "an extreme excess")
                out.append(f"the extra distance represents {excess_grade} over what was quoted")
            if party == "rider":
                if dev is not None and dev > 15 and not justified:
                    out.append("with no recorded justification for the extra distance the rider was overcharged")
                if stop and stop > 240:
                    out.append("an unexplained waiting stop added charges the rider never agreed to")
            else:
                if justified:
                    out.append("recorded conditions explain the detour so the fare was earned")
                elif dur and dur > 130:
                    out.append("elevated trip duration points to traffic rather than driver routing")
                else:
                    out.append("the driver delivered the trip the meter reflects")
        elif category == "no_show":
            reached = m.get("driver_reached_pickup")
            waited = _num(m.get("driver_waited_seconds"))
            contact = m.get("contact_attempt_recorded")
            if reached is False:
                out.append("telemetry never placed the driver at the pickup point")
            elif reached is True:
                out.append("telemetry confirms the driver reached the pickup point")
            else:
                out.append("arrival telemetry is incomplete")
            if waited is not None:
                if waited < 300:
                    grade = ("barely began waiting" if waited < 60
                             else "waited only briefly" if waited < 180
                             else "waited but stopped short of the requirement")
                    out.append(f"the required waiting period was not completed — the driver {grade}")
                else:
                    grade = ("waited just past the requirement" if waited < 360
                             else "waited comfortably beyond the requirement" if waited < 600
                             else "waited far longer than required")
                    out.append(f"the full waiting period elapsed — the driver {grade}")
            if contact is False:
                out.append("no contact attempt is on record")
            elif contact is True:
                out.append("a contact attempt is on record")
            if party == "rider":
                out.append("so the rider contends the cancellation fee was invalid")
            else:
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
            excess = max(fare_cents - quoted_cents, 0)
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
                ruling_type = "refund"
                amount_cents = excess if excess > 0 else _estimate_excess(m)
                action_desc = "Partial fare refund of the excess attributable to the extra distance."
                confidence = 0.82
                reasoning_bits.append(
                    f"Deviation {dev}% exceeds {tol}% without recorded justification; the rider "
                    f"is entitled to the excess over the quoted fare (RP-ROUTE-003, RP-FARE-001)."
                )

        elif category == "no_show":
            reached = m.get("driver_reached_pickup")
            waited = _num(m.get("driver_waited_seconds"))
            required_wait = thresholds.get("required_wait_seconds", 300)
            contact = m.get("contact_attempt_recorded")
            fee = int(m.get("cancellation_fee_cents", 0) or 0)
            if reached is False:
                ruling_type = "refund"
                amount_cents = fee
                action_desc = "Full refund of the cancellation fee; telemetry never placed the driver at pickup."
                confidence = 0.86
                reasoning_bits.append(
                    "Telemetry never places the driver within the arrival radius; the fee is "
                    "invalid (RP-NOSHOW-002)."
                )
            elif waited is not None and waited < required_wait:
                ruling_type = "refund"
                amount_cents = fee
                action_desc = "Refund of the cancellation fee; required wait not met."
                confidence = 0.84
                reasoning_bits.append(
                    f"Driver waited {waited}s < required {required_wait}s; the fee is invalid "
                    f"(RP-NOSHOW-004)."
                )
            elif contact is False:
                ruling_type = "refund"
                amount_cents = fee
                action_desc = "Refund of the cancellation fee; no recorded contact attempt."
                confidence = 0.81
                reasoning_bits.append("No contact attempt is recorded; the fee is invalid (RP-NOSHOW-004).")
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


def _estimate_excess(m: dict[str, Any]) -> int:
    """When no explicit excess is present, estimate from deviation over quoted fare — a
    measurement-derived figure, still the Judge's computation, capped by the caller (D-11)."""
    dev = _num(m.get("deviation_pct")) or 0.0
    quoted = int(m.get("quoted_fare_cents", 0) or 0)
    tol = 15.0
    over = max(dev - tol, 0.0) / 100.0
    return int(round(quoted * over))
