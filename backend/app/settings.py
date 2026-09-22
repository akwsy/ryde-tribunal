"""Runtime configuration, sourced from the environment (see .env.example at repo root).

Only NAMES and shapes live in `.env.example`; values come from the process environment.
No policy constants live here — the policy document is loaded from JSON at runtime (D-18).
The numeric thresholds below (D-08..D-11) are *decision parameters*, recorded on every
ruling; they are not policy remedies and never encode a per-case verdict.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Model provider (D-04) ---
    model_provider: str = Field(default="deterministic_mock")
    model_base_url: str = Field(default="")
    model_name: str = Field(default="")
    model_api_key: str = Field(default="")
    model_timeout_s: int = Field(default=30)

    # --- External information source (I-8) ---
    external_info_enabled: bool = Field(default=False)
    external_info_base_url: str = Field(default="")
    external_info_api_key: str = Field(default="")

    # --- Policy (D-18): single JSON source of truth, versioned ---
    policy_version: str = Field(default="ryde-policy-0.1.0")
    # Canonical runtime location is the database specialist's seed file. For offline/CI
    # runs before that file exists, the loader falls back to the backend test fixture.
    # See backend/ASSUMPTIONS.md (A-1).
    policy_path: str = Field(default="")

    # --- Decision parameters (D-08..D-11), recorded on every ruling ---
    escalation_confidence_threshold: float = Field(default=0.70)
    high_impact_amount_cents: int = Field(default=2500)
    goodwill_cap_cents: int = Field(default=1500)
    fraud_risk_escalation_threshold: float = Field(default=0.60)
    currency: str = Field(default="SGD")
    timezone: str = Field(default="Asia/Singapore")

    # --- Database (integration) ---
    # Read-only DSN for ride_data/case_archive via the ryde_backend_readonly role. PLAIN
    # psycopg DSN (postgresql://…), NOT a SQLAlchemy URL — the database accessors use psycopg.
    # When empty, main.py wires the PendingDatabaseReader (database_unavailable) as the default.
    read_database_dsn: str = Field(default="")
    # Separate writable DSN for the backend-owned tribunal schema (Phase Zero uses the
    # in-process store; this is the seam for the SQLAlchemy-backed store at integration).
    tribunal_database_dsn: str = Field(default="")

    # --- Backend ---
    backend_host: str = Field(default="127.0.0.1")
    backend_port: int = Field(default=8000)
    log_level: str = Field(default="info")

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=()
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
