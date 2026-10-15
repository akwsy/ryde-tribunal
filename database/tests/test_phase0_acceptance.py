from __future__ import annotations

import inspect
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from pydantic import ValidationError
from psycopg.rows import dict_row

import reader
from reader.models import Money, RideHeader
from seed.export_bundles import export as export_seed_bundles
from seed.generator import (
    ARCHIVE_SOURCE_NAMESPACE,
    BASE_ARCHIVE_CASE_COUNT,
    CATEGORY_TAGS,
    POLICY_VERSION,
    seed_database,
)
from tests.conftest import DATABASE_DIR, DATABASE_URL, run_alembic

pytestmark = pytest.mark.usefixtures("migrated_seeded_database")

OUTCOME_COLUMN_RE = re.compile(r"expected|verdict|outcome|resolution|fault|ground.?truth|correct|is_valid|refund_granted", re.I)
PII_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\+65[ -]?[689][0-9]{7}|\b(?:john|mary|david|sarah|michael|jessica|tan|lim|ng)\b", re.I)


def rows(sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        return list(conn.execute(sql, params).fetchall())


def scalar(sql: str, params: tuple[object, ...] = ()) -> object:
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(sql, params).fetchone()[0]


def live_or_unused_case_id() -> str:
    """Use a real live case ID when backend tables are present, else an unused canonical ID."""
    with psycopg.connect(DATABASE_URL) as conn:
        if conn.execute("SELECT to_regclass('tribunal.case_records')").fetchone()[0]:
            live_id = conn.execute(
                "SELECT case_id FROM tribunal.case_records ORDER BY case_id LIMIT 1"
            ).fetchone()
            if live_id is not None:
                return str(live_id[0])
        candidate = conn.execute(
            """SELECT 'DSP-' || lpad(n::text, 6, '0')
               FROM generate_series(900000,999999) AS n
               WHERE NOT EXISTS (
                 SELECT 1 FROM case_archive.archive_cases c
                 WHERE c.archive_case_id='DSP-' || lpad(n::text, 6, '0')
               ) ORDER BY n LIMIT 1"""
        ).fetchone()
        assert candidate is not None
        return str(candidate[0])


def test_migrations_apply_to_empty_database_and_roll_back_cleanly(isolated_migration_database) -> None:
    isolated_url, alembic_url = isolated_migration_database
    run_alembic("upgrade", "head", database_url=alembic_url)
    with psycopg.connect(isolated_url) as conn:
        assert conn.execute("SELECT to_regnamespace('ride_data')").fetchone()[0] == "ride_data"
        assert conn.execute("SELECT to_regnamespace('case_archive')").fetchone()[0] == "case_archive"
        # The archive dashboard reader requires the ruling history added in
        # migration 0005. Keep this explicit so a fresh `upgrade head` proves
        # it creates the relation used by the live read path.
        assert conn.execute(
            "SELECT to_regclass('case_archive.archive_case_rulings')"
        ).fetchone()[0] == "case_archive.archive_case_rulings"
    run_alembic("downgrade", "base", database_url=alembic_url)
    with psycopg.connect(isolated_url) as conn:
        assert conn.execute("SELECT to_regnamespace('ride_data')").fetchone()[0] is None
        assert conn.execute("SELECT to_regnamespace('case_archive')").fetchone()[0] is None
    run_alembic("upgrade", "head", database_url=alembic_url)


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
    with psycopg.connect(DATABASE_URL) as conn:
        archived_user_ids = {
            str(row[0]) for row in conn.execute(
                "SELECT archive_user_id FROM case_archive.archive_user_snapshots"
            )
        }
        archived_ride_ids = {
            str(row[0]) for row in conn.execute(
                "SELECT archive_ride_id FROM case_archive.archive_trip_snapshots"
            )
        }
        archived_evidence_ids = {
            str(row[0]) for row in conn.execute(
                "SELECT archive_evidence_id FROM case_archive.archive_case_evidence"
            )
        }
        policy_ids = {
            str(row[0]) for row in conn.execute(
                "SELECT policy_version_id FROM case_archive.archive_policy_versions"
            )
        }
    assert all(re.fullmatch(r"USR-[RD]-\d{6}", value) for value in archived_user_ids)
    assert all(re.fullmatch(r"RIDE-\d{6}", value) for value in archived_ride_ids)
    assert all(re.fullmatch(r"EV-\d{6}", value) for value in archived_evidence_ids)
    assert all(re.fullmatch(r"POLICY-\d{6}", value) for value in policy_ids)
    assert not any("ARCH-" in value for value in archived_user_ids | archived_ride_ids | archived_evidence_ids | policy_ids)
    with psycopg.connect(DATABASE_URL) as conn:
        archive_case_ids = {
            str(row[0]) for row in conn.execute(
                "SELECT archive_case_id FROM case_archive.archive_cases"
            )
        }
    assert archive_case_ids
    assert all(re.fullmatch(r"DSP-[0-9]{6}", value) for value in archive_case_ids)
    archive_id_constraints = rows(
        """
        SELECT c.conname, pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'case_archive'
          AND c.conname IN (
            'archive_cases_archive_case_id_check',
            'archive_trip_snapshots_archive_ride_id_check',
            'archive_user_snapshots_archive_user_id_check',
            'archive_case_evidence_identifier_check',
            'archive_policy_versions_surrogate_id_check'
          )
        ORDER BY c.conname
        """
    )
    assert len(archive_id_constraints) == 5
    assert all("ARCH" not in str(item["definition"]) for item in archive_id_constraints)
    assert all(re.fullmatch(r"DSP-\d{6}", value) for value in archive_case_ids)
    with psycopg.connect(DATABASE_URL) as conn:
        if conn.execute("SELECT to_regclass('tribunal.case_records')").fetchone()[0]:
            live_case_ids = {row[0] for row in conn.execute("SELECT case_id FROM tribunal.case_records")}
            assert archive_case_ids.isdisjoint(live_case_ids)

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


def test_phase_one_seed_additions_have_ratings_archive_links_and_requested_dates() -> None:
    assert scalar("SELECT count(*) FROM ride_data.users WHERE synthetic IS TRUE") == 100
    assert scalar("SELECT count(*) FROM ride_data.rides WHERE synthetic IS TRUE") == 160
    assert scalar("SELECT count(*) FROM case_archive.archive_cases WHERE synthetic IS TRUE") == 47
    assert scalar("SELECT count(*) FROM ride_data.users WHERE synthetic IS TRUE AND role='rider'") == 50
    assert scalar("SELECT count(*) FROM ride_data.users WHERE synthetic IS TRUE AND role='driver'") == 50

    broken_ratings = rows(
        """
        SELECT r.ride_id FROM ride_data.rides r LEFT JOIN ride_data.ride_ratings a USING (ride_id)
        WHERE r.synthetic IS TRUE GROUP BY r.ride_id,r.ride_status
        HAVING (r.ride_status='completed' AND count(a.rating_id)<>2)
            OR (r.ride_status<>'completed' AND count(a.rating_id)<>0)
        """
    )
    assert broken_ratings == []
    mismatched_averages = rows(
        """
        SELECT p.user_id FROM ride_data.user_profiles p
        JOIN ride_data.users u USING (user_id)
        JOIN (SELECT rated_user_id,round(avg(rating),2) AS received_average
              FROM ride_data.ride_ratings WHERE synthetic IS TRUE GROUP BY rated_user_id) a
          ON a.rated_user_id=p.user_id
        WHERE u.synthetic IS TRUE AND p.synthetic IS TRUE AND p.average_rating<>a.received_average
        """
    )
    assert mismatched_averages == []
    missing_profile_fields = rows(
        """SELECT u.user_id FROM ride_data.users u JOIN ride_data.user_profiles p USING (user_id)
        WHERE u.synthetic IS TRUE AND (
          p.total_trips IS NULL OR p.dispute_history_total IS NULL OR p.dispute_history_upheld IS NULL
          OR p.dispute_history_rejected IS NULL OR p.dispute_history_upheld_against IS NULL
          OR p.fraud_flag_count IS NULL OR p.payment_method IS NULL
          OR (u.role='driver' AND p.vehicle IS NULL) OR (u.role='rider' AND p.vehicle IS NOT NULL)
          OR (p.fraud_flag_count=0 AND p.fraud_flag_details IS NOT NULL)
          OR (p.fraud_flag_count>0 AND p.fraud_flag_details IS NULL)
        )"""
    )
    assert missing_profile_fields == []
    wrong_trip_totals = rows(
        """SELECT u.user_id FROM ride_data.users u JOIN ride_data.user_profiles p USING (user_id)
        LEFT JOIN ride_data.rides r ON (r.rider_user_id=u.user_id OR r.driver_user_id=u.user_id)
          AND r.synthetic IS TRUE
        WHERE u.synthetic IS TRUE GROUP BY u.user_id,p.total_trips,p.lifetime_completed_rides
        HAVING count(r.ride_id)<>p.total_trips OR
          count(r.ride_id) FILTER (WHERE r.ride_status='completed')<>p.lifetime_completed_rides"""
    )
    assert wrong_trip_totals == []

    new_trip_window = rows(
        """SELECT ride_id FROM ride_data.rides WHERE ride_id BETWEEN 'RIDE-000061' AND 'RIDE-000160'
        AND (requested_at::date < DATE '2026-06-01' OR requested_at::date > DATE '2026-08-31')"""
    )
    assert new_trip_window == []
    new_case_window = rows(
        """SELECT c.archive_case_id FROM case_archive.archive_cases c
        JOIN case_archive.archive_trip_snapshots t USING (archive_ride_id)
        WHERE c.bundle_case_key LIKE 'ryde-tribunal-synthetic-archive:seed-case-%%'
          AND substring(c.bundle_case_key from 'seed-case-([0-9]+)$')::integer BETWEEN 33 AND 47
          AND (c.created_at::date NOT BETWEEN DATE '2026-06-01' AND DATE '2026-08-31'
            OR t.trip_at::date NOT BETWEEN DATE '2026-06-01' AND DATE '2026-08-31'
            OR c.created_at<=t.trip_at)"""
    )
    assert new_case_window == []
    categories = {
        str(r["category"]) for r in rows(
            "SELECT DISTINCT category FROM case_archive.archive_cases WHERE bundle_case_key LIKE 'ryde-tribunal-synthetic-archive:seed-case-%%' AND substring(bundle_case_key from 'seed-case-([0-9]+)$')::integer BETWEEN 33 AND 47"
        )
    }
    assert categories == set(CATEGORY_TAGS)
    assert scalar(
        """SELECT count(*) FROM case_archive.archive_cases c
        JOIN case_archive.archive_user_snapshots u ON u.archive_user_id=c.filing_archive_user_id
        WHERE (c.filed_by='rider' AND u.role<>'rider') OR (c.filed_by='driver' AND u.role<>'driver')"""
    ) == 0
    assert scalar(
        """SELECT count(*) FROM case_archive.archive_trip_snapshots t
        JOIN case_archive.archive_user_snapshots r ON r.archive_user_id=t.rider_archive_user_id
        JOIN case_archive.archive_user_snapshots d ON d.archive_user_id=t.driver_archive_user_id
        WHERE t.synthetic IS TRUE AND (t.trip_status='completed' AND
          (t.rider_rating<>d.average_rating OR t.driver_rating<>r.average_rating))"""
    ) == 0
    assert scalar(
        "SELECT count(*) FROM case_archive.archive_case_rulings WHERE ruling_stage='reviewer_approved' AND decision_origin='human'"
    ) > 0
    assert scalar(
        "SELECT count(*) FROM case_archive.archive_case_rulings WHERE ruling_stage='model_proposed' AND decision_origin='agent'"
    ) == 47


def test_archive_rating_columns_match_the_party_receiving_each_rating() -> None:
    assert scalar(
        """SELECT count(*) FROM case_archive.archive_trip_snapshots t
        JOIN case_archive.archive_user_snapshots rider ON rider.archive_user_id=t.rider_archive_user_id
        JOIN case_archive.archive_user_snapshots driver ON driver.archive_user_id=t.driver_archive_user_id
        WHERE t.synthetic IS TRUE AND t.trip_status='completed'
          AND (t.rider_rating<>driver.average_rating OR t.driver_rating<>rider.average_rating)"""
    ) == 0


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
    policy = json.loads((DATABASE_DIR / "seed" / "policy" / "ryde-policy-0.1.1.json").read_text())
    threshold_names = {item["name"] for item in policy["numeric_thresholds"]}
    for name in threshold_names:
        sides = {r["side"] for r in rows("SELECT side FROM ride_data.scenario_tags WHERE threshold_name = %s", (name,))}
        assert sides == {"inside", "outside"}


def test_policy_json_matches_authoritative_markdown() -> None:
    """Check database policy against prose, with the owner-approved D-10 override."""
    repo_root = Path(__file__).resolve().parents[2]
    markdown_path = repo_root / "docs" / "03-mock-policy.md"
    markdown_text = markdown_path.read_text(encoding="utf-8")
    json_path = DATABASE_DIR / "seed" / "policy" / "ryde-policy-0.1.2.json"
    policy = json.loads(json_path.read_text())

    json_rules = {r["id"]: r for r in policy["rules"]}
    expected_thresholds = {
        "route_deviation_pct": 15,
        "unexpected_stop_seconds": 240,
        "driver_wait_seconds": 300,
        "arrival_distance_meters": 100,
        "duration_ratio_pct": 130,
        "photo_window_seconds": 7200,
    }

    rule_re = re.compile(r"^\*\*(RP-[A-Z]+-\d{3})\.\*\*\s+(.+?)(?=\n\n## |\n\*\*RP-|\Z)", re.MULTILINE | re.DOTALL)
    found: dict[str, str] = {}
    for match in rule_re.finditer(markdown_text):
        rule_id = match.group(1)
        text = " ".join(match.group(2).strip().split())
        text = text.replace("*", "").replace("`", "")
        text = text.replace("≥", ">=").replace("≤", "<=")
        found[rule_id] = text

    assert len(found) == 28, f"expected 28 rules in markdown, found {len(found)}"

    # The historical fixture records this D-10 clarification for legacy case coverage.
    # and remains unchanged until the lead updates the prose contract.
    expected_overrides = {
        "RP-ESC-003": (
            "Escalate when the case is high impact (D-10: money >= SGD 25.00, "
            "a safety category that does not meet RP-SAFETY-001 auto-ruling eligibility, "
            "or >=3 disputes by the same party in 30 days)."
        ),
    }
    assert policy["version"] == POLICY_VERSION == "ryde-policy-0.1.2"
    for rule_id, markdown_text in found.items():
        assert rule_id in json_rules, f"rule {rule_id} from markdown missing in JSON"
        actual_text = json_rules[rule_id]["text"]
        expected_text = expected_overrides.get(rule_id, markdown_text)
        assert actual_text == expected_text, (
            f"rule {rule_id} text mismatch.\n"
            f"EXPECTED: {expected_text}\n"
            f"JSON:     {actual_text}"
        )
    assert "fraud assessment" in json_rules["RP-EV-004"]["text"]
    assert "fraud risk" not in json_rules["RP-ESC-003"]["text"]

    for name, expected_value in expected_thresholds.items():
        threshold = next((t for t in policy["numeric_thresholds"] if t["name"] == name), None)
        assert threshold is not None, f"missing numeric_threshold {name}"
        assert threshold["value"] == expected_value, (
            f"threshold {name} value mismatch: expected {expected_value}, got {threshold['value']}"
        )


def test_seeded_policy_versions_preserve_prior_fraud_escalation_snapshot() -> None:
    versions = rows(
        "SELECT policy_version, policy_document FROM case_archive.archive_policy_versions "
        "WHERE policy_version IN ('ryde-policy-0.1.0', 'ryde-policy-0.1.1')"
    )
    documents = {str(row["policy_version"]): row["policy_document"] for row in versions}
    assert set(documents) == {"ryde-policy-0.1.0", "ryde-policy-0.1.1"}
    old_rule = next(rule for rule in documents["ryde-policy-0.1.0"]["rules"] if rule["id"] == "RP-ESC-003")
    current_rule = next(rule for rule in documents["ryde-policy-0.1.1"]["rules"] if rule["id"] == "RP-ESC-003")
    assert "fraud risk >= 0.60" in old_rule["text"]
    assert "fraud risk" not in current_rule["text"]
    current_version = rows(
        "SELECT policy_version, policy_document FROM case_archive.archive_policy_versions "
        "WHERE policy_version = %s", (POLICY_VERSION,)
    )
    assert len(current_version) == 1
    assert current_version[0]["policy_document"]["version"] == POLICY_VERSION


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


def test_seed_reseed_preserves_archive_id_mappings_and_export(tmp_path: Path) -> None:
    def mappings() -> dict[str, tuple[tuple[str, str], ...]]:
        return {
            "users": tuple(sorted(
                (str(row["bundle_user_key"]), str(row["archive_user_id"]))
                for row in rows("SELECT bundle_user_key,archive_user_id FROM case_archive.archive_user_snapshots WHERE bundle_user_key LIKE %s", ("ryde-tribunal-synthetic-archive:seed-%",))
            )),
            "trips": tuple(sorted(
                (str(row["bundle_trip_key"]), str(row["archive_ride_id"]))
                for row in rows("SELECT bundle_trip_key,archive_ride_id FROM case_archive.archive_trip_snapshots WHERE bundle_trip_key LIKE %s", ("ryde-tribunal-synthetic-archive:seed-trip-%",))
            )),
            "cases": tuple(sorted(
                (str(row["bundle_case_key"]), str(row["archive_case_id"]))
                for row in rows("SELECT bundle_case_key,archive_case_id FROM case_archive.archive_cases WHERE bundle_case_key LIKE %s", ("ryde-tribunal-synthetic-archive:seed-case-%",))
            )),
            "evidence": tuple(sorted(
                (str(row["bundle_evidence_key"]), str(row["archive_evidence_id"]))
                for row in rows("SELECT bundle_evidence_key,archive_evidence_id FROM case_archive.archive_case_evidence WHERE bundle_evidence_key LIKE %s", ("ryde-tribunal-synthetic-archive:seed-evidence-%",))
            )),
        }

    before = mappings()
    before_company_zip = tmp_path / "before-company.zip"
    before_archive_zip = tmp_path / "before-archive.zip"
    export_seed_bundles(DATABASE_URL, before_company_zip, before_archive_zip)
    with zipfile.ZipFile(before_archive_zip) as archive:
        before_members = {name: archive.read(name) for name in archive.namelist()}

    seed_database(DATABASE_URL, "ride-data-v1", "case-archive-v1")

    assert mappings() == before
    after_company_zip = tmp_path / "after-company.zip"
    after_archive_zip = tmp_path / "after-archive.zip"
    export_seed_bundles(DATABASE_URL, after_company_zip, after_archive_zip)
    with zipfile.ZipFile(after_archive_zip) as archive:
        after_members = {name: archive.read(name) for name in archive.namelist()}
    assert after_members == before_members
    assert b"ARCH-EV-" not in after_members["evidence.csv"]


def test_reseed_recovers_legacy_missing_case_bundle_keys() -> None:
    before = {
        f"{ARCHIVE_SOURCE_NAMESPACE}:seed-trip-{int(row['seed_index']):06d}": str(row["archive_case_id"])
        for row in rows(
            """SELECT substring(t.bundle_trip_key from 'seed-trip-([0-9]+)$')::integer AS seed_index,
                      c.archive_case_id
               FROM case_archive.archive_cases c
               JOIN case_archive.archive_trip_snapshots t
                 ON t.archive_ride_id=c.archive_ride_id
               WHERE c.synthetic IS TRUE AND t.synthetic IS TRUE
                 AND t.bundle_trip_key LIKE %s
                 AND substring(t.bundle_trip_key from 'seed-trip-([0-9]+)$')::integer
                     BETWEEN 1 AND %s""",
            (f"{ARCHIVE_SOURCE_NAMESPACE}:seed-trip-%", BASE_ARCHIVE_CASE_COUNT),
        )
    }
    assert len(before) == BASE_ARCHIVE_CASE_COUNT
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """UPDATE case_archive.archive_trip_snapshots t
               SET bundle_trip_key='migration-trip-DSP-ARCH-' ||
                   substring(t.bundle_trip_key from 'seed-trip-([0-9]+)$')
               FROM case_archive.archive_cases c
               WHERE t.archive_ride_id=c.archive_ride_id
                 AND c.synthetic IS TRUE AND t.synthetic IS TRUE
                 AND c.bundle_case_key LIKE %s
                 AND substring(t.bundle_trip_key from 'seed-trip-([0-9]+)$')::integer
                     BETWEEN 1 AND %s""",
            (f"{ARCHIVE_SOURCE_NAMESPACE}:seed-case-%", BASE_ARCHIVE_CASE_COUNT),
        )
        conn.execute(
            """UPDATE case_archive.archive_cases c SET bundle_case_key=NULL
               FROM case_archive.archive_trip_snapshots t
               WHERE t.archive_ride_id=c.archive_ride_id
                 AND c.synthetic IS TRUE AND t.synthetic IS TRUE
                 AND t.bundle_trip_key LIKE 'migration-trip-DSP-ARCH-%'""",
        )

    seed_database(DATABASE_URL, "ride-data-v1", "case-archive-v1")

    after = {
        str(row["bundle_trip_key"]): str(row["archive_case_id"])
        for row in rows(
            """SELECT t.bundle_trip_key,c.archive_case_id
               FROM case_archive.archive_cases c
               JOIN case_archive.archive_trip_snapshots t
                 ON t.archive_ride_id=c.archive_ride_id
               WHERE c.synthetic IS TRUE AND t.synthetic IS TRUE
                 AND t.bundle_trip_key LIKE %s
                 AND substring(t.bundle_trip_key from 'seed-trip-([0-9]+)$')::integer
                     BETWEEN 1 AND %s""",
            (f"{ARCHIVE_SOURCE_NAMESPACE}:seed-trip-%", BASE_ARCHIVE_CASE_COUNT),
        )
    }
    assert after == before
    assert scalar("SELECT count(*) FROM case_archive.archive_cases WHERE synthetic IS TRUE") == 47


def test_reseed_preserves_company_rows_and_refreshes_synthetic_rows() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "INSERT INTO ride_data.users (user_id, role, display_handle, full_name, created_at, account_status, synthetic) "
            "VALUES ('USR-R-900001', 'rider', NULL, 'Example Imported Rider', NULL, NULL, false)"
        )
        conn.execute(
            "INSERT INTO ride_data.user_profiles (user_id, account_age_days, lifetime_completed_rides, average_rating, rating_trend, synthetic, total_trips) "
            "VALUES ('USR-R-900001', 30, NULL, 4.25, NULL, false, 8)"
        )
        conn.execute(
            "INSERT INTO ride_data.user_dispute_counters (user_id, disputes_30d, disputes_180d, route_deviation_count, no_show_count, property_damage_count, safety_incident_count, synthetic) "
            "VALUES ('USR-R-900001', NULL, NULL, NULL, NULL, NULL, NULL, false)"
        )
    try:
        seed_database(DATABASE_URL, "ride-data-v1", "case-archive-v1")
        assert scalar("SELECT count(*) FROM ride_data.users WHERE user_id = 'USR-R-900001'") == 1
        assert scalar("SELECT count(*) FROM ride_data.users WHERE synthetic IS TRUE") == 100
        assert scalar("SELECT count(*) FROM ride_data.rides WHERE synthetic IS TRUE") == 160
        assert scalar("SELECT count(*) FROM case_archive.archive_cases WHERE synthetic IS TRUE") == 47
    finally:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute("DELETE FROM ride_data.user_dispute_counters WHERE user_id = 'USR-R-900001'")
            conn.execute("DELETE FROM ride_data.user_profiles WHERE user_id = 'USR-R-900001'")
            conn.execute("DELETE FROM ride_data.users WHERE user_id = 'USR-R-900001'")


def test_eleven_accessors_return_validated_models_and_no_write_surface() -> None:
    assert set(reader.__all__) == {
        "get_ride",
        "get_route",
        "get_gps_samples",
        "get_chat_log",
        "get_app_events",
        "get_fare_breakdown",
        "get_profile",
        "get_archive_case",
        "list_archive_disputes",
        "search_archive",
        "search_rides",
    }
    exported_functions = {name for name, obj in inspect.getmembers(reader, inspect.isfunction) if not name.startswith("_")}
    assert exported_functions == set(reader.__all__)
    assert not any(re.search(r"persist|insert|update|delete|write", name, re.I) for name in exported_functions)

    assert reader.get_ride("RIDE-000001").ride_id == "RIDE-000001"
    assert reader.get_route("RIDE-000001").waypoints
    assert reader.get_gps_samples("RIDE-000001")
    assert reader.get_chat_log("RIDE-000001")
    assert reader.get_app_events("RIDE-000001") == []
    assert reader.get_fare_breakdown("RIDE-000001").promos
    profile = reader.get_profile("USR-R-000001")
    assert profile.dispute_counts.disputes_180d >= 0
    assert profile.company_dispute_history is not None
    first_archive_id = str(scalar("SELECT archive_case_id FROM case_archive.archive_cases ORDER BY created_at, archive_case_id LIMIT 1"))
    assert reader.get_archive_case(first_archive_id).decision.verdict
    archive_disputes = reader.list_archive_disputes(limit=3)
    assert archive_disputes
    assert re.fullmatch(r"DSP-\d{6}", archive_disputes[0].archive_case_id)
    assert reader.search_archive("route_deviation", {"category": "route_deviation"}, 3)

    trip_choices = reader.search_rides("RIDE-000001", limit=1)
    assert len(trip_choices) == 1
    assert trip_choices[0].ride_id == "RIDE-000001"
    assert trip_choices[0].pickup_label
    assert trip_choices[0].dropoff_label
    recent_choices = reader.search_rides("", limit=2)
    assert len(recent_choices) == 2
    assert recent_choices[0].booked_at >= recent_choices[1].booked_at

    with pytest.raises(ValidationError):
        Money.model_validate({"amount_cents": "325", "currency": "SGD"})
    assert RideHeader.model_validate(
        {
            "ride_id": "RIDE-000001",
            "rider_user_id": "USR-R-000001",
            "driver_user_id": "USR-D-000001",
            "requested_at": datetime(2026, 9, 22, tzinfo=timezone.utc),
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
    ).synthetic is False


def test_canonical_no_show_category_name_is_no_show_charge() -> None:
    policy_path = DATABASE_DIR / "seed/policy/ryde-policy-0.1.1.json"
    policy = json.loads(policy_path.read_text())
    assert all(rule["section"] != "no_show" for rule in policy["rules"])
    assert any(rule["section"] == "no_show_charge" for rule in policy["rules"])
    assert "no_show" not in CATEGORY_TAGS


def test_archive_accessor_rejects_live_id() -> None:
    live_or_unused_id = live_or_unused_case_id()
    with pytest.raises(LookupError):
        reader.get_archive_case(live_or_unused_id)
    with pytest.raises(ValueError):
        reader.get_archive_case("RIDE-000001")
    with pytest.raises(ValueError):
        reader.get_archive_case("DSP-ARCH-000017")
    archive_id = str(scalar("SELECT archive_case_id FROM case_archive.archive_cases ORDER BY created_at, archive_case_id OFFSET 16 LIMIT 1"))
    assert reader.get_archive_case(archive_id).archive_case_id == archive_id


def test_search_archive_rejects_live_id_in_features() -> None:
    live_or_unused_id = live_or_unused_case_id()
    with pytest.raises(ValueError):
        reader.search_archive("route_deviation", {"case_id": live_or_unused_id}, 5)
    with pytest.raises(ValueError):
        reader.search_archive("route_deviation", {"ride_id": "RIDE-000001"}, 5)
    assert reader.search_archive("route_deviation", {"category": "route_deviation"}, 5)


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
                "INSERT INTO case_archive.archive_cases (archive_case_id, archive_ride_id, category, subject, filed_by, created_at, policy_version, synthetic) VALUES ('DSP-999999', 'RIDE-999999', 'route_deviation', 'blocked', 'rider', now(), 'ryde-policy-0.1.0', true)"
            )
        conn.rollback()
