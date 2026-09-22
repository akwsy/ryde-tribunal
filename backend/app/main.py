"""ASGI entrypoint: `uvicorn app.main:app`.

Reader selection is by config (`app.api.container.build_container(reader=...)`):
`read_database_dsn` set → `PostgresReader` over the database package's accessors (read-only
role); empty → `PendingDatabaseReader`, whose every accessor raises `DatabaseUnavailable`, so a
server with no database configured correctly returns `database_unavailable` and never a
fabricated ruling. Tests inject a fixture reader at the same seam.
"""

from __future__ import annotations

from typing import Any

from app.api.app import create_app
from app.api.container import build_container
from app.persistence.reader import DatabaseReader, DatabaseUnavailable
from app.settings import get_settings


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
    search_archive = _unavailable
    get_archive_case = _unavailable


def build():
    settings = get_settings()
    if settings.read_database_dsn:
        from app.persistence.postgres_reader import PostgresReader
        reader = PostgresReader(settings.read_database_dsn)
    else:
        reader = PendingDatabaseReader()
    container = build_container(reader=reader, settings=settings)
    return create_app(container)


app = build()
