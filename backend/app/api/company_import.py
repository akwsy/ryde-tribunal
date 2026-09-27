"""Company-data import endpoint and its response-count projection."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from app.api.container import Container


def register_company_import_route(
    app: FastAPI,
    container: Container,
    error_response: Callable[..., JSONResponse],
) -> None:
    """Register the validated ZIP import endpoint on the application."""
    @app.post("/api/v1/imports/company-data")
    async def import_company_data(
        request: Request,
        x_reviewer_id: str | None = Header(default=None),
    ):
        if not x_reviewer_id:
            return error_response("validation_error", "X-Reviewer-Id header required", 401)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/zip":
            return error_response("validation_error", "Content-Type must be application/zip", 415)

        max_bytes = container.settings.import_max_upload_bytes
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    return error_response("validation_error", "ZIP upload exceeds the configured size limit", 413)
            except ValueError:
                return error_response("validation_error", "invalid Content-Length header", 400)

        descriptor, temp_name = tempfile.mkstemp(prefix="ryde-company-import-", suffix=".zip")
        temp_path = Path(temp_name)
        byte_count = 0
        try:
            with os.fdopen(descriptor, "wb") as uploaded:
                async for chunk in request.stream():
                    byte_count += len(chunk)
                    if byte_count > max_bytes:
                        return error_response("validation_error", "ZIP upload exceeds the configured size limit", 413)
                    uploaded.write(chunk)

            # Import package parsing is side-effect free. import_bundle validates typed values
            # before opening its DB connection or issuing any write.
            from database.importer.bundle import BundleValidationError, load_bundle
            from database.importer.persist import ImportDataError, import_bundle
            import psycopg

            try:
                with zipfile.ZipFile(temp_path) as archive:
                    if sum(member.file_size for member in archive.infolist()) > max_bytes:
                        return error_response(
                            "validation_error",
                            "expanded ZIP contents exceed the configured size limit",
                            413,
                        )
            except zipfile.BadZipFile:
                # load_bundle returns the consistent validation error below.
                pass
            try:
                bundle = load_bundle(temp_path)
            except BundleValidationError as exc:
                return error_response("validation_error", str(exc), 400)
            import_dsn = container.settings.import_database_dsn
            if not import_dsn:
                return error_response("database_unavailable", "company-data import database is not configured", 503)
            try:
                result = import_bundle(import_dsn, bundle)
            except ImportDataError as exc:
                return error_response("validation_error", str(exc), 400)
            except psycopg.Error:
                # Driver messages can contain bound company data; never echo them to the API.
                return error_response("database_unavailable", "company-data import failed; transaction rolled back", 503)
            imported, skipped = _company_import_counts(bundle, result)
            return {
                "source_system": str(bundle.manifest["source_system"]),
                "imported": imported,
                "skipped_duplicate_ids": skipped,
            }
        finally:
            temp_path.unlink(missing_ok=True)


def _company_import_counts(bundle, result) -> tuple[dict[str, int], dict[str, int]]:
    """Count stored records, including records skipped with duplicate parent IDs."""
    tables = bundle.tables
    skipped_users = set(result.skipped_user_ids)
    skipped_trips = set(result.skipped_trip_ids)

    def duplicate_children(filename: str) -> int:
        return sum(1 for row in tables[filename]
                   if row["company_trip_id"] in skipped_trips)

    total_users = len(tables["users.csv"])
    total_profiles = len(tables["profiles.csv"])
    total_trips = len(tables["trips.csv"])
    total_routes = total_fares = total_trips
    total_gps = len(tables["gps_telemetry.csv"])
    total_chat = len(tables["chat_logs.csv"])
    total_events = len(tables["app_events.csv"])
    skipped = {
        "users": len(skipped_users),
        "profiles": sum(1 for row in tables["profiles.csv"]
                         if row["company_user_id"] in skipped_users),
        "trips": len(skipped_trips),
        "routes": len(skipped_trips),
        "fares": len(skipped_trips),
        "gps_telemetry": duplicate_children("gps_telemetry.csv"),
        "chat_logs": duplicate_children("chat_logs.csv"),
        "app_events": duplicate_children("app_events.csv"),
    }
    totals = {
        "users": total_users,
        "profiles": total_profiles,
        "trips": total_trips,
        "routes": total_routes,
        "fares": total_fares,
        "gps_telemetry": total_gps,
        "chat_logs": total_chat,
        "app_events": total_events,
    }
    imported = {kind: total - skipped[kind] for kind, total in totals.items()}
    return imported, skipped
