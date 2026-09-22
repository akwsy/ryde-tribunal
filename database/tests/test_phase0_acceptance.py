from __future__ import annotations

import inspect
import json
import os
import re
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from pydantic import ValidationError
from psycopg.rows import dict_row

import reader
from reader.models import Money, RideHeader
from seed.generator import seed_database
from tests.conftest import DATABASE_DIR, DATABASE_URL, run_alembic

OUTCOME_COLUMN_RE = re.compile(r"expected|verdict|outcome|resolution|fault|ground.?truth|correct|is_valid|refund_granted", re.I)
PII_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\+65[ -]?[689][0-9]{7}|\b(?:john|mary|david|sarah|michael|jessica|tan|lim|ng)\b", re.I)


def rows(sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        return list(conn.execute(sql, params).fetchall())


def scalar(sql: str, params: tuple[object, ...] = ()) -> object:
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(sql, params).fetchone()[0]


def test_migrations_apply_to_empty_database_and_roll_back_cleanly() -> None:
    run_alembic("downgrade", "base")
    assert scalar("SELECT to_regnamespace('ride_data')") is None
    assert scalar("SELECT to_regnamespace('case_archive')") is None
    run_alembic("upgrade", "head")
    assert scalar("SELECT to_regnamespace('ride_data')") == "ride_data"
    assert scalar("SELECT to_regnamespace('case_archive')") == "case_archive"
    seed_database(DATABASE_URL)


def test_outcome_freedom_guard_scans_live_column_names() -> None:
    columns = rows(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'ride_data'
        ORDER BY table_name, column_name
        """
    )
    offenders = [f"{r['table_name']}.{r['column_name']}" for r in columns if OUTCOME_COLUMN_RE.search(str(r["column_name"]))]
    assert offenders == []


def test_identifier_namespaces_are_disjoint_and_archive_has_no_live_fk() -> None:
    live_values: set[str] = set()
    archive_values: set[str] = set()
    id_columns = rows(
        """
        SELECT table_schema, table_name, column_name
        FROM information_schema.columns
        WHERE table_schema IN ('ride_data', 'case_archive')
          AND data_type IN ('text', 'character varying', 'character')
          AND column_name LIKE '%%id%%'
        ORDER BY table_schema, table_name, column_name
        """
    )
    with psycopg.connect(DATABASE_URL) as conn:
        for item in id_columns:
            values = conn.execute(
                f"SELECT DISTINCT {item['column_name']} FROM {item['table_schema']}.{item['table_name']} WHERE {item['column_name']} IS NOT NULL"
            ).fetchall()
            target = live_values if item["table_schema"] == "ride_data" else archive_values
            target.update(str(v[0]) for v in values)
    assert live_values.isdisjoint(archive_values)
    assert all(not value.startswith("RIDE-ARCH-") and not value.startswith("DSP-ARCH-") for value in live_values)
    assert all(not re.match(r"^RIDE-[0-9]{6}$", value) and not re.match(r"^DSP-[0-9]{6}$", value) for value in archive_values)

    archive_to_live_fks = rows(
        """
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class src ON src.oid = con.conrelid
        JOIN pg_namespace src_ns ON src_ns.oid = src.relnamespace
        JOIN pg_class dst ON dst.oid = con.confrelid
        JOIN pg_namespace dst_ns ON dst_ns.oid = dst.relnamespace
        WHERE con.contype = 'f'
          AND src_ns.nspname = 'case_archive'
          AND dst_ns.nspname = 'ride_data'
        """
    )
    assert archive_to_live_fks == []


def test_minimum_row_counts_and_all_rows_are_synthetic() -> None:
    assert scalar("SELECT count(*) FROM ride_data.rides") >= 50
    assert scalar("SELECT count(*) FROM case_archive.archive_cases") >= 30
    tables = rows(
        """
        SELECT table_schema, table_name
        FROM information_schema.columns
        WHERE table_schema IN ('ride_data', 'case_archive') AND column_name = 'synthetic'
        ORDER BY table_schema, table_name
        """
    )
    assert tables
    for table in tables:
        count_false = scalar(
            f"SELECT count(*) FROM {table['table_schema']}.{table['table_name']} WHERE synthetic IS NOT TRUE"
        )
        assert count_false == 0, table


def test_referential_integrity_rejects_orphans_and_dependent_ride_delete() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                "INSERT INTO ride_data.ride_gps_samples (ride_id, sample_at, lat, lon, accuracy_meters, speed_meters_per_second, collector, synthetic) VALUES ('RIDE-999999', now(), 1.0, 103.0, 5.0, 0.0, 'test', true)"
            )
        conn.rollback()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute("DELETE FROM ride_data.rides WHERE ride_id = 'RIDE-000001'")
        conn.rollback()


def test_route_data_supports_deviation_stop_and_duration_comparison_for_every_ride() -> None:
    missing = rows(
        """
        SELECT r.ride_id
        FROM ride_data.rides r
        LEFT JOIN ride_data.ride_route_plans p USING (ride_id)
        LEFT JOIN ride_data.ride_gps_samples g USING (ride_id)
        GROUP BY r.ride_id, p.planned_distance_meters, p.actual_distance_meters,
                 p.planned_duration_seconds, p.actual_duration_seconds
        HAVING p.planned_distance_meters IS NULL OR p.actual_distance_meters IS NULL
            OR p.planned_duration_seconds IS NULL OR p.actual_duration_seconds IS NULL
            OR count(g.sample_id) = 0
        """
    )
    assert missing == []
    assert scalar("SELECT count(*) FROM ride_data.ride_stops") >= 50


def test_chat_logs_have_role_timestamp_and_no_real_personal_data() -> None:
    messages = rows("SELECT participant_role, sent_at, message_text FROM ride_data.ride_chat_messages")
    assert messages
    for msg in messages:
        assert msg["participant_role"] in {"rider", "driver", "support"}
        assert msg["sent_at"] is not None
        assert not PII_RE.search(str(msg["message_text"]))


def test_fare_data_supports_breakdown_surge_promo_and_cancellation_fee_checks() -> None:
    assert scalar("SELECT count(*) FROM ride_data.ride_fare_breakdowns WHERE surge_multiplier > 1") > 0
    assert scalar("SELECT count(*) FROM ride_data.ride_promo_applications") >= 50
    assert scalar("SELECT count(*) FROM ride_data.ride_fare_breakdowns WHERE cancellation_fee_cents > 0") > 0
    components_missing = scalar(
        """
        SELECT count(*) FROM ride_data.ride_fare_breakdowns
        WHERE base_fare_cents IS NULL OR distance_fare_cents IS NULL OR time_fare_cents IS NULL
           OR waiting_fare_cents IS NULL OR platform_fee_cents IS NULL OR total_fare_cents IS NULL
        """
    )
    assert components_missing == 0


def test_profiles_carry_account_age_rating_pattern_and_prior_dispute_counts_for_both_roles() -> None:
    for role in ("rider", "driver"):
        assert scalar("SELECT count(*) FROM ride_data.users WHERE role = %s", (role,)) >= 30
    missing = rows(
        """
        SELECT u.user_id
        FROM ride_data.users u
        LEFT JOIN ride_data.user_profiles p USING (user_id)
        LEFT JOIN ride_data.user_dispute_counters d USING (user_id)
        LEFT JOIN ride_data.user_rating_history h USING (user_id)
        GROUP BY u.user_id, p.account_age_days, p.rating_trend, d.disputes_180d
        HAVING p.account_age_days IS NULL OR p.rating_trend IS NULL OR d.disputes_180d IS NULL OR count(h.rating_id) = 0
        """
    )
    assert missing == []


def test_archive_cases_carry_required_decision_and_human_review_fields() -> None:
    missing = rows(
        """
        SELECT c.archive_case_id
        FROM case_archive.archive_cases c
        LEFT JOIN case_archive.archive_case_classifications cl USING (archive_case_id)
        LEFT JOIN case_archive.archive_case_decisions d USING (archive_case_id)
        LEFT JOIN case_archive.archive_human_reviews h USING (archive_case_id)
        WHERE cl.primary_classification IS NULL OR cl.subject IS NULL
           OR d.verdict IS NULL OR d.recommended_action_description IS NULL
           OR d.decision_origin IS NULL OR h.human_reviewed IS NULL
        """
    )
    assert missing == []
    human_touched = scalar("SELECT count(*) FROM case_archive.archive_human_reviews WHERE human_reviewed IS TRUE")
    total = scalar("SELECT count(*) FROM case_archive.archive_human_reviews")
    assert Decimal(str(human_touched)) / Decimal(str(total)) >= Decimal("0.40")
    assert Decimal(str(human_touched)) / Decimal(str(total)) <= Decimal("0.50")


def test_boundary_coverage_is_enumerated_by_scenario_tags() -> None:
    policy = json.loads((DATABASE_DIR / "seed" / "policy" / "ryde-policy-0.1.0.json").read_text())
    threshold_names = {item["name"] for item in policy["numeric_thresholds"]}
    for name in threshold_names:
        sides = {r["side"] for r in rows("SELECT side FROM ride_data.scenario_tags WHERE threshold_name = %s", (name,))}
        assert sides == {"inside", "outside"}


def _snapshot() -> str:
    tables = rows(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('ride_data', 'case_archive') AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
        """
    )
    payload = []
    with psycopg.connect(DATABASE_URL) as conn:
        for table in tables:
            data = conn.execute(
                f"SELECT to_jsonb(t) FROM {table['table_schema']}.{table['table_name']} t ORDER BY to_jsonb(t)::text"
            ).fetchall()
            payload.append((table["table_schema"], table["table_name"], [row[0] for row in data]))
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def test_seed_is_repeatable_for_same_seed() -> None:
    seed_database(DATABASE_URL, "ride-data-v1", "case-archive-v1")
    first = _snapshot()
    seed_database(DATABASE_URL, "ride-data-v1", "case-archive-v1")
    second = _snapshot()
    assert first == second


def test_eight_accessors_return_validated_models_and_no_write_surface() -> None:
    assert set(reader.__all__) == {
        "get_ride",
        "get_route",
        "get_gps_samples",
        "get_chat_log",
        "get_fare_breakdown",
        "get_profile",
        "get_case",
        "search_archive",
    }
    exported_functions = {name for name, obj in inspect.getmembers(reader, inspect.isfunction) if not name.startswith("_")}
    assert exported_functions == set(reader.__all__)
    assert not any(re.search(r"persist|insert|update|delete|write", name, re.I) for name in exported_functions)

    assert reader.get_ride("RIDE-000001").ride_id == "RIDE-000001"
    assert reader.get_route("RIDE-000001").waypoints
    assert reader.get_gps_samples("RIDE-000001")
    assert reader.get_chat_log("RIDE-000001")
    assert reader.get_fare_breakdown("RIDE-000001").promos
    assert reader.get_profile("USR-R-000001").dispute_counts.disputes_180d >= 0
    assert reader.get_case("DSP-ARCH-000001").decision.verdict
    assert reader.search_archive("route_deviation", {"category": "route_deviation"}, 3)

    with pytest.raises(ValidationError):
        Money.model_validate({"amount_cents": "325", "currency": "SGD"})
    with pytest.raises(ValidationError):
        RideHeader.model_validate(
            {
                "ride_id": "RIDE-000001",
                "rider_user_id": "USR-R-000001",
                "driver_user_id": "USR-D-000001",
                "requested_at": "2026-09-22T00:00:00Z",
                "accepted_at": None,
                "pickup_at": None,
                "dropoff_at": None,
                "ride_status": "completed",
                "service_tier": "standard",
                "quoted_distance_meters": 1,
                "quoted_duration_seconds": 1,
                "quoted_fare": {"amount_cents": 1, "currency": "SGD"},
                "fare_total": {"amount_cents": 1, "currency": "SGD"},
                "synthetic": False,
            }
        )


def test_backend_role_has_select_but_insert_is_refused() -> None:
    backend_url = os.getenv(
        "BACKEND_READONLY_DATABASE_URL",
        "postgresql://ryde_backend_readonly:ryde_backend_readonly@localhost:5432/ryde_tribunal",
    )
    with psycopg.connect(backend_url) as conn:
        assert conn.execute("SELECT count(*) FROM ride_data.rides").fetchone()[0] >= 50
        assert conn.execute("SELECT count(*) FROM case_archive.archive_cases").fetchone()[0] >= 30
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO ride_data.users (user_id, role, display_handle, created_at, account_status, synthetic) VALUES ('USR-R-999999', 'rider', 'blocked', now(), 'active', true)"
            )
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO case_archive.archive_cases (archive_case_id, archive_ride_id, category, subject, filed_by, created_at, policy_version, synthetic) VALUES ('DSP-ARCH-999999', 'RIDE-ARCH-999999', 'route_deviation', 'blocked', 'rider', now(), 'ryde-policy-0.1.0', true)"
            )
        conn.rollback()
