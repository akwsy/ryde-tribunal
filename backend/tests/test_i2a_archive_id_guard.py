"""I-2a — an archive read must refuse a live identifier.

The near-miss: an ambiguous `get_case` was read as the live dispute by the backend and
implemented as an archived case by the database specialist, which would have handed the case
under adjudication an outcome-bearing archive record. The contract removed `get_case`; the
archive path is now `get_archive_case`, which RAISES on a live `DSP-*` / `RIDE-*` id.

Since the database specialist's reader does not exist yet, these assertions run against the
backend's OWN guard (`assert_archive_id`) and its fixture reader — the guard must exist on our
side too, not only theirs.
"""

from __future__ import annotations

import pytest

from app.persistence.reader import LiveIdRejected, assert_archive_id
from tests.fixtures.cases import add_archive, route_case
from tests.fixtures.reader import FixtureReader


def test_assert_archive_id_raises_on_live_dsp_id():
    with pytest.raises(LiveIdRejected):
        assert_archive_id("DSP-000045")


def test_assert_archive_id_raises_on_live_ride_id():
    with pytest.raises(LiveIdRejected):
        assert_archive_id("RIDE-000123")


def test_assert_archive_id_accepts_archive_ids():
    assert assert_archive_id("DSP-ARCH-000017") == "DSP-ARCH-000017"
    assert assert_archive_id("RIDE-ARCH-000009") == "RIDE-ARCH-000009"


def test_assert_archive_id_rejects_garbage():
    with pytest.raises(LiveIdRejected):
        assert_archive_id("not-an-id")


def test_get_archive_case_raises_on_live_id():
    reader = FixtureReader()
    add_archive(reader, "route_deviation")
    with pytest.raises(LiveIdRejected):
        reader.get_archive_case("DSP-000045")  # a live case id must never resolve


def test_get_archive_case_returns_archived_case():
    reader = FixtureReader()
    add_archive(reader, "route_deviation")
    got = reader.get_archive_case("DSP-ARCH-000017")
    assert got is not None and got.archive_case_id == "DSP-ARCH-000017"


def test_reader_has_no_live_case_accessor():
    # The live case belongs to the tribunal schema; the reader must not expose get_case.
    reader = FixtureReader()
    assert not hasattr(reader, "get_case")


def test_adjudication_never_routes_live_id_to_archive(client, reader, store, rid, monkeypatch):
    """Wrap the reader's archive accessors to record every id they are called with, run a full
    adjudication, and assert every archive call received an archive-namespaced id — never the
    live DSP id under adjudication."""
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
    for cid in seen_ids:
        assert not cid.startswith("DSP-0") and not cid.startswith("RIDE-0"), (
            f"a live id {cid!r} was routed to an archive accessor"
        )
