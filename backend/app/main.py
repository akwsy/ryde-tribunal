"""ASGI entrypoint: `uvicorn app.main:app`.

The DB specialist's Postgres-backed reader does not exist yet (Phase Zero integration is a
later lead-agent task). Until it lands, the server wires a `PendingDatabaseReader` that raises
`DatabaseUnavailable` on every accessor — so a running server correctly returns
`database_unavailable` and never a fabricated ruling. Tests inject a fixture reader instead;
integration swaps in the real reader at the same seam (`app.api.container.build_container`).
"""

from __future__ import annotations

from typing import Any

from app.api.app import create_app
from app.api.container import build_container
from app.persistence.reader import DatabaseReader, DatabaseUnavailable


class PendingDatabaseReader:
    """Stand-in until the database specialist's reader is integrated. Every accessor signals
    the datastore is not wired, which the API maps to `database_unavailable`."""

    def _unavailable(self, *_a: Any, **_k: Any):
        raise DatabaseUnavailable(
            "database reader not yet integrated (Phase Zero: DB specialist owns the reader)"
        )

    get_ride = _unavailable
    get_route = _unavailable
    get_gps_samples = _unavailable
    get_chat_log = _unavailable
    get_fare_breakdown = _unavailable
    get_profile = _unavailable
    get_case = _unavailable
    search_archive = _unavailable
    persist_model_work = _unavailable


def build() :
    container = build_container(reader=PendingDatabaseReader())
    return create_app(container)


app = build()
