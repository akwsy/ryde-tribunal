"""Policy loader (D-18): the policy document lives in ONE place — a versioned JSON file —
loaded at runtime. No policy remedies are duplicated as Python constants.

Canonical runtime path: database/seed/policy/ryde-policy-<version>.json (owned by the
database specialist, now on main). That file is the single source of truth and is consumed
UNCHANGED: its rules use `{id, section, text}` and it carries a top-level `numeric_thresholds`
list. The loader accepts `id` via a Pydantic alias to keep the internal name `rule_id`, so the
database's file is never reshaped. `POLICY_PATH` overrides the location.

`shared/openapi.yaml` PolicyDocument requires `rules[].{id, text}` (+ optional `category`);
`as_public_document` emits exactly that.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../backend
_REPO_ROOT = _BACKEND_DIR.parent

SOURCE_BACKED_POLICY_VERSIONS = frozenset({"ryde-policy-1.0.0", "ryde-policy-1.1.0"})


def is_source_backed_policy(version: str) -> bool:
    return version in SOURCE_BACKED_POLICY_VERSIONS

# Map the canonical numeric_thresholds names to the keys the evaluator/judge look up. The
# VALUES all come from the file — nothing is hardcoded here except the name correspondence.
_THRESHOLD_KEY_MAP = {
    "route_deviation_pct": "deviation_tolerance_pct",
    "unexpected_stop_seconds": "unexplained_stop_seconds",
    "driver_wait_seconds": "required_wait_seconds",
    "arrival_distance_meters": "arrival_radius_m",
    "duration_ratio_pct": "duration_tolerance_pct",
    "photo_window_seconds": "photo_window_seconds",
}


class PolicyRuleDoc(BaseModel):
    """One rule from the canonical file. `id` in the file → `rule_id` internally via alias, so
    the file is consumed unchanged. `section` is the canonical field; exposed as `category`."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    rule_id: str = Field(alias="id")
    text: str
    section: str | None = None
    classification: str = "historical_fictional"
    source: dict[str, Any] | None = None
    services: tuple[str, ...] = ()


class PolicyDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    version: str
    currency: str = "SGD"
    rules: tuple[PolicyRuleDoc, ...]
    numeric_thresholds: tuple[dict[str, Any], ...] = ()

    def rule(self, rule_id: str) -> PolicyRuleDoc | None:
        for r in self.rules:
            if r.rule_id == rule_id:
                return r
        return None

    def threshold_map(self) -> dict[str, float]:
        """Flatten the canonical numeric_thresholds into the evaluator/judge key space."""
        out: dict[str, float] = {}
        for t in self.numeric_thresholds:
            name = t.get("name")
            value = t.get("value")
            if name is None or value is None:
                continue
            key = _THRESHOLD_KEY_MAP.get(name, name)
            out[key] = float(value)
        return out

    def as_public_document(self) -> dict:
        """GET /policy/{version} — matches shared/openapi.yaml PolicyDocument (id, text, category)."""
        return {
            "version": self.version,
            "rules": [
                {"rule_id": r.rule_id, "id": r.rule_id, "text": r.text, "category": r.section, "classification": r.classification,
                 "source": r.source, "services": list(r.services)}
                for r in self.rules
            ],
        }


def _candidate_paths(version: str, explicit: str | None) -> list[Path]:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit))
    # `version` already carries the "ryde-policy-" prefix (e.g. "ryde-policy-0.1.0").
    paths.append(_REPO_ROOT / "database" / "seed" / "policy" / f"{version}.json")
    return paths


class PolicyNotFoundError(FileNotFoundError):
    pass


def load_policy(version: str, *, explicit_path: str | None = None) -> PolicyDocument:
    for path in _candidate_paths(version, explicit_path):
        if path.is_file():
            data = json.loads(path.read_text())
            return PolicyDocument.model_validate(data)
    tried = ", ".join(str(p) for p in _candidate_paths(version, explicit_path))
    raise PolicyNotFoundError(f"policy {version!r} not found (looked in: {tried})")


@lru_cache
def load_policy_cached(version: str, explicit_path: str | None) -> PolicyDocument:
    return load_policy(version, explicit_path=explicit_path)
