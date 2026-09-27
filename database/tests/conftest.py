from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Iterator

import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from psycopg import sql
from sqlalchemy.engine import make_url

from seed.generator import seed_database

DATABASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("RYDE_TEST_DATABASE_URL", "postgresql:///ryde_tribunal_test")
ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql:///postgres")


def require_test_database_name(database_url: str) -> str:
    target_database = make_url(database_url).database
    if not target_database:
        raise ValueError("RYDE_TEST_DATABASE_URL must name a database")
    if not target_database.lower().endswith(("_test", "_tests")):
        raise ValueError(
            "database acceptance tests require a database name ending in '_test' or '_tests'; "
            "set RYDE_TEST_DATABASE_URL to a disposable test database"
        )
    return target_database


def ensure_database() -> None:
    target_database = require_test_database_name(DATABASE_URL)
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (target_database,)
        ).fetchone()
        if exists is None:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_database)))


def run_alembic(*args: str, database_url: str | None = None) -> None:
    subprocess.run(
        ["python", "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=DATABASE_DIR,
        check=True,
        env={**os.environ, "DATABASE_URL": database_url or DATABASE_URL},
    )


def ensure_test_case_id_sequence(database_url: str = DATABASE_URL) -> None:
    """Provision the backend-owned ID sequence in DB-package-only disposable test DBs."""
    require_test_database_name(database_url)
    with psycopg.connect(database_url) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS tribunal")
        conn.execute("CREATE SEQUENCE IF NOT EXISTS tribunal.case_id_seq START WITH 100001")


@pytest.fixture(scope="session")
def migrated_seeded_database() -> None:
    # Reader accessors use DATABASE_URL; pin them to the guarded test target even when
    # the caller only supplied RYDE_TEST_DATABASE_URL. Never let DB tests fall through
    # to the application's local ryde_tribunal database.
    require_test_database_name(DATABASE_URL)
    os.environ["DATABASE_URL"] = DATABASE_URL
    ensure_database()
    run_alembic("upgrade", "head")
    ensure_test_case_id_sequence()
    seed_database(DATABASE_URL)


@pytest.fixture
def isolated_company_import_database() -> Iterator[str]:
    """Create a disposable, empty DB for persistence importer tests."""
    database_name = f"ryde_import_test_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    isolated_url = make_conninfo(ADMIN_URL, dbname=database_name)
    isolated_alembic_url = make_url(ADMIN_URL).set(database=database_name).render_as_string(
        hide_password=False
    ).replace("%", "%%")
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        subprocess.run(
            ["python", "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
            cwd=DATABASE_DIR,
            check=True,
            env={**os.environ, "DATABASE_URL": isolated_alembic_url},
        )
        yield isolated_url
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))


@pytest.fixture
def isolated_migration_database() -> Iterator[tuple[str, str]]:
    """An empty database for destructive migration apply/rollback checks."""
    database_name = f"ryde_migration_test_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    isolated_url = make_conninfo(ADMIN_URL, dbname=database_name)
    isolated_alembic_url = make_url(ADMIN_URL).set(database=database_name).render_as_string(
        hide_password=False
    ).replace("%", "%%")
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        yield isolated_url, isolated_alembic_url
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))
