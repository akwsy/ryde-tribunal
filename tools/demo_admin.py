"""One-time operator setup for an isolated, synthetic hosted demo database.

Normal application startup never runs this command.  The database name and empty
state are checked before any migration or seed write.  Credentials are read from
environment variables and never printed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
DEMO_RIDES = {
    "RIDE-000145": ("route_deviation", "Was the recorded route appropriate?", "Please review the route taken and the quoted fare."),
    "RIDE-000150": ("no_show_charge", "Was the waiting charge supported?", "I dispute the waiting charge after the driver reached the pickup point."),
    "RIDE-000147": ("fare_calculation", "Does the receipt match the fare?", "Please check the trip receipt against the fare components."),
    "RIDE-000160": ("other_cancellation_fee", "Was this cancellation charge correct?", "Please check the charge type and the recorded cancellation events."),
    "RIDE-000155": ("fare_calculation", "A fare component needs review", "I cannot reconcile one of the fare items with my receipt."),
    "RIDE-000158": ("safety_incident", "Safety concern during the trip", "Please preserve the trip records and arrange a reviewer assessment."),
}
RECENT_RIDES = [f"RIDE-{index:06d}" for index in range(145, 161)]


def _database_name(conn: psycopg.Connection) -> str:
    name = conn.execute("select current_database()").fetchone()[0]
    if name != "ryde_tribunal_demo" and not name.endswith(("_test", "_tests")):
        raise RuntimeError(f"Refusing demo setup on database {name!r}")
    return name


def _run_migration(folder: str, dsn: str) -> None:
    env = {**os.environ, "DATABASE_URL": dsn.replace("postgresql://", "postgresql+psycopg://", 1),
           "PYTHONPATH": str(ROOT)}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / folder, env=env, check=True)


def _shift_recent_trips(conn: psycopg.Connection) -> None:
    """Move selected seeded trips to October without changing archive snapshots."""
    dates = {ride: datetime(2026, 10, 15, 8, tzinfo=timezone(timedelta(hours=8)))
             + timedelta(hours=2 * offset) for offset, ride in enumerate(RECENT_RIDES)}
    columns = conn.execute("""SELECT table_name,column_name FROM information_schema.columns
        WHERE table_schema='ride_data' AND data_type='timestamp with time zone'
          AND table_name IN (SELECT table_name FROM information_schema.columns
                             WHERE table_schema='ride_data' AND column_name='ride_id')""").fetchall()
    grouped: dict[str, list[str]] = {}
    for table, column in columns:
        grouped.setdefault(table, []).append(column)
    for ride, target in dates.items():
        original = conn.execute("SELECT requested_at FROM ride_data.rides WHERE ride_id=%s", (ride,)).fetchone()
        if original is None:
            raise RuntimeError(f"Synthetic trip {ride} is missing")
        delta = target - original[0]
        for table, fields in grouped.items():
            assignments = sql.SQL(", ").join(sql.SQL("{} = {} + %s").format(sql.Identifier(field), sql.Identifier(field)) for field in fields)
            conn.execute(sql.SQL("UPDATE {}.{} SET {} WHERE ride_id=%s").format(
                sql.Identifier("ride_data"), sql.Identifier(table), assignments), tuple(delta for _ in fields) + (ride,))


def _create_app_roles(conn: psycopg.Connection) -> None:
    reader_password = os.environ.get("DEMO_READER_PASSWORD", "")
    writer_password = os.environ.get("DEMO_WRITER_PASSWORD", "")
    if len(reader_password) < 24 or len(writer_password) < 24:
        raise RuntimeError("Set distinct DEMO_READER_PASSWORD and DEMO_WRITER_PASSWORD, each at least 24 characters")
    for role, password, group in (
        ("ryde_demo_reader", reader_password, "ryde_backend_readonly"),
        ("ryde_demo_writer", writer_password, "ryde_backend_writer"),
    ):
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
        else:
            conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
        conn.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(role)))
    conn.execute("GRANT USAGE ON SCHEMA tribunal TO ryde_demo_writer")
    conn.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA tribunal TO ryde_demo_writer")
    conn.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA tribunal TO ryde_demo_writer")
    conn.execute("GRANT USAGE ON SCHEMA ride_data TO ryde_demo_writer")
    conn.execute("GRANT USAGE ON SEQUENCE ride_data.imported_evidence_id_seq TO ryde_demo_writer")


def _prepare_current_policy_examples(conn: psycopg.Connection) -> None:
    """Give recent seeded trips current service names and coherent fee records."""
    conn.execute("UPDATE ride_data.rides SET service_tier='RydeX' WHERE ride_id=ANY(%s)", (RECENT_RIDES,))
    # The two-minute rider cancellation is eligible for the published S$6.61
    # voucher when the request is filed within 30 days.
    conn.execute("""UPDATE ride_data.rides SET accepted_at=requested_at,
        cancellation_at=requested_at + interval '2 minutes',
        cancellation_reason='rider_cancelled' WHERE ride_id='RIDE-000150'""")
    conn.execute("""UPDATE ride_data.ride_fare_breakdowns SET
        total_fare_cents=total_fare_cents+161, cancellation_fee_cents=661
        WHERE ride_id='RIDE-000150'""")
    # Keep one receipt straightforward: the generic seed includes a promotional
    # row and rounding adjustment that are absent from its stated total.
    conn.execute("DELETE FROM ride_data.ride_promo_applications WHERE ride_id='RIDE-000147'")
    conn.execute("DELETE FROM ride_data.ride_fare_adjustments WHERE ride_id='RIDE-000147'")
    for sequence, event_type, offset in ((1, "driver_arrived", 30), (2, "rider_cancelled", 120)):
        conn.execute("""INSERT INTO ride_data.ride_app_events
            (event_id,ride_id,sequence_no,event_at,event_type,details,source_system,
             evidence_source,verification_status,verified_by,verified_at,provenance,synthetic)
            SELECT 'EV-'||lpad(nextval('ride_data.imported_evidence_id_seq')::text,6,'0'),
                   ride_id,%s,requested_at+(%s * interval '1 second'),%s,
                   'Recorded by the trip app','synthetic_demo','first_party_record',
                   'verified','synthetic-demo-generator',requested_at,
                   '{"dataset":"synthetic-demo-v1"}'::jsonb,true
            FROM ride_data.rides WHERE ride_id='RIDE-000150'""", (sequence, offset, event_type))
    # The completed trip includes a S$5 rider waiting charge at the three-minute
    # boundary. The payment total is unchanged because the seed had a S$5
    # cancellation component in the same synthetic fare record.
    conn.execute("""UPDATE ride_data.rides SET ride_status='completed',
        dropoff_at=requested_at + interval '20 minutes' WHERE ride_id='RIDE-000160'""")
    conn.execute("""UPDATE ride_data.ride_fare_breakdowns SET waiting_fare_cents=500,
        cancellation_fee_cents=0 WHERE ride_id='RIDE-000160'""")
    conn.execute("""UPDATE ride_data.user_dispute_counters SET disputes_30d=1
        WHERE user_id=(SELECT rider_user_id FROM ride_data.rides WHERE ride_id='RIDE-000160')""")
    # Preserve one genuinely inconsistent receipt as the human-review example.
    conn.execute("""UPDATE ride_data.ride_fare_breakdowns SET total_fare_cents=total_fare_cents+37
        WHERE ride_id='RIDE-000155'""")


def _file_current_cases(dsn: str) -> None:
    from fastapi.testclient import TestClient
    from app.api.app import create_app
    from app.api.container import build_container
    from app.persistence.postgres_reader import PostgresReader
    from app.persistence.postgres_store import PostgresResultStore
    from app.settings import Settings

    settings = Settings(_env_file=None, read_database_dsn=dsn, tribunal_database_dsn=dsn,
                        model_provider="deterministic_mock", policy_version="ryde-policy-1.1.0",
                        demo_access_enabled=False)
    app = create_app(build_container(reader=PostgresReader(dsn), store=PostgresResultStore(dsn), settings=settings))
    with TestClient(app) as client:
        for ride, (category, subject, description) in DEMO_RIDES.items():
            details = {"fee_type": "rider_waiting"} if ride == "RIDE-000160" else {}
            response = client.post("/api/v1/disputes", json={"ride_id": ride, "category": category,
                "filed_by": "rider", "subject": subject, "description": description,
                "category_details": details},
                headers={"X-Reviewer-Id": "synthetic-demo-setup", "Idempotency-Key": f"demo-{ride}"})
            if response.status_code not in (200, 201):
                raise RuntimeError(f"Demo case filing failed for {ride}: {response.status_code} {response.text[:200]}")
            case_id = response.json()["case_id"]
            result = client.post(f"/api/v1/disputes/{case_id}/adjudicate", headers={
                "X-Reviewer-Id": "synthetic-demo-setup", "Idempotency-Key": f"demo-adjudicate-{ride}"})
            if result.status_code not in (200, 201):
                raise RuntimeError(f"Demo adjudication failed for {case_id}: {result.status_code} {result.text[:200]}")


def initialize() -> None:
    dsn = os.environ.get("DEMO_ADMIN_DSN", "")
    if not dsn.startswith("postgresql://"):
        raise RuntimeError("Set DEMO_ADMIN_DSN to a plain PostgreSQL DSN for a new demo database")
    with psycopg.connect(dsn, autocommit=True) as conn:
        name = _database_name(conn)
        existing = conn.execute("""SELECT count(*) FROM information_schema.tables
            WHERE table_schema IN ('ride_data','case_archive','tribunal')""").fetchone()[0]
        if existing:
            raise RuntimeError(f"Database {name!r} already contains application tables; setup will not reseed it")
    _run_migration("database", dsn)
    _run_migration("backend", dsn)
    from database.seed.generator import seed_database
    seed_database(dsn)
    with psycopg.connect(dsn) as conn:
        _database_name(conn)
        _shift_recent_trips(conn)
        _prepare_current_policy_examples(conn)
        _create_app_roles(conn)
        conn.commit()
    _file_current_cases(dsn)
    with psycopg.connect(dsn) as conn:
        _database_name(conn)
        conn.execute("CREATE SCHEMA IF NOT EXISTS demo_admin")
        conn.execute("CREATE TABLE demo_admin.seed_run (seed_id text PRIMARY KEY, completed_at timestamptz NOT NULL DEFAULT now())")
        conn.execute("INSERT INTO demo_admin.seed_run(seed_id) VALUES ('synthetic-demo-v1')")
        conn.commit()
    print(f"Initialized {name}: 47 historical decisions, 16 recent trips, 6 current-policy cases")


if __name__ == "__main__":
    if sys.argv[1:] != ["initialize"]:
        raise SystemExit("Usage: python tools/demo_admin.py initialize")
    initialize()
