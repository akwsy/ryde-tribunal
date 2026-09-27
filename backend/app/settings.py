"""Runtime configuration, sourced from the environment (see .env.example at repo root).

Only NAMES and shapes live in `.env.example`; values come from the process environment.
No policy constants live here — the policy document is loaded from JSON at runtime (D-18).
The numeric thresholds below (D-08..D-11) are *decision parameters*, recorded on every
ruling; they are not policy remedies and never encode a per-case verdict.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Model provider (D-04) ---
    model_provider: str = Field(default="deterministic_mock")
    model_base_url: str = Field(default="")
    model_name: str = Field(default="")
    model_provider_name: str = Field(default="")
    model_api_key: str = Field(default="")
    model_timeout_s: int = Field(default=30)

    # --- External information source (I-8) ---
    external_info_enabled: bool = Field(default=False)
    external_info_base_url: str = Field(default="")
    external_info_api_key: str = Field(default="")

    # --- Policy (D-18): single JSON source of truth, versioned ---
    policy_version: str = Field(default="ryde-policy-0.1.2")
    # Canonical runtime location is the database specialist's versioned policy file.
    policy_path: str = Field(default="")
    judging_config_path: str = Field(default="")

    # --- Decision parameters (D-08..D-11), recorded on every ruling ---
    escalation_confidence_threshold: float = Field(default=0.70)
    high_impact_amount_cents: int = Field(default=2500)
    goodwill_cap_cents: int = Field(default=1500)
    currency: str = Field(default="SGD")
    timezone: str = Field(default="Asia/Singapore")

    # --- Database (integration) ---
    # Read-only DSN for ride_data/case_archive via the ryde_backend_readonly role. PLAIN
    # psycopg DSN (postgresql://…), NOT a SQLAlchemy URL — the database accessors use psycopg.
    # When empty, main.py wires the PendingDatabaseReader (database_unavailable) as the default.
    read_database_dsn: str = Field(default="")
    # Separate writable DSN for the backend-owned tribunal schema. Empty selects the
    # in-process store for offline work.
    tribunal_database_dsn: str = Field(default="")
    # Writer target for HTTP company-data imports; plain psycopg DSN (postgresql://...).
    import_database_dsn: str = Field(default="")
    import_max_upload_bytes: int = Field(default=52_428_800, gt=0)

    # --- Backend ---
    backend_host: str = Field(default="127.0.0.1")
    backend_port: int = Field(default=8000)
    log_level: str = Field(default="info")

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=()
    )

    @field_validator("import_database_dsn")
    @classmethod
    def validate_import_database_dsn(cls, value: str) -> str:
        if value.startswith(("postgresql+", "postgres+")):
            raise ValueError("IMPORT_DATABASE_DSN must be a plain psycopg DSN, not a SQLAlchemy URL")
        if "://" in value and not value.startswith(("postgresql://", "postgres://")):
            raise ValueError("IMPORT_DATABASE_DSN must use a PostgreSQL psycopg DSN")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
