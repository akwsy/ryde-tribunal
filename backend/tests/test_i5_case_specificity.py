"""I-5 — two different cases must not yield the same argument.

>=6 materially different cases per category. On normalized advocate argument text (lowercased,
ids and numbers stripped) assert pairwise similarity below a declared ceiling, AND that each
argument cites a distinct evidence-id set. Identical output across two cases in a category is a
hard failure.

Two independent guarantees (I-5 options (a) and (b), per the lead's review):

  (a) The deterministic mock varies argument STRUCTURE per case — one of five sentence
      skeletons is selected from the case's own ruling-relevant finding
      (`DeterministicMockProvider._structure_key`), so two cases in the same qualitative band
      still differ in sentence shape and connectives, not merely in a hot-swapped number.

  (b) The BINDING guarantee is structural and text-independent: `_assert_structural_distinctness`
      requires the cited-evidence sets to be pairwise distinct with mean Jaccard DISTANCE ≥ 0.5.
      That catches an implementation that varies wording while reasoning over the same evidence
      — exactly the failure text similarity cannot see.

The text-similarity ceiling below is a SECONDARY smell test, set on independent grounds at
**0.95**: two arguments above 0.95 normalized-token Jaccard are effectively the same template
differing only in stripped ids, which is what this cap is meant to catch. It is deliberately
NOT fitted to the current numbers (measured maxima ~0.82 no_show, ~0.90 route) — a ceiling
chosen to just clear the current numbers is the weak guarantee the review flagged, so the real
teeth are the never-identical check and the structural distance floor, and this cap only rules
out near-duplicate templates. Normalization strips evidence IDS but RETAINS numeric magnitudes,
because a measured value (34% vs 80% deviation) is legitimate case-specific content.
"""

from __future__ import annotations

import re

from tests.fixtures.cases import noshow_case, route_case
from tests.conftest import make_settings
from app.api.container import build_container
from app.api.app import create_app
from fastapi.testclient import TestClient
from tests.fixtures.reader import FixtureReader

SIMILARITY_CEILING = 0.95


def _normalize(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"\b[a-z]+-[a-z0-9]+\b", " ", text)   # strip ids like ev-r000-1
    text = re.sub(r"[^a-z0-9\s]", " ", text)              # keep alphanumerics incl. numbers
    return {t for t in text.split() if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _build() -> tuple[TestClient, object]:
    reader = FixtureReader()
    container = build_container(reader=reader, settings=make_settings())
    return reader, container


def _adjudicate(client, case_id):
    return client.post(f"/api/v1/disputes/{case_id}/adjudicate",
                       headers={"X-Reviewer-Id": "REV-1"}).json()


def _ev_set(body, side) -> frozenset:
    return frozenset(
        c["citations"][0]["evidence_id"]
        for c in body["advocates"][side]["claims"]
        if c["citations"]
    )


def _assert_case_specific(bodies, side):
    args = [b["advocates"][side]["argument"] for b in bodies]
    norms = [_normalize(a) for a in args]
    ev_sets = [_ev_set(b, side) for b in bodies]
    for i in range(len(bodies)):
        for k in range(i + 1, len(bodies)):
            # Hard: never byte-identical.
            assert args[i] != args[k], f"{side} arguments identical for cases {i},{k}"
            # (b) text-similarity ceiling — a weak proxy, kept as one signal.
            sim = _jaccard(norms[i], norms[k])
            assert sim < SIMILARITY_CEILING, (
                f"{side} arguments too similar ({sim:.2f}) for cases {i},{k}"
            )
            # Hard: distinct cited-evidence set.
            assert ev_sets[i] != ev_sets[k], (
                f"{side} cited identical evidence set for cases {i},{k}"
            )


def _assert_structural_distinctness(bodies, side):
    """I-5 option (b): a signal that does NOT depend on text similarity at all — the
    cited-evidence sets must be pairwise distinct with mean Jaccard DISTANCE above a floor.
    This catches an implementation that varies wording but reasons over the same evidence."""
    ev_sets = [_ev_set(b, side) for b in bodies]
    dists = []
    for i in range(len(bodies)):
        for k in range(i + 1, len(bodies)):
            union = ev_sets[i] | ev_sets[k]
            inter = ev_sets[i] & ev_sets[k]
            dist = 1.0 - (len(inter) / len(union) if union else 1.0)
            dists.append(dist)
    mean_dist = sum(dists) / len(dists)
    # Every pair cites a distinct set (distance > 0), and on average the sets are well apart.
    assert min(dists) > 0.0, f"{side}: some case pair cites an identical evidence set"
    assert mean_dist >= 0.5, f"{side}: mean cited-evidence Jaccard distance {mean_dist:.2f} too low"


def test_route_deviation_cases_are_specific():
    reader, container = _build()
    client = TestClient(create_app(container))
    specs = [
        (13.7, 18.4, 1370, 1840),
        (8.0, 20.0, 900, 2200),
        (25.0, 26.0, 2500, 2600),
        (5.0, 9.0, 600, 1080),
        (12.3, 14.0, 1230, 1400),
        (30.0, 45.0, 3000, 4500),
    ]
    for i, (p, a, q, c) in enumerate(specs):
        route_case(reader, store=container.store,
                   case_id=f"DSP-R{i:03d}", ride_id=f"RIDE-R{i:03d}",
                   planned_km=p, actual_km=a, quoted_cents=q, charged_cents=c)
    bodies = [_adjudicate(client, f"DSP-R{i:03d}") for i in range(len(specs))]
    _assert_case_specific(bodies, "rider")
    _assert_case_specific(bodies, "driver")
    _assert_structural_distinctness(bodies, "rider")
    _assert_structural_distinctness(bodies, "driver")


def test_no_show_cases_are_specific():
    reader, container = _build()
    client = TestClient(create_app(container))
    specs = [
        (True, 320, True, 400),    # clean: arrived, waited, contacted -> fee valid
        (False, 0, False, 500),    # never arrived -> fee invalid
        (True, 120, True, 300),    # arrived but wait too short -> fee invalid
        (True, 400, False, 350),   # arrived, waited, but no contact -> fee invalid
        (False, 60, True, 600),    # never arrived (brief wait) -> fee invalid
        (True, 305, True, 250),    # clean but marginal wait, nominal fee -> fee valid
    ]
    for i, (reached, waited, contact, fee) in enumerate(specs):
        noshow_case(reader, store=container.store,
                    case_id=f"DSP-N{i:03d}", ride_id=f"RIDE-N{i:03d}",
                    reached_pickup=reached, waited_seconds=waited,
                    contact_attempt=contact, fee_cents=fee)
    bodies = [_adjudicate(client, f"DSP-N{i:03d}") for i in range(len(specs))]
    _assert_case_specific(bodies, "rider")
    _assert_case_specific(bodies, "driver")
    _assert_structural_distinctness(bodies, "rider")
    _assert_structural_distinctness(bodies, "driver")
