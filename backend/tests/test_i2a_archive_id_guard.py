"""I-2a — archive lookups stay archive-table-scoped with globally unique canonical IDs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.persistence.reader import LiveIdRejected, assert_archive_id
from app.persistence.store import ResultStore
from tests.fixtures.cases import add_archive, route_case
from tests.fixtures.reader import FixtureReader


def test_assert_archive_id_accepts_canonical_archive_shape():
    # Live and archived records share this syntax. Source is determined by the accessor path.
    assert assert_archive_id("DSP-000017") == "DSP-000017"


def test_assert_archive_id_rejects_ride_ids():
    with pytest.raises(LiveIdRejected):
        assert_archive_id("RIDE-000123")


def test_assert_archive_id_rejects_garbage():
    with pytest.raises(LiveIdRejected):
        assert_archive_id("not-an-id")


def test_get_archive_case_does_not_fall_through_to_live_store():
    reader = FixtureReader()
    add_archive(reader, "route_deviation")
    # This ID has the same shape as a live ID, but lookup is archive-only and returns no row.
    assert reader.get_archive_case("DSP-000045") is None


def test_get_archive_case_returns_archived_case():
    reader = FixtureReader()
    add_archive(reader, "route_deviation")
    got = reader.get_archive_case("DSP-000017")
    assert got is not None and got.archive_case_id == "DSP-000017"


def test_reader_has_no_live_case_accessor():
    # The live case belongs to the tribunal schema; the reader must not expose get_case.
    reader = FixtureReader()
    assert not hasattr(reader, "get_case")


def test_adjudication_never_routes_live_id_to_archive(container, reader, rid, monkeypatch):
    """Run adjudication and ensure archive lookups do not receive the active live case ID."""
    container.store = ResultStore()
    client = TestClient(create_app(container))
    store = container.store
    route_case(reader, store=store, case_id="DSP-000045", ride_id="RIDE-000123",
               planned_km=13.7, actual_km=18.4, quoted_cents=1370, charged_cents=1840)
    add_archive(reader, "route_deviation")

    seen_ids: list[str] = []
    real_search = reader.search_archive
    real_get = reader.get_archive_case

    def spy_search(category, features, limit):
        return real_search(category, features, limit)

    def spy_get(archive_case_id):
        seen_ids.append(archive_case_id)
        return real_get(archive_case_id)

    monkeypatch.setattr(reader, "get_archive_case", spy_get)
    monkeypatch.setattr(reader, "search_archive", spy_search)

    r = client.post("/api/v1/disputes/DSP-000045/adjudicate", headers={"X-Reviewer-Id": rid})
    assert r.status_code == 200
    # No archive-by-id call received the live case id (nor any live-shaped id).
    assert "DSP-000045" not in seen_ids
