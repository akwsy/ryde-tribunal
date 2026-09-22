"""Alembic environment for the backend-owned `tribunal` schema.

Reads DATABASE_URL from the environment (never hardcoded). Autogenerate is scoped to the
`tribunal` schema only — the backend must never emit DDL for `ride_data` or `case_archive`
(it has SELECT-only there, and a write attempt fails in PostgreSQL by design).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.persistence.models import SCHEMA, Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set to run migrations")
    return url


def _include_object(obj, name, type_, reflected, compare_to):
    # Only ever touch the tribunal schema.
    if type_ == "table":
        return getattr(obj, "schema", None) == SCHEMA
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=SCHEMA,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # The version table lives in the tribunal schema, so the schema must exist before
        # Alembic stamps it (the first migration also CREATE SCHEMA IF NOT EXISTS — idempotent).
        connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=SCHEMA,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
