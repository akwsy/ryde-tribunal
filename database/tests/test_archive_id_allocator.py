from __future__ import annotations

from archive_importer.persist import _case_identifier, _identifier


class _SequenceResult:
    def fetchone(self):
        return {"generated_id": 100123}


class _SequenceConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> _SequenceResult:
        self.calls.append((query, params))
        return _SequenceResult()


def test_archive_snapshot_allocator_uses_shared_entity_sequences() -> None:
    conn = _SequenceConnection()
    assert _identifier(conn, "ride_data.imported_rider_id_seq", "USR", "R") == "USR-R-100123"
    assert _identifier(conn, "ride_data.imported_driver_id_seq", "USR", "D") == "USR-D-100123"
    assert _identifier(conn, "ride_data.imported_ride_id_seq", "RIDE") == "RIDE-100123"
    assert _identifier(conn, "ride_data.imported_evidence_id_seq", "EV") == "EV-100123"
    assert [params for _, params in conn.calls] == [
        ("ride_data.imported_rider_id_seq",),
        ("ride_data.imported_driver_id_seq",),
        ("ride_data.imported_ride_id_seq",),
        ("ride_data.imported_evidence_id_seq",),
    ]


def test_archive_case_allocator_uses_shared_live_case_sequence() -> None:
    conn = _SequenceConnection()
    assert _case_identifier(conn) == "DSP-100123"
    assert conn.calls == [("SELECT nextval('tribunal.case_id_seq') AS generated_id", ())]
