#!/usr/bin/env python3
"""Normalize historical record IDs to the same formats used by live records.

The command is a dry run unless --apply is supplied. Run after backend migrations reach head and
database migrations reach 0007_global_archive_entity_ids, with the backend and all seed/import
processes stopped. Upgrade database migrations to head after the remap to enforce canonical IDs.
It rewrites stored references in one DB transaction and advances the shared entity sequences.
"""
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Json, Jsonb


MIGRATION_KEY = "global_record_ids_v2"
PATTERNS = {
    "case": re.compile(r"^DSP-(?:ARCH-)?(\d{6})$"),
    "ride": re.compile(r"^(?:RIDE-ARCH-|RIDE-)(\d{6})$"),
    "rider": re.compile(r"^(?:USR-ARCH-R-|USR-R-)(\d{6})$"),
    "driver": re.compile(r"^(?:USR-ARCH-D-|USR-D-)(\d{6})$"),
    "evidence": re.compile(r"^(?:ARCH-EV-(\d{6})-\d{2}|EV-(\d{6}))$"),
    "policy": re.compile(r"^(?:ARCH-POLICY-|POLICY-)(\d{6})$"),
}
PREFIXES = {
    "case": "DSP",
    "ride": "RIDE",
    "rider": "USR-R",
    "driver": "USR-D",
    "evidence": "EV",
    "policy": "POLICY",
}
SEQUENCES = {
    "case": [("tribunal", "case_id_seq")],
    "ride": [("ride_data", "imported_ride_id_seq")],
    "rider": [("ride_data", "imported_rider_id_seq")],
    "driver": [("ride_data", "imported_driver_id_seq")],
    "evidence": [
        ("ride_data", "imported_evidence_id_seq"),
        ("tribunal", "evidence_id_seq"),  # legacy sequence high-water before cutover
    ],
    "policy": [],
}
ID_COLUMNS = {
    "case_id", "archive_case_id", "ride_id", "archive_ride_id",
    "user_id", "archive_user_id", "rider_archive_user_id", "driver_archive_user_id",
    "filing_archive_user_id", "rider_id", "driver_id", "evidence_id",
    "archive_evidence_id", "event_id", "message_id", "call_id", "signal_id",
    "policy_version_id",
}
JSON_SCHEMAS = ("tribunal", "case_archive")
SKIP_JSON_KEYS = ("company", "external", "source", "source_key", "bundle")


@dataclass(frozen=True)
class StoredId:
    entity: str
    source: str
    old_id: str
    filed_at: datetime | None = None


@dataclass(frozen=True)
class IdChange:
    entity: str
    source: str
    old_id: str
    new_id: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit the remap; default is dry-run")
    return parser


def _table_lock(conn: psycopg.Connection[Any]) -> None:
    rows = conn.execute(
        "SELECT schemaname, tablename FROM pg_tables "
        "WHERE schemaname IN ('ride_data','tribunal','case_archive') "
        "ORDER BY schemaname, tablename"
    ).fetchall()
    if not rows:
        raise RuntimeError("Expected ride_data, tribunal, and case_archive tables")
    for schema, table in rows:
        conn.execute(
            sql.SQL("LOCK TABLE {}.{} IN ACCESS EXCLUSIVE MODE").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        )


def _assert_ready(conn: psycopg.Connection[Any]) -> None:
    required = (
        "ride_data.rides", "ride_data.users", "ride_data.ride_app_events",
        "ride_data.ride_chat_messages", "ride_data.ride_call_attempts",
        "ride_data.ride_device_signals",
        "ride_data.imported_ride_id_seq", "ride_data.imported_rider_id_seq",
        "ride_data.imported_driver_id_seq", "ride_data.imported_evidence_id_seq",
        "tribunal.case_records", "tribunal.case_id_seq", "tribunal.evidence_id_seq",
        "case_archive.archive_cases", "case_archive.archive_trip_snapshots",
        "case_archive.archive_user_snapshots", "case_archive.archive_case_evidence",
        "case_archive.archive_policy_versions", "case_archive.archive_case_rulings",
    )
    missing = [name for name in required if conn.execute(
        "SELECT to_regclass(%s)", (name,)
    ).fetchone()[0] is None]
    if missing:
        raise RuntimeError(
            "Apply backend migrations to head and database migrations through 0007 before remapping; missing: "
            + ", ".join(missing)
        )
    versions = {
        "database": conn.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchone(),
        "backend": conn.execute(
            "SELECT version_num FROM tribunal.alembic_version"
        ).fetchone(),
    }
    if versions["database"] is None or versions["database"][0] != "0007_global_archive_entity_ids":
        raise RuntimeError("Database migrations must be at 0007_global_archive_entity_ids")
    if versions["backend"] is None or versions["backend"][0] != "0002_case_result_origin":
        raise RuntimeError("Backend migrations must be at 0002_case_result_origin")


def _already_applied(conn: psycopg.Connection[Any]) -> bool:
    if conn.execute("SELECT to_regclass('case_archive.case_id_migration_log')").fetchone()[0] is None:
        return False
    return conn.execute(
        "SELECT 1 FROM case_archive.case_id_migration_log WHERE migration_key=%s",
        (MIGRATION_KEY,),
    ).fetchone() is not None


def _sequence_highwater(conn: psycopg.Connection[Any], schema: str, name: str) -> int | None:
    if conn.execute("SELECT to_regclass(%s)", (f"{schema}.{name}",)).fetchone()[0] is None:
        return None
    last_value, is_called = conn.execute(
        sql.SQL("SELECT last_value, is_called FROM {}.{}").format(
            sql.Identifier(schema), sql.Identifier(name)
        )
    ).fetchone()
    return int(last_value) if is_called else int(last_value) - 1


def _suffix(entity: str, identifier: str) -> int | None:
    match = PATTERNS[entity].fullmatch(identifier)
    if match is None:
        return None
    return int(next(group for group in match.groups() if group is not None))


def _maximum(entity: str, identifiers: list[str], sequence_marks: list[int | None]) -> int:
    stored = [value for identifier in identifiers if (value := _suffix(entity, identifier)) is not None]
    return max([0, *stored, *(mark for mark in sequence_marks if mark is not None)])


def _case_records(conn: psycopg.Connection[Any]) -> list[StoredId]:
    rows = conn.execute(
        """SELECT 'live', case_id, filed_at FROM tribunal.case_records
           UNION ALL
           SELECT 'archive', archive_case_id, created_at FROM case_archive.archive_cases
           ORDER BY 3 NULLS LAST, 2"""
    ).fetchall()
    records = [StoredId("case", row[0], row[1], row[2]) for row in rows]
    return records


def _archive_ids(conn: psycopg.Connection[Any], entity: str) -> list[StoredId]:
    queries = {
        "ride": "SELECT 'archive', archive_ride_id, trip_at FROM case_archive.archive_trip_snapshots ORDER BY archive_ride_id",
        "rider": "SELECT 'archive', archive_user_id, NULL FROM case_archive.archive_user_snapshots WHERE role='rider' ORDER BY archive_user_id",
        "driver": "SELECT 'archive', archive_user_id, NULL FROM case_archive.archive_user_snapshots WHERE role='driver' ORDER BY archive_user_id",
        "evidence": "SELECT 'archive', archive_evidence_id, recorded_at FROM case_archive.archive_case_evidence ORDER BY archive_evidence_id",
        "policy": "SELECT 'archive', policy_version_id, effective_from FROM case_archive.archive_policy_versions ORDER BY policy_version_id",
    }
    return [StoredId(entity, row[0], row[1], row[2]) for row in conn.execute(queries[entity]).fetchall()]


def _live_ids(conn: psycopg.Connection[Any], entity: str) -> list[str]:
    queries = {
        "case": "SELECT case_id FROM tribunal.case_records",
        "ride": "SELECT ride_id FROM ride_data.rides",
        "rider": "SELECT user_id FROM ride_data.users WHERE role='rider'",
        "driver": "SELECT user_id FROM ride_data.users WHERE role='driver'",
        "evidence": (
            "SELECT event_id FROM ride_data.ride_app_events "
            "UNION ALL SELECT message_id FROM ride_data.ride_chat_messages "
            "UNION ALL SELECT call_id FROM ride_data.ride_call_attempts "
            "UNION ALL SELECT signal_id FROM ride_data.ride_device_signals"
        ),
        "policy": "SELECT NULL::text WHERE false",
    }
    values = [row[0] for row in conn.execute(queries[entity]).fetchall()]
    return values


def _json_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _json_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _json_strings(item)


def _tribunal_evidence_ids(conn: psycopg.Connection[Any]) -> list[str]:
    columns = conn.execute(
        """SELECT table_schema,table_name,column_name FROM information_schema.columns
           WHERE table_schema='tribunal' AND data_type IN ('json','jsonb')
           ORDER BY table_name,column_name"""
    ).fetchall()
    result: list[str] = []
    for schema, table, column in columns:
        statement = sql.SQL("SELECT {} FROM {}.{} WHERE {} IS NOT NULL").format(
            sql.Identifier(column), sql.Identifier(schema), sql.Identifier(table), sql.Identifier(column)
        )
        for (value,) in conn.execute(statement).fetchall():
            result.extend(
                item for item in _json_strings(value)
                if PATTERNS["evidence"].fullmatch(item)
            )
    return result


def _plans(conn: psycopg.Connection[Any]) -> tuple[list[IdChange], dict[str, int]]:
    records: list[StoredId] = []
    case_records = _case_records(conn)
    records.extend(case_records)
    for entity in ("ride", "rider", "driver", "evidence", "policy"):
        records.extend(_archive_ids(conn, entity))

    changes: list[IdChange] = []
    highwaters: dict[str, int] = {}
    entity_records = {entity: [item for item in records if item.entity == entity]
                      for entity in PATTERNS}
    for entity, rows in entity_records.items():
        live_ids = _live_ids(conn, entity)
        archive_ids = [item.old_id for item in rows if item.source == "archive"]
        all_ids = live_ids + archive_ids
        json_ids = _tribunal_evidence_ids(conn) if entity == "evidence" else []
        malformed = [item for item in all_ids if _suffix(entity, item) is None]
        if malformed:
            raise RuntimeError(
                f"Unexpected {entity} ID(s), no rows changed: {malformed[:5]!r}"
            )
        duplicates = sorted({item for item in all_ids if all_ids.count(item) > 1})
        if duplicates:
            raise RuntimeError(
                f"Existing {entity} IDs collide across records and cannot be remapped safely: "
                f"{duplicates[:5]!r}"
            )
        marks = [
            _sequence_highwater(conn, schema, sequence)
            for schema, sequence in SEQUENCES[entity]
        ]
        if entity == "evidence":
            marks += [_suffix("evidence", identifier) for identifier in json_ids]
        highwater = _maximum(entity, all_ids + json_ids, marks)
        highwaters[entity] = highwater
        if entity == "policy":
            rows = sorted(rows, key=lambda item: (item.filed_at or datetime.min, item.old_id))
        elif entity == "case":
            rows = sorted(rows, key=lambda item: (item.filed_at is None, item.filed_at, item.old_id))
        else:
            rows = sorted(rows, key=lambda item: item.old_id)
        if highwater + len(rows) > 999_999:
            raise RuntimeError(f"Six-digit {entity} ID range exhausted")
        for index, item in enumerate(rows, start=1):
            new_id = f"{PREFIXES[entity]}-{highwater + index:06d}"
            changes.append(IdChange(entity, item.source, item.old_id, new_id))
    old_ids = [change.old_id for change in changes]
    if len(old_ids) != len(set(old_ids)):
        raise RuntimeError("Two identifier classes contain the same old ID; refusing ambiguous remap")
    return changes, highwaters


def _dependent_foreign_keys(conn: psycopg.Connection[Any]) -> list[tuple[str, str, str, bool, bool]]:
    return conn.execute(
        """SELECT child_ns.nspname, child.relname, con.conname, con.condeferrable, con.condeferred
           FROM pg_constraint con JOIN pg_class child ON child.oid=con.conrelid
           JOIN pg_namespace child_ns ON child_ns.oid=child.relnamespace
           WHERE con.contype='f' AND con.confrelid IN (
             'tribunal.case_records'::regclass,
             'case_archive.archive_cases'::regclass,
             'case_archive.archive_trip_snapshots'::regclass,
             'case_archive.archive_user_snapshots'::regclass,
             'case_archive.archive_case_evidence'::regclass)
           ORDER BY child_ns.nspname,child.relname,con.conname"""
    ).fetchall()


def _defer_foreign_keys(conn: psycopg.Connection[Any]) -> list[tuple[str, str, str, bool, bool]]:
    constraints = _dependent_foreign_keys(conn)
    for schema, table, name, _deferrable, _deferred in constraints:
        conn.execute(sql.SQL("ALTER TABLE {}.{} ALTER CONSTRAINT {} DEFERRABLE INITIALLY DEFERRED").format(
            sql.Identifier(schema), sql.Identifier(table), sql.Identifier(name)
        ))
    conn.execute("SET CONSTRAINTS ALL DEFERRED")
    return constraints


def _restore_foreign_keys(conn: psycopg.Connection[Any], constraints) -> None:
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    for schema, table, name, was_deferrable, was_deferred in constraints:
        if was_deferrable:
            mode = "DEFERRED" if was_deferred else "IMMEDIATE"
            query = sql.SQL("ALTER TABLE {}.{} ALTER CONSTRAINT {} DEFERRABLE INITIALLY " + mode)
        else:
            query = sql.SQL("ALTER TABLE {}.{} ALTER CONSTRAINT {} NOT DEFERRABLE")
        conn.execute(query.format(sql.Identifier(schema), sql.Identifier(table), sql.Identifier(name)))


def _replace_json(value: Any, replacements: dict[str, str], parent_key: str = "") -> tuple[Any, bool]:
    if isinstance(value, str):
        if any(token in parent_key.lower() for token in SKIP_JSON_KEYS):
            return value, False
        replacement = replacements.get(value, value)
        return replacement, replacement != value
    if isinstance(value, list):
        result, changed = [], False
        for item in value:
            new_item, item_changed = _replace_json(item, replacements, parent_key)
            result.append(new_item)
            changed |= item_changed
        return result, changed
    if isinstance(value, dict):
        result, changed = {}, False
        for key, item in value.items():
            if isinstance(key, str) and not any(token in key.lower() for token in SKIP_JSON_KEYS):
                new_key = replacements.get(key, key)
            else:
                new_key = key
            new_item, item_changed = _replace_json(item, replacements, str(key))
            result[new_key] = new_item
            changed |= item_changed or new_key != key
        return result, changed
    return value, False


def _replace_json_references(conn: psycopg.Connection[Any], replacements: dict[str, str]) -> int:
    updates = 0
    for schema in JSON_SCHEMAS:
        columns = conn.execute(
            """SELECT table_name,column_name,data_type FROM information_schema.columns
               WHERE table_schema=%s AND data_type IN ('json','jsonb')
               ORDER BY table_name,column_name""", (schema,)
        ).fetchall()
        for table, column, data_type in columns:
            select = sql.SQL("SELECT ctid::text,{} FROM {}.{} WHERE {} IS NOT NULL").format(
                sql.Identifier(column), sql.Identifier(schema), sql.Identifier(table), sql.Identifier(column)
            )
            for ctid, raw in conn.execute(select).fetchall():
                value, changed = _replace_json(raw, replacements)
                if not changed:
                    continue
                wrapped = Jsonb(value) if data_type == "jsonb" else Json(value)
                update = sql.SQL("UPDATE {}.{} SET {}=%s WHERE ctid=%s::tid").format(
                    sql.Identifier(schema), sql.Identifier(table), sql.Identifier(column)
                )
                conn.execute(update, (wrapped, ctid))
                updates += 1
    return updates


def _replace_id_columns(conn: psycopg.Connection[Any], replacements: dict[str, str]) -> int:
    columns = conn.execute(
        """SELECT table_schema,table_name,column_name FROM information_schema.columns
           WHERE table_schema IN ('ride_data','tribunal','case_archive')
             AND column_name = ANY(%s)
             AND data_type IN ('text','character varying','character')
           ORDER BY table_schema,table_name,column_name""", (list(ID_COLUMNS),)
    ).fetchall()
    updates = 0
    for schema, table, column in columns:
        for old_id, new_id in replacements.items():
            query = sql.SQL("UPDATE {}.{} SET {}=%s WHERE {}=%s").format(
                sql.Identifier(schema), sql.Identifier(table), sql.Identifier(column), sql.Identifier(column)
            )
            updates += conn.execute(query, (new_id, old_id)).rowcount
    return updates


def _normalize_seed_bundle_evidence_keys(conn: psycopg.Connection[Any]) -> int:
    return conn.execute(
        """UPDATE case_archive.archive_case_evidence
           SET bundle_evidence_key =
             'ryde-tribunal-synthetic-archive:seed-evidence-' ||
             split_part(split_part(bundle_evidence_key, 'ARCH-EV-', 2), '-', 1) || '-' ||
             split_part(split_part(bundle_evidence_key, 'ARCH-EV-', 2), '-', 2)
           WHERE synthetic IS TRUE
             AND bundle_evidence_key LIKE 'ryde-tribunal-synthetic-archive:ARCH-EV-%'"""
    ).rowcount


def _legacy_seed_bundle_evidence_key_count(conn: psycopg.Connection[Any]) -> int:
    return conn.execute(
        """SELECT count(*) FROM case_archive.archive_case_evidence
           WHERE synthetic IS TRUE
             AND bundle_evidence_key LIKE 'ryde-tribunal-synthetic-archive:ARCH-EV-%'"""
    ).fetchone()[0]


def _apply_changes(conn: psycopg.Connection[Any], changes: list[IdChange]) -> int:
    constraints = _defer_foreign_keys(conn)
    old_to_new = {item.old_id: item.new_id for item in changes}
    # 0007 left this legacy check in its ARCH-only form even though the remap
    # moves archive case ride references to the shared RIDE-###### namespace.
    # Replace it transactionally with the final predicate before touching rows.
    conn.execute(
        "ALTER TABLE case_archive.archive_cases "
        "DROP CONSTRAINT IF EXISTS archive_cases_archive_ride_id_check"
    )
    try:
        updated = _replace_id_columns(conn, old_to_new)
        updated += _replace_json_references(conn, old_to_new)
        # Flush deferred FK cascade events before changing the table constraint.
        _restore_foreign_keys(conn, constraints)
        conn.execute(
            "ALTER TABLE case_archive.archive_cases "
            "ADD CONSTRAINT archive_cases_archive_ride_id_check "
            "CHECK (archive_ride_id ~ '^RIDE-[0-9]{6}$')"
        )
        return updated
    except Exception:
        # The outer transaction rolls back all data and DDL; do not leave FK
        # constraints altered if this helper is reused with a savepoint later.
        raise


def _set_sequence(conn: psycopg.Connection[Any], schema: str, name: str, value: int) -> None:
    if value <= 0:
        conn.execute("SELECT setval(%s::regclass,1,false)", (f"{schema}.{name}",))
    else:
        conn.execute("SELECT setval(%s::regclass,%s,true)", (f"{schema}.{name}", value))


def _set_sequences(conn: psycopg.Connection[Any], highwaters: dict[str, int], changes: list[IdChange]) -> None:
    for entity, sequences in SEQUENCES.items():
        suffixes = [_suffix(entity, item.new_id) for item in changes if item.entity == entity]
        value = max([highwaters[entity], *(item for item in suffixes if item is not None)])
        for schema, name in sequences:
            if conn.execute("SELECT to_regclass(%s)", (f"{schema}.{name}",)).fetchone()[0] is not None:
                _set_sequence(conn, schema, name, value)


def migrate(database_url: str, *, apply: bool) -> None:
    if database_url.startswith("postgresql+psycopg://"):
        database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(database_url) as conn:
        try:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_KEY,))
            _assert_ready(conn)
            _table_lock(conn)
            if _already_applied(conn):
                print("Global record ID migration is already recorded; no changes made.")
                conn.rollback()
                return
            changes, highwaters = _plans(conn)
            seed_key_count = _legacy_seed_bundle_evidence_key_count(conn)
            if apply:
                changed_values = _apply_changes(conn, changes)
                changed_seed_keys = _normalize_seed_bundle_evidence_keys(conn)
                _set_sequences(conn, highwaters, changes)
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS case_archive.case_id_migration_log (
                         migration_key text PRIMARY KEY, completed_at timestamptz NOT NULL DEFAULT now(),
                         remapped_cases integer NOT NULL, first_assigned_id text, last_assigned_id text,
                         previous_highwater integer NOT NULL)"""
                )
                case_changes = [item for item in changes if item.entity == "case"]
                case_highwater = highwaters["case"]
                conn.execute(
                    """INSERT INTO case_archive.case_id_migration_log
                         (migration_key,remapped_cases,first_assigned_id,last_assigned_id,previous_highwater)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (MIGRATION_KEY, len(case_changes),
                     case_changes[0].new_id if case_changes else None,
                     case_changes[-1].new_id if case_changes else None, case_highwater),
                )
                conn.commit()
            else:
                changed_values = 0
                changed_seed_keys = 0
                conn.rollback()
            print("Planned ID changes by entity:")
            for entity in PATTERNS:
                entity_changes = [item for item in changes if item.entity == entity]
                if not entity_changes:
                    continue
                print(f"  {entity}: {len(entity_changes)}; previous high-water {highwaters[entity]}; "
                      f"range {entity_changes[0].new_id}..{entity_changes[-1].new_id}")
            if apply:
                print(f"Database ID/reference fields updated: {changed_values}")
            print(f"Synthetic evidence source keys to normalize: {seed_key_count}")
            if apply:
                print(f"Synthetic evidence source keys normalized: {changed_seed_keys}")
            print(f"Mode: {'APPLIED' if apply else 'DRY RUN (no changes committed)'}")
        except Exception:
            conn.rollback()
            raise


def main() -> None:
    args = _parser().parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL to the migration-capable local PostgreSQL database.")
    migrate(database_url, apply=args.apply)


if __name__ == "__main__":
    main()
