from __future__ import annotations

from contextlib import contextmanager

from app.persistence.postgres_store import PostgresResultStore


def test_evidence_ids_use_shared_ride_data_sequence(monkeypatch):
    executed = []

    class Session:
        def execute(self, statement):
            executed.append(str(statement))

            class Result:
                @staticmethod
                def scalar_one():
                    return 123456

            return Result()

    @contextmanager
    def begin():
        yield Session()

    class SessionFactory:
        def begin(self):
            return begin()

    store = PostgresResultStore("postgresql://unused")
    monkeypatch.setattr(store, "_sessions", SessionFactory())
    try:
        assert store.allocate_evidence_id() == "EV-123456"
    finally:
        store._engine.dispose()

    assert executed == ["SELECT nextval('ride_data.imported_evidence_id_seq')"]
