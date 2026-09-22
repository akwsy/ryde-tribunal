"""Generate handoff artifacts (brief §9): the OpenAPI document (for the lead agent to diff
against shared/openapi.yaml) and one sample CaseResult per Phase-Zero category.

Run: `uv run python -m tools.gen_handoff` from backend/. Writes into backend/handoff/.
Uses the deterministic_mock provider + fixture reader, so it is fully offline.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.container import build_container
from tests.conftest import make_settings  # type: ignore
from tests.fixtures.cases import noshow_case, route_case  # type: ignore
from tests.fixtures.reader import FixtureReader  # type: ignore

OUT = Path(__file__).resolve().parents[1] / "handoff"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    reader = FixtureReader()
    container = build_container(reader=reader, settings=make_settings())
    route_case(reader, store=container.store, case_id="DSP-000045", ride_id="RIDE-000123",
               planned_km=13.7, actual_km=18.4, quoted_cents=1370, charged_cents=1840)
    noshow_case(reader, store=container.store, case_id="DSP-000046", ride_id="RIDE-000200",
                reached_pickup=False, waited_seconds=0, contact_attempt=False, fee_cents=400)
    app = create_app(container)
    client = TestClient(app)

    # OpenAPI
    (OUT / "openapi.json").write_text(json.dumps(app.openapi(), indent=2, sort_keys=True))

    # Sample CaseResult per category
    for cid, name in (("DSP-000045", "sample_case_result_route_deviation.json"),
                      ("DSP-000046", "sample_case_result_no_show.json")):
        body = client.post(f"/api/v1/disputes/{cid}/adjudicate",
                           headers={"X-Reviewer-Id": "REV-001"}).json()
        (OUT / name).write_text(json.dumps(body, indent=2))
    print(f"wrote handoff artifacts to {OUT}")


if __name__ == "__main__":
    main()
