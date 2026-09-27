from __future__ import annotations

import hashlib
import json
import os
import random
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

DEFAULT_DATABASE_URL = "postgresql:///ryde_tribunal"
DEFAULT_RIDE_SEED = "ride-data-v1"
DEFAULT_ARCHIVE_SEED = "case-archive-v1"
POLICY_PATH = Path(__file__).parent / "policy" / "ryde-policy-0.1.2.json"
POLICY_VERSION = "ryde-policy-0.1.2"
ARCHIVE_SOURCE_NAMESPACE = "ryde-tribunal-synthetic-archive"
RIDE_SOURCE_NAMESPACE = "ryde-tribunal-synthetic-seed"
REFERENCE_NOW = datetime(2026, 9, 22, 0, 0, tzinfo=UTC)
SINGAPORE = ZoneInfo("Asia/Singapore")

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

CATEGORY_TAGS = [
    "route_deviation", "no_show_charge", "fare_calculation", "other_cancellation_fee",
    "property_damage", "safety_incident", "lost_item", "conduct_complaint",
]
BASE_RIDER_COUNT = 40
BASE_DRIVER_COUNT = 40
ADDITIONAL_USER_COUNT = 20
BASE_RIDE_COUNT = 60
ADDITIONAL_RIDE_COUNT = 100
BASE_ARCHIVE_CASE_COUNT = 32
ADDITIONAL_ARCHIVE_CASE_COUNT = 15


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _dt_for_ride(rng: random.Random, index: int) -> datetime:
    if index > BASE_RIDE_COUNT:
        day_offset = (index - 61) % 92
        hour = rng.choice([7, 8, 10, 13, 17, 18, 20])
        local_time = datetime(2026, 6, 1, tzinfo=SINGAPORE) + timedelta(
            days=day_offset, hours=hour, minutes=rng.randrange(60)
        )
        return local_time.astimezone(UTC)
    day_offset = index % 70
    if rng.random() < 0.62:
        hour = rng.choice([7, 8, 17, 18, 19])
    else:
        hour = rng.choice([10, 11, 13, 14, 21, 22])
    minute = rng.randrange(0, 60)
    return REFERENCE_NOW - timedelta(days=69 - day_offset) + timedelta(hours=hour, minutes=minute)


def _archive_case_times(index: int) -> tuple[datetime, datetime]:
    """Return trip and filing times while retaining the original archive dates."""
    if index <= BASE_ARCHIVE_CASE_COUNT:
        created_at = REFERENCE_NOW - timedelta(days=540 - index * 16)
        return created_at - timedelta(days=1 + index % 8), created_at
    trip_day = (index - BASE_ARCHIVE_CASE_COUNT - 1) * 4
    trip_at = datetime(2026, 6, 1, 10, tzinfo=UTC) + timedelta(days=trip_day)
    created_at = trip_at + timedelta(days=1 + (index % 5))
    return trip_at, created_at


def _nudge(value: Decimal, steps: int) -> Decimal:
    return value + Decimal(steps) * Decimal("0.001000")


def _policy_document() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _policy_document_version(version: str) -> dict[str, Any]:
    path = Path(__file__).parent / "policy" / f"{version}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _thresholds() -> dict[str, Decimal]:
    policy = _policy_document()
    return {item["name"]: Decimal(str(item["value"])) for item in policy["numeric_thresholds"]}


def _clear(conn: psycopg.Connection[Any]) -> dict[str, dict[str, str]]:
    ride_tables = [
        "ride_data.ingest_audit",
        "ride_data.scenario_tags",
        "ride_data.ride_app_events",
        "ride_data.ride_external_conditions",
        "ride_data.ride_device_signals",
        "ride_data.ride_promo_applications",
        "ride_data.ride_fare_adjustments",
        "ride_data.ride_fare_breakdowns",
        "ride_data.ride_ratings",
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
    ]
    archive_tables = [
        "case_archive.archive_precedent_index",
        "case_archive.archive_appeals",
        "case_archive.archive_case_rulings",
        "case_archive.archive_human_reviews",
        "case_archive.archive_case_decisions",
        "case_archive.archive_case_evidence",
        "case_archive.archive_case_classifications",
        "case_archive.archive_cases",
        "case_archive.archive_trip_snapshots",
        "case_archive.archive_user_snapshots",
        "case_archive.archive_policy_versions",
    ]
    preserved_ids: dict[str, dict[str, str]] = {
        "cases": {}, "users": {}, "trips": {}, "evidence": {},
    }
    legacy_trip_key_prefix = "migration-trip-DSP-ARCH-"
    case_rows = conn.execute(
        """SELECT c.bundle_case_key, c.archive_case_id, t.bundle_trip_key
           FROM case_archive.archive_cases c
           LEFT JOIN case_archive.archive_trip_snapshots t
             ON t.archive_ride_id = c.archive_ride_id
           WHERE c.bundle_case_key LIKE %s
              OR (c.bundle_case_key IS NULL AND c.synthetic IS TRUE
                  AND t.synthetic IS TRUE AND (
                    t.bundle_trip_key LIKE %s OR t.bundle_trip_key LIKE %s
                  ))""",
        (
            f"{ARCHIVE_SOURCE_NAMESPACE}:seed-case-%",
            f"{ARCHIVE_SOURCE_NAMESPACE}:seed-trip-%",
            f"{legacy_trip_key_prefix}%",
        ),
    ).fetchall()
    trip_key_prefix = f"{ARCHIVE_SOURCE_NAMESPACE}:seed-trip-"
    for key, value, trip_key in case_rows:
        # Older generated snapshots did not store the case bundle key. Recover it
        # only when the case links to a synthetic trip with one of our exact seeded
        # keys and six-digit index. The migration key supports databases seeded before
        # archive bundle keys were added. This avoids inferring identity from content.
        if key is None and isinstance(trip_key, str):
            if trip_key.startswith(trip_key_prefix):
                suffix = trip_key[len(trip_key_prefix):]
            elif trip_key.startswith(legacy_trip_key_prefix):
                suffix = trip_key[len(legacy_trip_key_prefix):]
            else:
                suffix = ""
            if len(suffix) == 6 and suffix.isdigit():
                key = f"{ARCHIVE_SOURCE_NAMESPACE}:seed-case-{suffix}"
        if key and value.startswith("DSP-") and value[4:].isdigit():
            previous = preserved_ids["cases"].get(key)
            if previous is not None and previous != value:
                raise RuntimeError(f"duplicate seeded case mapping for {key!r}")
            preserved_ids["cases"][key] = value
    for key, value in conn.execute(
        "SELECT bundle_user_key, archive_user_id FROM case_archive.archive_user_snapshots "
        "WHERE bundle_user_key LIKE %s",
        (f"{ARCHIVE_SOURCE_NAMESPACE}:seed-%",),
    ).fetchall():
        if key and value.startswith(("USR-R-", "USR-D-")):
            preserved_ids["users"][key] = value
    for key, value in conn.execute(
        "SELECT bundle_trip_key, archive_ride_id FROM case_archive.archive_trip_snapshots "
        "WHERE bundle_trip_key LIKE %s",
        (f"{ARCHIVE_SOURCE_NAMESPACE}:seed-trip-%",),
    ).fetchall():
        if key and value.startswith("RIDE-") and value[5:].isdigit():
            preserved_ids["trips"][key] = value
    for key, value in conn.execute(
        "SELECT bundle_evidence_key, archive_evidence_id FROM case_archive.archive_case_evidence "
        "WHERE bundle_evidence_key LIKE %s",
        (f"{ARCHIVE_SOURCE_NAMESPACE}:seed-evidence-%",),
    ).fetchall():
        if key and value.startswith("EV-") and value[3:].isdigit():
            preserved_ids["evidence"][key] = value
    company_rows_exist = conn.execute(
        """
        SELECT EXISTS (
          SELECT 1 FROM ride_data.users WHERE synthetic IS FALSE
          UNION ALL SELECT 1 FROM ride_data.rides WHERE synthetic IS FALSE
          UNION ALL SELECT 1 FROM ride_data.external_user_ids x JOIN ride_data.users u USING (user_id) WHERE u.synthetic IS FALSE
          UNION ALL SELECT 1 FROM ride_data.external_trip_ids x JOIN ride_data.rides r USING (ride_id) WHERE r.synthetic IS FALSE
          UNION ALL SELECT 1 FROM ride_data.ride_app_events WHERE synthetic IS FALSE
        )
        """
    ).fetchone()[0]
    if not company_rows_exist:
        conn.execute(f"TRUNCATE TABLE {', '.join(ride_tables + archive_tables)} RESTART IDENTITY CASCADE")
        return preserved_ids
    conn.execute(
        "DELETE FROM ride_data.external_trip_ids x USING ride_data.rides r "
        "WHERE x.ride_id = r.ride_id AND r.synthetic IS TRUE"
    )
    conn.execute(
        "DELETE FROM ride_data.external_user_ids x USING ride_data.users u "
        "WHERE x.user_id = u.user_id AND u.synthetic IS TRUE"
    )
    for table in ride_tables:
        conn.execute(f"DELETE FROM {table} WHERE synthetic IS TRUE")
    for table in archive_tables:
        conn.execute(f"DELETE FROM {table} WHERE synthetic IS TRUE")
    return preserved_ids


def _insert_users(conn: psycopg.Connection[Any], rng: random.Random) -> None:
    rows = []
    profiles = []
    counters = []
    created_base = REFERENCE_NOW - timedelta(days=950)
    for role, prefix, base_count in (("rider", "USR-R", BASE_RIDER_COUNT), ("driver", "USR-D", BASE_DRIVER_COUNT)):
        for i in range(1, base_count + ADDITIONAL_USER_COUNT // 2 + 1):
            user_id = f"{prefix}-{i:06d}"
            age_days = 90 + ((i * 17) % 1100)
            created_at = created_base + timedelta(days=i * 3)
            rows.append((user_id, role, f"{role}_{i:06d}", created_at, "active", True))
            # Preserve the exact random draw sequence for the original 80 users so their ride
            # timestamps remain stable when deterministic seed counts are extended.
            avg = (
                Decimal("4.00") + Decimal(rng.randrange(0, 95)) / Decimal("100")
                if i <= base_count
                else Decimal("4.00") + Decimal((i * 17) % 95) / Decimal("100")
            )
            trend = ["stable", "rising", "falling", "volatile"][i % 4]
            historical_total = i % 5
            historical_upheld = historical_total // 2
            historical_rejected = historical_total - historical_upheld
            fraud_count = 1 if i % 13 == 0 else 0
            payment_method = ("card", "wallet", "paynow")[i % 3]
            vehicle = f"Synthetic sedan {i:03d}" if role == "driver" else None
            profiles.append((
                user_id, age_days, 0, avg, trend, True, 0, historical_total,
                historical_upheld, historical_rejected, min(historical_total, i % 3),
                fraud_count, "Synthetic test flag" if fraud_count else None, payment_method, vehicle,
            ))
            # user_dispute_counters is a recent-window/category counter. The profile dispute_history_*
            # fields are lifetime imported-company summaries, so they are intentionally distinct.
            counters.append((user_id, i % 4, i % 9, i % 5, (i + 1) % 4, (i + 2) % 3, (i + 3) % 2, True))
    conn.cursor().executemany(
        "INSERT INTO ride_data.users (user_id, role, display_handle, created_at, account_status, synthetic) VALUES (%s,%s,%s,%s,%s,%s)",
        rows,
    )
    conn.cursor().executemany(
        """INSERT INTO ride_data.user_profiles
        (user_id,account_age_days,lifetime_completed_rides,average_rating,rating_trend,synthetic,
         evidence_source,verification_status,total_trips,dispute_history_total,dispute_history_upheld,
         dispute_history_rejected,dispute_history_upheld_against,fraud_flag_count,fraud_flag_details,
         payment_method,vehicle)
        VALUES (%s,%s,%s,%s,%s,%s,'system_record','verified',%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        profiles,
    )
    conn.cursor().executemany(
        "INSERT INTO ride_data.user_dispute_counters (user_id, disputes_30d, disputes_180d, route_deviation_count, no_show_count, property_damage_count, safety_incident_count, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        counters,
    )
    conn.cursor().executemany(
        "INSERT INTO ride_data.external_user_ids (source_system,company_user_id,user_id,content_sha256) VALUES (%s,%s,%s,%s)",
        [
            (RIDE_SOURCE_NAMESPACE, f"synthetic-user-{role[0]}-{i:06d}", f"{prefix}-{i:06d}",
             hashlib.sha256(f"synthetic-user-{role[0]}-{i:06d}".encode()).hexdigest())
            for role, prefix in (("rider", "USR-R"), ("driver", "USR-D"))
            for i in range(1, 51)
        ],
    )


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

    for i in range(1, BASE_RIDE_COUNT + ADDITIONAL_RIDE_COUNT + 1):
        ride_id = f"RIDE-{i:06d}"
        # Keep the original 60 seed pairings stable. Rotate only the additions so every
        # generated rider and driver receives at least one rating from a completed trip.
        rider_shift = 1 if i > BASE_RIDE_COUNT else 0
        driver_shift = 3 if i > BASE_RIDE_COUNT else 0
        rider_user_id = f"USR-R-{((i - 1 + rider_shift) % 50) + 1:06d}"
        driver_user_id = f"USR-D-{((i * 3 - 1 + driver_shift) % 50) + 1:06d}"
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
        ride_status = "cancelled_after_arrival" if i % 10 == 0 else "completed"

        conn.execute(
            "INSERT INTO ride_data.rides (ride_id, rider_user_id, driver_user_id, requested_at, accepted_at, pickup_at, dropoff_at, ride_status, service_tier, quoted_distance_meters, quoted_duration_seconds, quoted_fare_cents, currency, synthetic, evidence_source, verification_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (ride_id, rider_user_id, driver_user_id, requested_at, accepted_at, pickup_at, dropoff_at, ride_status, "standard", int(planned_distance), int(planned_duration), quoted_fare, "SGD", True, "system_record", "verified"),
        )
        conn.execute(
            "INSERT INTO ride_data.ride_route_plans (ride_id, pickup_label, pickup_lat, pickup_lon, dropoff_label, dropoff_lat, dropoff_lon, planned_distance_meters, actual_distance_meters, planned_duration_seconds, actual_duration_seconds, driver_arrival_distance_meters, driver_wait_seconds, synthetic, evidence_source, verification_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
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
                "system_record",
                "verified",
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
                "INSERT INTO ride_data.ride_gps_samples (ride_id, sample_at, lat, lon, accuracy_meters, speed_meters_per_second, collector, evidence_source, verification_status, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (ride_id, pickup_at + timedelta(minutes=seq * 5), _nudge(pickup[1], seq), _nudge(pickup[2], seq), Decimal("4.50") + Decimal(seq) / Decimal("10"), Decimal("8.00") + Decimal(seq), "app_v3", "system_record", "verified", True),
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
                "INSERT INTO ride_data.ride_chat_messages (message_id, ride_id, participant_role, sent_at, message_text, evidence_source, verification_status, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (ev_id, ride_id, role, requested_at + timedelta(minutes=3 + ev_counter % 4), text, "system_record", "verified", True),
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
            "INSERT INTO ride_data.ride_fare_breakdowns (ride_id, base_fare_cents, distance_fare_cents, time_fare_cents, waiting_fare_cents, surge_multiplier, surge_fare_cents, cancellation_fee_cents, platform_fee_cents, total_fare_cents, currency, synthetic, evidence_source, verification_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (ride_id, base, distance_fare, time_fare, waiting_fare, surge, surge_fare, cancellation, platform, total, "SGD", True, "system_record", "verified"),
        )
        if ride_status == "completed":
            driver_rating = Decimal("3.50") + Decimal((i * 7) % 151) / Decimal("100")
            rider_rating = Decimal("3.60") + Decimal((i * 11) % 141) / Decimal("100")
            conn.cursor().executemany(
                "INSERT INTO ride_data.ride_ratings (ride_id, rated_user_id, rating_from_role, rating, rated_at, synthetic) VALUES (%s,%s,%s,%s,%s,true)",
                [
                    (ride_id, rider_user_id, "driver", rider_rating, dropoff_at + timedelta(hours=1)),
                    (ride_id, driver_user_id, "rider", driver_rating, dropoff_at + timedelta(hours=1)),
                ],
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

    conn.execute(
        """
        UPDATE ride_data.user_profiles p
        SET average_rating = r.mean_rating
        FROM (
          SELECT rated_user_id, round(avg(rating), 2) AS mean_rating, count(*) AS rating_count
          FROM ride_data.ride_ratings WHERE synthetic IS TRUE GROUP BY rated_user_id
        ) r
        WHERE p.user_id = r.rated_user_id AND p.synthetic IS TRUE
        """
    )
    conn.execute(
        """UPDATE ride_data.user_profiles p
        SET total_trips=counts.total_trips,lifetime_completed_rides=counts.completed_trips
        FROM (
          SELECT u.user_id,
            count(r.ride_id)::integer AS total_trips,
            count(r.ride_id) FILTER (WHERE r.ride_status='completed')::integer AS completed_trips
          FROM ride_data.users u LEFT JOIN ride_data.rides r
            ON (r.rider_user_id=u.user_id OR r.driver_user_id=u.user_id) AND r.synthetic IS TRUE
          WHERE u.synthetic IS TRUE GROUP BY u.user_id
        ) counts
        WHERE p.user_id=counts.user_id AND p.synthetic IS TRUE"""
    )
    conn.execute(
        """
        INSERT INTO ride_data.user_rating_history (user_id, rating_at, rating, sample_size, synthetic)
        SELECT rated_user_id, max(rated_at), round(avg(rating), 2), count(*), true
        FROM ride_data.ride_ratings WHERE synthetic IS TRUE GROUP BY rated_user_id
        """
    )
    for table in [
        "rides", "ride_route_plans", "ride_waypoints", "ride_gps_samples", "ride_stops",
        "ride_chat_messages", "ride_app_events", "ride_call_attempts", "ride_fare_breakdowns", "ride_fare_adjustments",
        "ride_promo_applications", "ride_device_signals", "ride_external_conditions", "scenario_tags",
    ]:
        counts[table] = conn.execute(f"SELECT count(*) FROM ride_data.{table} WHERE synthetic IS TRUE").fetchone()[0]
    synthetic_ride_ids = conn.execute(
        "SELECT ride_id FROM ride_data.rides WHERE synthetic IS TRUE ORDER BY ride_id"
    ).fetchall()
    conn.cursor().executemany(
        "INSERT INTO ride_data.external_trip_ids (source_system,company_trip_id,ride_id,content_sha256) VALUES (%s,%s,%s,%s)",
        [
            (RIDE_SOURCE_NAMESPACE, f"synthetic-trip-{ride_id.removeprefix('RIDE-')}", ride_id,
             hashlib.sha256(f"synthetic-trip-{ride_id.removeprefix('RIDE-')}".encode()).hexdigest())
            for (ride_id,) in synthetic_ride_ids
        ],
    )
    dataset_hash = hashlib.sha256(json.dumps(counts, sort_keys=True).encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT INTO ride_data.ingest_audit (generator_name, ride_seed, archive_seed, generated_at, policy_version, row_counts, dataset_sha256, synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        ("database.seed.generator", ride_seed, archive_seed, REFERENCE_NOW, POLICY_VERSION, Jsonb(counts), dataset_hash, True),
    )


def _archive_internal_id(
    conn: psycopg.Connection[Any], sequence: str, prefix: str, role_code: str | None = None
) -> str:
    value = conn.execute("SELECT nextval(%s::regclass)", (sequence,)).fetchone()[0]
    if value > 999999:
        raise ValueError(f"global ID range exhausted for {prefix}")
    role_part = f"-{role_code}" if role_code else ""
    return f"{prefix}{role_part}-{value:06d}"


def _insert_archive(
    conn: psycopg.Connection[Any], rng: random.Random, preserved_ids: dict[str, dict[str, str]]
) -> None:
    policy = _policy_document()
    policy_0_1_1 = _policy_document_version("ryde-policy-0.1.1")
    previous_policy = deepcopy(policy_0_1_1)
    previous_policy["version"] = "ryde-policy-0.1.0"
    previous_policy_rule = next(rule for rule in previous_policy["rules"] if rule["id"] == "RP-ESC-003")
    previous_policy_rule["text"] = (
        "Escalate when the case is high impact (D-10: money >= SGD 25.00, safety category, "
        "fraud risk >= 0.60, or >=3 disputes by the same party in 30 days)."
    )
    policy_versions = [
        (
            "ryde-policy-0.0.8",
            "POLICY-000008",
            REFERENCE_NOW - timedelta(days=540),
            REFERENCE_NOW - timedelta(days=360),
            {**deepcopy(previous_policy), "version": "ryde-policy-0.0.8"},
        ),
        (
            "ryde-policy-0.0.9",
            "POLICY-000009",
            REFERENCE_NOW - timedelta(days=360),
            REFERENCE_NOW - timedelta(days=180),
            {**deepcopy(previous_policy), "version": "ryde-policy-0.0.9"},
        ),
        (
            "ryde-policy-0.1.0",
            "POLICY-000010",
            REFERENCE_NOW - timedelta(days=180),
            REFERENCE_NOW - timedelta(days=30),
            previous_policy,
        ),
        (
            "ryde-policy-0.1.1",
            "POLICY-000011",
            REFERENCE_NOW - timedelta(days=30),
            REFERENCE_NOW,
            policy_0_1_1,
        ),
        (POLICY_VERSION, "POLICY-000012", REFERENCE_NOW, None, policy),
    ]
    conn.cursor().executemany(
        "INSERT INTO case_archive.archive_policy_versions VALUES (%s,%s,%s,%s,%s,%s)",
        [(name, version_id, start, end, Jsonb(doc), True) for name, version_id, start, end, doc in policy_versions],
    )
    reason_codes = ["policy_misapplied", "evidence_misweighted", "evidence_missing", "fraud_suspected", "goodwill", "safety_override", "other"]
    case_ids: dict[int, str] = {}
    for i in range(1, BASE_ARCHIVE_CASE_COUNT + ADDITIONAL_ARCHIVE_CASE_COUNT + 1):
        bundle_key = f"{ARCHIVE_SOURCE_NAMESPACE}:seed-case-{i:06d}"
        if bundle_key in preserved_ids["cases"]:
            case_ids[i] = preserved_ids["cases"][bundle_key]
        else:
            value = conn.execute("SELECT nextval('tribunal.case_id_seq')").fetchone()[0]
            if value > 999999:
                raise ValueError("global dispute case ID range exhausted")
            case_ids[i] = f"DSP-{value:06d}"
    for i in range(1, BASE_ARCHIVE_CASE_COUNT + ADDITIONAL_ARCHIVE_CASE_COUNT + 1):
        case_id = case_ids[i]
        trip_bundle_key = f"{ARCHIVE_SOURCE_NAMESPACE}:seed-trip-{i:06d}"
        ride_id = preserved_ids["trips"].get(trip_bundle_key) or _archive_internal_id(
            conn, "ride_data.imported_ride_id_seq", "RIDE"
        )
        category = CATEGORY_TAGS[(i - 1) % len(CATEGORY_TAGS)]
        trip_at, created_at = _archive_case_times(i)
        policy_version = next(
            name
            for name, _, effective_from, effective_to, _ in policy_versions
            if effective_from <= created_at and (effective_to is None or created_at < effective_to)
        )
        subject = f"synthetic {category.replace('_', ' ')} precedent"
        human_touched = i <= 14 or 33 <= i <= 40
        decision_origin = "human" if human_touched else "agent"
        filed_by = "rider" if i % 3 else "driver"
        verdict = ["refund", "compensation", "no_action", "escalated"][i % 4]
        ruling_type = "no_action" if verdict == "escalated" else verdict
        confidence = None if human_touched and i % 5 == 0 else Decimal("0.610") + Decimal((i * 7) % 35) / Decimal("100")
        amount = 0 if ruling_type == "no_action" else 200 + (i % 12) * 125
        rider_bundle_key = f"{ARCHIVE_SOURCE_NAMESPACE}:seed-rider-{i:06d}"
        driver_bundle_key = f"{ARCHIVE_SOURCE_NAMESPACE}:seed-driver-{i:06d}"
        rider_archive_user_id = preserved_ids["users"].get(rider_bundle_key) or _archive_internal_id(
            conn, "ride_data.imported_rider_id_seq", "USR", "R"
        )
        driver_archive_user_id = preserved_ids["users"].get(driver_bundle_key) or _archive_internal_id(
            conn, "ride_data.imported_driver_id_seq", "USR", "D"
        )
        filing_user_id = rider_archive_user_id if filed_by == "rider" else driver_archive_user_id
        rider_received_rating = Decimal("3.90") + Decimal((i * 7) % 111) / Decimal("100")
        driver_received_rating = Decimal("3.80") + Decimal((i * 11) % 121) / Decimal("100")
        conn.execute(
            "INSERT INTO case_archive.archive_user_snapshots (archive_user_id,bundle_user_key,role,display_name,account_age_days,average_rating,total_trips) VALUES (%s,%s,'rider',%s,%s,%s,%s)",
            (rider_archive_user_id, rider_bundle_key, f"Synthetic rider {i:06d}", 180 + i, rider_received_rating, 20 + i),
        )
        conn.execute(
            "INSERT INTO case_archive.archive_user_snapshots (archive_user_id,bundle_user_key,role,display_name,account_age_days,average_rating,total_trips) VALUES (%s,%s,'driver',%s,%s,%s,%s)",
            (driver_archive_user_id, driver_bundle_key, f"Synthetic driver {i:06d}", 400 + i, driver_received_rating, 80 + i),
        )
        trip_fare = 1200 + i * 37
        conn.execute(
            """INSERT INTO case_archive.archive_trip_snapshots
            (archive_ride_id,bundle_trip_key,rider_archive_user_id,driver_archive_user_id,trip_status,trip_at,
             requested_at,accepted_at,pickup_at,dropoff_at,service_tier,quoted_distance_meters,
             quoted_duration_seconds,quoted_fare_cents,fare_cents,currency,rider_rating,driver_rating,
             fare_breakdown,pricing_structure,pickup_details,dropoff_details,gps_data)
            VALUES (%s,%s,%s,%s,'completed',%s,%s,%s,%s,%s,'standard',%s,%s,%s,%s,'SGD',%s,%s,%s,%s,%s,%s,%s)""",
            (ride_id, trip_bundle_key, rider_archive_user_id, driver_archive_user_id,
             trip_at, trip_at, trip_at + timedelta(minutes=2), trip_at + timedelta(minutes=7),
             trip_at + timedelta(minutes=27), 7000 + i * 100, 1200 + i * 10, trip_fare, trip_fare,
             driver_received_rating, rider_received_rating,
             Jsonb({"currency":"SGD","base_fare_cents":350,"distance_fare_cents":500+i,
                    "time_fare_cents":350+i*36,"waiting_fare_cents":0,"surge_multiplier":1.0,
                    "surge_fare_cents":0,"cancellation_fee_cents":0,"platform_fee_cents":0,
                    "total_fare_cents":trip_fare}),
             Jsonb({"service_tier":"standard","currency":"SGD","distance_rate_cents_per_km":50,
                    "time_rate_cents_per_minute":25}),
             Jsonb({"label":"orchard","lat":1.3048,"lon":103.8318}),
             Jsonb({"label":"marina_bay","lat":1.283,"lon":103.86}),
             Jsonb([{"recorded_at":(trip_at+timedelta(minutes=seq*5)).isoformat(),
                     "lat":float(Decimal("1.3048")-Decimal(seq)*Decimal("0.005")),
                     "lon":float(Decimal("103.8318")+Decimal(seq)*Decimal("0.007")),
                     "accuracy_meters":5.0,"speed_kmh":30.0+seq*2} for seq in range(4)])),
        )
        conn.execute(
            "INSERT INTO case_archive.archive_cases (archive_case_id,archive_ride_id,category,subject,filed_by,created_at,policy_version,synthetic,filing_archive_user_id,bundle_case_key) VALUES (%s,%s,%s,%s,%s,%s,%s,true,%s,%s)",
            (case_id, ride_id, category, subject, filed_by, created_at, policy_version, filing_user_id, f"{ARCHIVE_SOURCE_NAMESPACE}:seed-case-{i:06d}"),
        )
        conn.execute(
            "INSERT INTO case_archive.archive_case_classifications VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (case_id, category, Jsonb(["synthetic", "precedent"]), subject, amount, Decimal((i % 8)) / Decimal("10"), True),
        )
        case_evidence_ids: dict[int, str] = {}
        for j, evidence_class in enumerate(["gps_telemetry", "fare", "chat_log"]):
            evidence_bundle_key = f"{ARCHIVE_SOURCE_NAMESPACE}:seed-evidence-{i:06d}-{j:02d}"
            evidence_id = preserved_ids["evidence"].get(evidence_bundle_key) or _archive_internal_id(
                conn, "ride_data.imported_evidence_id_seq", "EV"
            )
            case_evidence_ids[j] = evidence_id
            conn.execute(
                "INSERT INTO case_archive.archive_case_evidence (archive_evidence_id,archive_case_id,evidence_class,source,recorded_at,provenance,verification,visibility,payload,synthetic,bundle_evidence_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s)",
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
                    evidence_bundle_key,
                ),
            )
        conn.execute(
            "INSERT INTO case_archive.archive_case_decisions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (case_id, verdict, ruling_type, f"synthetic advisory action for {category}", amount, "SGD", confidence, decision_origin, created_at + timedelta(hours=2), True),
        )
        if human_touched:
            proposed_verdict = verdict if i % 3 else "no_action"
            proposed_type = "no_action" if proposed_verdict == "escalated" else proposed_verdict
            proposed_amount = amount if i % 2 else max(0, amount - 100)
            conn.execute(
                "INSERT INTO case_archive.archive_case_rulings (archive_case_id,ruling_stage,decision_origin,verdict,ruling_type,action_description,amount_cents,currency,confidence,decided_at) VALUES (%s,'model_proposed','agent',%s,%s,%s,%s,'SGD',%s,%s)",
                (case_id, proposed_verdict, proposed_type, f"synthetic model proposal for {category}", proposed_amount, confidence, created_at + timedelta(hours=1)),
            )
        conn.execute(
            "INSERT INTO case_archive.archive_case_rulings (archive_case_id,ruling_stage,decision_origin,verdict,ruling_type,action_description,amount_cents,currency,confidence,decided_at) VALUES (%s,%s,%s,%s,%s,%s,%s,'SGD',%s,%s)",
            (case_id, "reviewer_approved" if human_touched else "model_proposed", decision_origin,
             verdict, ruling_type, f"synthetic advisory action for {category}", amount, confidence, created_at + timedelta(hours=2)),
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
                Jsonb([case_evidence_ids[0]] if human_touched else []),
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
        preserved_case_ids = _clear(conn)
        _insert_users(conn, rng)
        _insert_archive(conn, rng, preserved_case_ids)
        _insert_rides(conn, rng, ride_seed, archive_seed)
        conn.commit()


def main() -> None:
    seed_database()


if __name__ == "__main__":
    main()
