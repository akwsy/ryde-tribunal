from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
import pytest

from seed.generator import seed_database

DATABASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:///ryde_tribunal")
ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql:///postgres")


def ensure_database() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = 'ryde_tribunal'").fetchone()
        if exists is None:
            conn.execute("CREATE DATABASE ryde_tribunal")


def run_alembic(*args: str) -> None:
    subprocess.run(
        ["python", "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=DATABASE_DIR,
        check=True,
        env={**os.environ, "DATABASE_URL": DATABASE_URL},
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_seeded_database() -> None:
    ensure_database()
    run_alembic("upgrade", "head")
    seed_database(DATABASE_URL)
