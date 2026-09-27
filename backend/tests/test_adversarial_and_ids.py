"""Adversarial advocacy (FIX 1) + evidence-id shape (FIX 3).

FIX 1: on the SAME case the two advocates must argue OPPOSED positions — not share prose. The
structural I-5 test passes on distinct evidence sets alone, so this adds the class of check that
was missing: near-identity of argument text is a failure, and each advocate's stance must be
directionally consistent with its own party.

FIX 3: every emitted evidence id (in evidence_references and in every citation) matches
^EV-\\d{6}$ — one id shape, no suffix.
"""

from __future__ import annotations

import re

from tests.fixtures.cases import route_case, noshow_case

EV_RE = re.compile(r"^EV-\d{6}$")

# Words a party would only say if arguing AGAINST itself.
_RIDER_ONLY = ("overcharg", "should not bear", "not validly charged", "invalid", "never agreed")
_DRIVER_ONLY = ("no overcharge", "fare is proper", "fare earned", "properly charged",
                "necessary", "delivered", "not charged above")


def _adjudicate(client, case_id, rid):
    return client.post(f"/api/v1/disputes/{case_id}/adjudicate",
                       headers={"X-Reviewer-Id": rid}).json()


def _norm(text: str) -> set[str]:
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return {t for t in text.split() if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a | b) else 1.0


def _assert_opposed(body):
    rider = body["advocates"]["rider"]["argument"]
    driver = body["advocates"]["driver"]["argument"]
    # Not near-identical prose.
    assert rider != driver
    sim = _jaccard(_norm(rider), _norm(driver))
    assert sim < 0.80, f"advocate arguments too similar ({sim:.2f}) — driver echoes rider"
    # Directional stance: the driver argument must NOT contain rider-only concessions.
    dlow = driver.lower()
    for phrase in ("should not bear", "the rider was overcharged", "not validly charged"):
        assert phrase not in dlow, f"driver conceded the rider's case: '{phrase}'"
    # And each advocate voices its own side at least once.
    assert any(p in rider.lower() for p in _RIDER_ONLY), "rider does not argue the rider's case"
    assert any(p in dlow for p in _DRIVER_ONLY), "driver does not argue the driver's case"


def test_route_deviation_advocates_are_opposed(client, reader, store, rid):
    # A real overcharge: charged > quoted, deviation well over tolerance.
    route_case(reader, store=store, case_id="DSP-000045", ride_id="RIDE-000123",
               planned_km=10.0, actual_km=20.0, quoted_cents=1000, charged_cents=1600)
    body = _adjudicate(client, "DSP-000045", rid)
    _assert_opposed(body)


def test_no_show_charge_advocates_are_opposed(client, reader, store, rid):
    noshow_case(reader, store=store, case_id="DSP-000046", ride_id="RIDE-000200",
                reached_pickup=True, waited_seconds=120, contact_attempt=True, fee_cents=400)
    body = _adjudicate(client, "DSP-000046", rid)
    _assert_opposed(body)


def _all_emitted_ids(body) -> list[str]:
    ids = list(body["judge"]["evidence_references"])
    for side in ("rider", "driver"):
        for claim in body["advocates"][side]["claims"]:
            for cit in claim["citations"]:
                ids.append(cit["evidence_id"])
    return ids


def test_every_emitted_evidence_id_matches_pattern(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000045", ride_id="RIDE-000123",
               planned_km=10.0, actual_km=15.0, quoted_cents=1000, charged_cents=1500)
    body = _adjudicate(client, "DSP-000045", rid)
    ids = _all_emitted_ids(body)
    assert ids, "no evidence ids emitted"
    for eid in ids:
        assert EV_RE.match(eid), f"evidence id {eid!r} does not match ^EV-\\d{{6}}$"


def test_every_citation_carries_valid_flag(client, reader, store, rid):
    route_case(reader, store=store, case_id="DSP-000045", ride_id="RIDE-000123",
               planned_km=10.0, actual_km=15.0, quoted_cents=1000, charged_cents=1500)
    body = _adjudicate(client, "DSP-000045", rid)
    for side in ("rider", "driver"):
        for claim in body["advocates"][side]["claims"]:
            for cit in claim["citations"]:
                assert "valid" in cit and isinstance(cit["valid"], bool), \
                    "citation missing required boolean 'valid'"
