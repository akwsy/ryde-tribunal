"""I-5 — two different cases must not yield the same argument.

>=6 materially different cases per category. On normalized advocate argument text (lowercased,
ids and numbers stripped) assert pairwise similarity below a declared ceiling, AND that each
argument cites a distinct evidence-id set. Identical output across two cases in a category is a
hard failure.

Declared similarity ceiling: 0.90 (Jaccard over normalized tokens). Rationale in
backend/ASSUMPTIONS.md (A-4). Normalization strips evidence IDS (which are trivially unique
per ride and would otherwise mask a template) but RETAINS numeric magnitudes, because a
measured value (34% vs 80% deviation, a 250c vs 600c fee) is legitimate case-specific content,
not boilerplate — an argument that cites the actual figure is reasoning about the case, and
two cases with different figures are genuinely different. The ceiling then catches arguments
that are identical templates differing only in the stripped ids, while tolerating the shared
domain vocabulary two same-family cases legitimately use. The hard checks (arguments never
byte-identical; each cites a DISTINCT evidence-id set) are the primary I-5 teeth.
"""

from __future__ import annotations

import re

from tests.fixtures.cases import noshow_case, route_case
from tests.conftest import make_settings
from app.api.container import build_container
from app.api.app import create_app
from fastapi.testclient import TestClient
from tests.fixtures.reader import FixtureReader

SIMILARITY_CEILING = 0.90


def _normalize(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"\b[a-z]+-[a-z0-9]+\b", " ", text)   # strip ids like ev-r000-1
    text = re.sub(r"[^a-z0-9\s]", " ", text)              # keep alphanumerics incl. numbers
    return {t for t in text.split() if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _run(reader) -> TestClient:
    container = build_container(reader=reader, settings=make_settings())
    return TestClient(create_app(container))


def _adjudicate(client, case_id):
    return client.post(f"/api/v1/disputes/{case_id}/adjudicate",
                       headers={"X-Reviewer-Id": "REV-1"}).json()


def _assert_case_specific(bodies, side):
    args = [b["advocates"][side]["argument"] for b in bodies]
    norms = [_normalize(a) for a in args]
    ev_sets = [
        frozenset(
            c["citations"][0]["evidence_id"]
            for c in b["advocates"][side]["claims"]
            if c["citations"]
        )
        for b in bodies
    ]
    for i in range(len(bodies)):
        for k in range(i + 1, len(bodies)):
            assert args[i] != args[k], f"{side} arguments identical for cases {i},{k}"
            sim = _jaccard(norms[i], norms[k])
            assert sim < SIMILARITY_CEILING, (
                f"{side} arguments too similar ({sim:.2f}) for cases {i},{k}"
            )
            assert ev_sets[i] != ev_sets[k], (
                f"{side} cited identical evidence set for cases {i},{k}"
            )


def test_route_deviation_cases_are_specific():
    reader = FixtureReader()
    specs = [
        (13.7, 18.4, 1370, 1840),
        (8.0, 20.0, 900, 2200),
        (25.0, 26.0, 2500, 2600),
        (5.0, 9.0, 600, 1080),
        (12.3, 14.0, 1230, 1400),
        (30.0, 45.0, 3000, 4500),
    ]
    for i, (p, a, q, c) in enumerate(specs):
        route_case(reader, case_id=f"DSP-R{i:03d}", ride_id=f"RIDE-R{i:03d}",
                   planned_km=p, actual_km=a, quoted_cents=q, charged_cents=c)
    client = _run(reader)
    bodies = [_adjudicate(client, f"DSP-R{i:03d}") for i in range(len(specs))]
    _assert_case_specific(bodies, "rider")
    _assert_case_specific(bodies, "driver")


def test_no_show_cases_are_specific():
    reader = FixtureReader()
    specs = [
        (True, 320, True, 400),    # clean: arrived, waited, contacted -> fee valid
        (False, 0, False, 500),    # never arrived -> fee invalid
        (True, 120, True, 300),    # arrived but wait too short -> fee invalid
        (True, 400, False, 350),   # arrived, waited, but no contact -> fee invalid
        (False, 60, True, 600),    # never arrived (brief wait) -> fee invalid
        (True, 305, True, 250),    # clean but marginal wait, nominal fee -> fee valid
    ]
    for i, (reached, waited, contact, fee) in enumerate(specs):
        noshow_case(reader, case_id=f"DSP-N{i:03d}", ride_id=f"RIDE-N{i:03d}",
                    reached_pickup=reached, waited_seconds=waited,
                    contact_attempt=contact, fee_cents=fee)
    client = _run(reader)
    bodies = [_adjudicate(client, f"DSP-N{i:03d}") for i in range(len(specs))]
    _assert_case_specific(bodies, "rider")
    _assert_case_specific(bodies, "driver")
