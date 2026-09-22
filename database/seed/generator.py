from __future__ import annotations

import hashlib
import json
import os
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

DEFAULT_DATABASE_URL = "postgresql:///ryde_tribunal"
DEFAULT_RIDE_SEED = "ride-data-v1"
DEFAULT_ARCHIVE_SEED = "case-archive-v1"
POLICY_PATH = Path(__file__).parent / "policy" / "ryde-policy-0.1.0.json"
POLICY_VERSION = "ryde-policy-0.1.0"
REFERENCE_NOW = datetime(2026, 9, 22, 0, 0, tzinfo=UTC)

LANDMARKS = [
    ("marina_bay", Decimal("1.283000"), Decimal("103.860000")),
    ("orchard", Decimal("1.304800"), Decimal("103.831800")),
    ("changi_airport", Decimal("1.364400"), Decimal("103.991500")),
    ("jurong_east", Decimal("1.333100"), Decimal("103.742300")),
    ("woodlands", Decimal("1.436000"), Decimal("103.786000")),
    ("tampines", Decimal("1.349600"), Decimal("103.956800")),
    ("sentosa", Decimal("1.249400"), Decimal("103.830300")),
    ("punggol", Decimal("1.405100"), Decimal("103.902300")),
]

CATEGORY_TAGS = ["route_deviation", "no_show", "property_damage", "safety_incident"]


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _dt_for_ride(rng: random.Random, index: int) -> datetime:
    day_offset = index % 70
    if rng.random() < 0.62:
        hour = rng.choice([7, 8, 17, 18, 19])
    else:
        hour = rng.choice([10, 11, 13, 14, 21, 22])
    minute = rng.randrange(0, 60)
    return REFERENCE_NOW - timedelta(days=69 - day_offset) + timedelta(hours=hour, minutes=minute)


def _nudge(value: Decimal, steps: int) -> Decimal:
    return value + Decimal(steps) * Decimal("0.001000")


def _policy_document() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _thresholds() -> dict[str, Decimal]:
    policy = _policy_document()
    return {item["name"]: Decimal(str(item["value"])) for item in policy["numeric_thresholds"]}


def _clear(conn: psycopg.Connection[Any]) -> None:
    tables = [
        "ride_data.ingest_audit",
        "ride_data.scenario_tags",
        "ride_data.ride_external_conditions",
        "ride_data.ride_device_signals",
        "ride_data.ride_promo_applications",
        "ride_data.ride_fare_adjustments",
        "ride_data.ride_fare_breakdowns",
        "ride_data.ride_call_attempts",
        "ride_data.ride_chat_messages",
        "ride_data.ride_stops",
        "ride_data.ride_gps_samples",
        "ride_data.ride_waypoints",
        "ride_data.ride_route_plans",
        "ride_data.rides",
        "ride_data.user_dispute_counters",
        "ride_data.user_rating_history",
        "ride_data.user_profiles",
        "ride_data.users",
        "case_archive.archive_precedent_index",
        "case_archive.archive_appeals",
        "case_archive.archive_human_reviews",
        "case_archive.archive_case_decisions",
        "case_archive.archive_case_evidence",
        "case_archive.archive_case_classifications",
        "case_archive.archive_cases",
        "case_archive.archive_policy_versions",
    ]
    conn.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")


def _insert_users(conn: psycopg.Connection[Any], rng: random.Random) -> None:
    rows = []
    profiles = []
    ratings = []
    counters = []
    created_base = REFERENCE_NOW - timedelta(days=950)
    for role, prefix in (("rider", "USR-R"), ("driver", "USR-D")):
        for i in range(1, 41):
            user_id = f"{prefix}-{i:06d}"
            age_days = 90 + ((i * 17) % 1100)
            created_at = created_base + timedelta(days=i * 3)
            rows.append((user_id, role, f"{role}_{i:06d}", created_at, "active", True))
            avg = Decimal("4.00") + Decimal(rng.randrange(0, 95)) / Decimal("100")
            trend = ["stable", "rising", "falling", "volatile"][i % 4]
            profiles.append((user_id, age_days, 50 + i * 7, avg, trend, True))
            counters.append((user_id, i % 4, i % 9, i % 5, (i + 1) % 4, (i + 2) % 3, (i + 3) % 2, True))
            for j in range(4):
                ratings.append((user_id, REFERENCE_NOW - timedelta(days=90 - j * 20, hours=i), avg - Decimal(j) / Decimal("20"), 8 + j, True))
    conn.cursor().executemany("INSERT INTO ride_data.users VALUES (%s,%s,%s,%s,%s,%s)", rows)
    conn.cursor().executemany("INSERT INTO ride_data.user_profiles VALUES (%s,%s,%s,%s,%s,%s)", profiles)
    conn.cursor().executemany(
        "INSERT INTO ride_data.user_rating_history (user_id, rating_at, rating, sample_size, synthetic) VALUES (%s,%s,%s,%s,%s)",
        ratings,
    )
    conn.cursor().executemany("INSERT INTO ride_data.user_dispute_counters VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", counters)


def _boundary_values(index: int, thresholds: dict[str, Decimal]) -> tuple[dict[str, Decimal], list[tuple[str, str, Decimal, Decimal]]]:
    planned_distance = Decimal("10000")
    planned_duration = Decimal("1200")
    values = {
        "actual_distance": planned_distance * Decimal("1.08"),
        "actual_duration": planned_duration * Decimal("1.05"),
        "stop_seconds": Decimal("90"),
        "wait_seconds": Decimal("180"),
        "arrival_meters": Decimal("80"),
        "photo_seconds": Decimal("3600"),
    }
    tags: list[tuple[str, str, Decimal, Decimal]] = []
    specs = [
        (1, "route_deviation_pct", "inside", Decimal("14.9")),
        (2, "route_deviation_pct", "outside", Decimal("15.1")),
        (3, "unexpected_stop_seconds", "inside", thresholds["unexpected_stop_seconds"] - 1),
        (4, "unexpected_stop_seconds", "outside", thresholds["unexpected_stop_seconds"] + 1),
        (5, "driver_wait_seconds", "inside", thresholds["driver_wait_seconds"] - 1),
        (6, "driver_wait_seconds", "outside", thresholds["driver_wait_seconds"] + 1),
        (7, "arrival_distance_meters", "inside", thresholds["arrival_distance_meters"] - 1),
        (8, "arrival_distance_meters", "outside", thresholds["arrival_distance_meters"] + 1),
        (9, "duration_ratio_pct", "inside", Decimal("129")),
        (10, "duration_ratio_pct", "outside", Decimal("131")),
        (11, "photo_window_seconds", "inside", thresholds["photo_window_seconds"] - 1),
        (12, "photo_window_seconds", "outside", thresholds["photo_window_seconds"] + 1),
    ]
    for ride_index, threshold_name, side, observed in specs:
        if index != ride_index:
            continue
        threshold = thresholds[threshold_name]
        tags.append((threshold_name, side, observed, threshold))
        if threshold_name == "route_deviation_pct":
            values["actual_distance"] = planned_distance * (Decimal("1") + observed / Decimal("100"))
        elif threshold_name == "unexpected_stop_seconds":
            values["stop_seconds"] = observed
        elif threshold_name == "driver_wait_seconds":
            values["wait_seconds"] = observed
        elif threshold_name == "arrival_distance_meters":
            values["arrival_meters"] = observed
        elif threshold_name == "duration_ratio_pct":
            values["actual_duration"] = planned_duration * observed / Decimal("100")
        elif threshold_name == "photo_window_seconds":
            values["photo_seconds"] = observed
    return values, tags


def _insert_rides(conn: psycopg.Connection[Any], rng: random.Random, ride_seed: str, archive_seed: str) -> None:
    thresholds = _thresholds()
    ev_counter = 1
    counts: dict[str, int] = {}

    for i in range(1, 61):
        ride_id = f"RIDE-{i:06d}"
        rider_user_id = f"USR-R-{((i - 1) % 40) + 1:06d}"
        driver_user_id = f"USR-D-{((i * 3 - 1) % 40) + 1:06d}"
        requested_at = _dt_for_ride(rng, i)
        accepted_at = requested_at + timedelta(minutes=2)
        pickup_at = accepted_at + timedelta(minutes=5)
        planned_distance = Decimal(7000 + (i % 12) * 750)
        planned_duration = Decimal(900 + (i % 10) * 90)
        boundary, tags = _boundary_values(i, thresholds)
        actual_distance = boundary["actual_distance"] if tags else planned_distance * (Decimal("1.02") + Decimal(i % 9) / Decimal("100"))
        actual_duration = boundary["actual_duration"] if tags else planned_duration * (Decimal("1.01") + Decimal(i % 12) / Decimal("100"))
        dropoff_at = pickup_at + timedelta(seconds=int(actual_duration))
        quoted_fare = 850 + int(planned_distance / Decimal("25"))
        pickup = LANDMARKS[(i - 1) % len(LANDMARKS)]
        dropoff = LANDMARKS[(i + 2) % len(LANDMARKS)]
        category_tag = CATEGORY_TAGS[(i - 1) % len(CATEGORY_TAGS)]
        ride_status = "cancelled_after_arrival" if category_tag == "no_show" and i % 5 == 0 else "completed"

        conn.execute(
            "INSERT INTO ride_data.rides VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (ride_id, rider_user_id, driver_user_id, requested_at, accepted_at, pickup_at, dropoff_at, ride_status, "standard", int(planned_distance), int(planned_duration), quoted_fare, "SGD", True),
        )
        conn.execute(
            "INSERT INTO ride_data.ride_route_plans VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                ride_id,
                pickup[0],
                pickup[1],
                pickup[2],
                dropoff[0],
                dropoff[1],
                dropoff[2],
                int(planned_distance),
                int(actual_distance),
                int(planned_duration),
                int(actual_duration),
                int(boundary["arrival_meters"]),
                int(boundary["wait_seconds"]),
                True,
            ),
        )

        for route_kind, distance in (("planned", planned_distance), ("actual", actual_distance)):
            for seq in range(3):
                lat = _nudge(pickup[1], seq + (1 if route_kind == "actual" else 0))
                lon = _nudge(pickup[2], seq + (2 if route_kind == "actual" else 0))
                conn.execute(
                    "INSERT INTO ride_data.ride_waypoints (ride_id, route_kind, sequence_no, lat, lon, label, recorded_at, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (ride_id, route_kind, seq, lat, lon, f"{route_kind}_point_{seq}", pickup_at + timedelta(minutes=seq * 4), True),
                )
        for seq in range(4):
            conn.execute(
                "INSERT INTO ride_data.ride_gps_samples (ride_id, sample_at, lat, lon, accuracy_meters, speed_meters_per_second, collector, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (ride_id, pickup_at + timedelta(minutes=seq * 5), _nudge(pickup[1], seq), _nudge(pickup[2], seq), Decimal("4.50") + Decimal(seq) / Decimal("10"), Decimal("8.00") + Decimal(seq), "app_v3", True),
            )
        if int(boundary["stop_seconds"]) > 0:
            stop_start = pickup_at + timedelta(minutes=8)
            conn.execute(
                "INSERT INTO ride_data.ride_stops (ride_id, started_at, ended_at, duration_seconds, lat, lon, rider_requested, note, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (ride_id, stop_start, stop_start + timedelta(seconds=int(boundary["stop_seconds"])), int(boundary["stop_seconds"]), _nudge(pickup[1], 2), _nudge(pickup[2], 2), i % 6 == 0, "synthetic stop telemetry", True),
            )

        for role, text in (("rider", "pickup pin confirmed"), ("driver", "i am on the way through platform route")):
            ev_id = f"EV-{ev_counter:06d}"
            ev_counter += 1
            conn.execute(
                "INSERT INTO ride_data.ride_chat_messages VALUES (%s,%s,%s,%s,%s,%s)",
                (ev_id, ride_id, role, requested_at + timedelta(minutes=3 + ev_counter % 4), text, True),
            )
        ev_id = f"EV-{ev_counter:06d}"
        ev_counter += 1
        conn.execute(
            "INSERT INTO ride_data.ride_call_attempts VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (ev_id, ride_id, "driver", "rider", pickup_at + timedelta(seconds=60), "unanswered", 0, True),
        )
        ev_id = f"EV-{ev_counter:06d}"
        ev_counter += 1
        conn.execute(
            "INSERT INTO ride_data.ride_device_signals VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (ev_id, ride_id, rider_user_id, "damage_photo", dropoff_at + timedelta(seconds=int(boundary["photo_seconds"])), Jsonb({"seconds_after_trip_end": int(boundary["photo_seconds"]), "storage_key": f"synthetic/{ride_id}/damage-photo"}), True),
        )

        surge = Decimal("1.20") if i % 7 == 0 else Decimal("1.00")
        base = 350
        distance_fare = int(actual_distance / Decimal("30"))
        time_fare = int(actual_duration / Decimal("8"))
        waiting_fare = max(0, int(boundary["stop_seconds"] - 120)) * 2
        surge_fare = int((base + distance_fare + time_fare) * (surge - Decimal("1.00")))
        cancellation = 500 if ride_status == "cancelled_after_arrival" else 0
        platform = 80
        total = base + distance_fare + time_fare + waiting_fare + surge_fare + cancellation + platform
        conn.execute(
            "INSERT INTO ride_data.ride_fare_breakdowns (ride_id, base_fare_cents, distance_fare_cents, time_fare_cents, waiting_fare_cents, surge_multiplier, surge_fare_cents, cancellation_fee_cents, platform_fee_cents, total_fare_cents, currency, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (ride_id, base, distance_fare, time_fare, waiting_fare, surge, surge_fare, cancellation, platform, total, "SGD", True),
        )
        conn.execute(
            "INSERT INTO ride_data.ride_fare_adjustments (ride_id, adjustment_type, amount_cents, currency, applied_at, synthetic) VALUES (%s,%s,%s,%s,%s,%s)",
            (ride_id, "rounding", i % 5, "SGD", dropoff_at, True),
        )
        conn.execute(
            "INSERT INTO ride_data.ride_promo_applications (ride_id, promo_code, amount_cents, currency, applied_at, synthetic) VALUES (%s,%s,%s,%s,%s,%s)",
            (ride_id, f"SYNTH{i % 6:02d}", 100 + (i % 4) * 50, "SGD", requested_at, True),
        )
        conn.execute(
            "INSERT INTO ride_data.ride_external_conditions (ride_id, condition_type, observed_at, source_label, payload, synthetic) VALUES (%s,%s,%s,%s,%s,%s)",
            (ride_id, "traffic" if i % 3 else "road_closure", requested_at, "synthetic_condition_feed", Jsonb({"congestion_index": (i % 10) / 10, "route_notice": "synthetic"}), True),
        )
        conn.execute(
            "INSERT INTO ride_data.scenario_tags (ride_id, tag, threshold_name, side, observed_value, threshold_value, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (ride_id, f"category_{category_tag}", None, "coverage", None, None, True),
        )
        for threshold_name, side, observed, threshold in tags:
            conn.execute(
                "INSERT INTO ride_data.scenario_tags (ride_id, tag, threshold_name, side, observed_value, threshold_value, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (ride_id, f"boundary_{threshold_name}_{side}", threshold_name, side, observed, threshold, True),
            )

    for table in [
        "rides", "ride_route_plans", "ride_waypoints", "ride_gps_samples", "ride_stops",
        "ride_chat_messages", "ride_call_attempts", "ride_fare_breakdowns", "ride_fare_adjustments",
        "ride_promo_applications", "ride_device_signals", "ride_external_conditions", "scenario_tags",
    ]:
        counts[table] = conn.execute(f"SELECT count(*) FROM ride_data.{table}").fetchone()[0]
    dataset_hash = hashlib.sha256(json.dumps(counts, sort_keys=True).encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT INTO ride_data.ingest_audit (generator_name, ride_seed, archive_seed, generated_at, policy_version, row_counts, dataset_sha256, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        ("database.seed.generator", ride_seed, archive_seed, REFERENCE_NOW, POLICY_VERSION, Jsonb(counts), dataset_hash, True),
    )


def _insert_archive(conn: psycopg.Connection[Any], rng: random.Random) -> None:
    policy = _policy_document()
    policy_versions = [
        ("ryde-policy-0.0.8", "ARCH-POLICY-000008", REFERENCE_NOW - timedelta(days=540), REFERENCE_NOW - timedelta(days=360), policy),
        ("ryde-policy-0.0.9", "ARCH-POLICY-000009", REFERENCE_NOW - timedelta(days=360), REFERENCE_NOW - timedelta(days=180), policy),
        ("ryde-policy-0.1.0", "ARCH-POLICY-000010", REFERENCE_NOW - timedelta(days=180), None, policy),
    ]
    conn.cursor().executemany(
        "INSERT INTO case_archive.archive_policy_versions VALUES (%s,%s,%s,%s,%s,%s)",
        [(name, version_id, start, end, Jsonb(doc), True) for name, version_id, start, end, doc in policy_versions],
    )
    reason_codes = ["policy_misapplied", "evidence_misweighted", "evidence_missing", "fraud_suspected", "goodwill", "safety_override", "other"]
    for i in range(1, 33):
        case_id = f"DSP-ARCH-{i:06d}"
        ride_id = f"RIDE-ARCH-{i:06d}"
        category = CATEGORY_TAGS[(i - 1) % len(CATEGORY_TAGS)]
        created_at = REFERENCE_NOW - timedelta(days=540 - i * 16)
        policy_version = policy_versions[(i - 1) % len(policy_versions)][0]
        subject = f"synthetic {category.replace('_', ' ')} precedent"
        human_touched = i <= 14
        decision_origin = "human" if human_touched else "agent"
        verdict = ["refund", "compensation", "no_action", "escalated"][i % 4]
        ruling_type = "no_action" if verdict == "escalated" else verdict
        confidence = None if human_touched and i % 5 == 0 else Decimal("0.610") + Decimal((i * 7) % 35) / Decimal("100")
        amount = 0 if ruling_type == "no_action" else 200 + (i % 12) * 125
        conn.execute(
            "INSERT INTO case_archive.archive_cases VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (case_id, ride_id, category, subject, "rider" if i % 3 else "driver", created_at, policy_version, True),
        )
        conn.execute(
            "INSERT INTO case_archive.archive_case_classifications VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (case_id, category, Jsonb(["synthetic", "precedent"]), subject, amount, Decimal((i % 8)) / Decimal("10"), True),
        )
        for j, evidence_class in enumerate(["gps_telemetry", "fare", "chat_log"]):
            evidence_id = f"ARCH-EV-{i:06d}-{j:02d}"
            conn.execute(
                "INSERT INTO case_archive.archive_case_evidence VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    evidence_id,
                    case_id,
                    evidence_class,
                    "system_record" if evidence_class != "chat_log" else "rider_submitted",
                    created_at + timedelta(minutes=j * 5),
                    Jsonb({"collector": "synthetic_archive", "table": evidence_class}),
                    Jsonb({"status": "verified" if evidence_class != "chat_log" else "unverified", "method": "synthetic", "uncertainty_pct": 2.5 + j}),
                    "both",
                    Jsonb({"summary": f"synthetic {evidence_class} archive record", "archive_ride_id": ride_id}),
                    True,
                ),
            )
        conn.execute(
            "INSERT INTO case_archive.archive_case_decisions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (case_id, verdict, ruling_type, f"synthetic advisory action for {category}", amount, "SGD", confidence, decision_origin, created_at + timedelta(hours=2), True),
        )
        conn.execute(
            "INSERT INTO case_archive.archive_human_reviews (archive_case_id, human_reviewed, changed_fields, reason_code, rationale, agreed_with_agent, reweighted_evidence, reviewed_at, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                case_id,
                human_touched,
                Jsonb(["recommended_amount_cents"] if human_touched and i % 2 == 0 else []),
                reason_codes[i % len(reason_codes)] if human_touched else None,
                "synthetic human-review calibration record" if human_touched else "synthetic fully automated archive record",
                (i % 3 != 0) if human_touched else None,
                Jsonb([f"ARCH-EV-{i:06d}-00"] if human_touched else []),
                created_at + timedelta(hours=4) if human_touched else None,
                True,
            ),
        )
        if i % 6 == 0:
            conn.execute(
                "INSERT INTO case_archive.archive_appeals (archive_case_id, appealed_at, appeal_reason, appeal_status, synthetic) VALUES (%s,%s,%s,%s,%s)",
                (case_id, created_at + timedelta(days=3), "synthetic appeal reason", "closed", True),
            )
        conn.execute(
            "INSERT INTO case_archive.archive_precedent_index (archive_case_id, category, feature_vector, summary, policy_version, synthetic) VALUES (%s,%s,%s,%s,%s,%s)",
            (case_id, category, Jsonb({"category": category, "amount_bucket": amount // 500, "human_touched": human_touched}), f"advisory synthetic precedent {case_id}", policy_version, True),
        )


def seed_database(database_url: str | None = None, ride_seed: str | None = None, archive_seed: str | None = None) -> None:
    database_url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    ride_seed = ride_seed or os.getenv("RIDE_DATA_SEED", DEFAULT_RIDE_SEED)
    archive_seed = archive_seed or os.getenv("CASE_ARCHIVE_SEED", DEFAULT_ARCHIVE_SEED)
    rng = _rng(f"{ride_seed}:{archive_seed}")
    with psycopg.connect(database_url) as conn:
        _clear(conn)
        _insert_users(conn, rng)
        _insert_archive(conn, rng)
        _insert_rides(conn, rng, ride_seed, archive_seed)
        conn.commit()


def main() -> None:
    seed_database()


if __name__ == "__main__":
    main()
