"""Policy loader (D-18): the policy document lives in ONE place — a versioned JSON file —
loaded at runtime. No policy remedies are duplicated as Python constants.

Canonical runtime path: database/seed/policy/ryde-policy-<version>.json (owned by the
database specialist). That file does not exist yet in Phase Zero, so for offline/CI runs the
loader falls back to the backend-owned test fixture at
backend/tests/fixtures/policy/ryde-policy-<version>.json, whose content is transcribed from
docs/03-mock-policy.md (ASSUMPTIONS A-1). `POLICY_PATH` overrides both.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../backend
_REPO_ROOT = _BACKEND_DIR.parent


class PolicyRuleDoc(BaseModel):
    model_config = ConfigDict(frozen=True)
    rule_id: str
    text: str
    # Optional structured facets the JSON may carry to help the evaluator locate measurements.
    # These are THRESHOLDS and FIELD NAMES only — never remedies (see the fixture).
    thresholds: dict[str, float] = {}


class PolicyDocument(BaseModel):
    model_config = ConfigDict(frozen=True)
    version: str
    currency: str
    rules: tuple[PolicyRuleDoc, ...]

    def rule(self, rule_id: str) -> PolicyRuleDoc | None:
        for r in self.rules:
            if r.rule_id == rule_id:
                return r
        return None

    def as_public_document(self) -> dict:
        """The document returned by GET /policy/{version} — exactly what was loaded."""
        return {
            "version": self.version,
            "currency": self.currency,
            "rules": [
                {"rule_id": r.rule_id, "text": r.text, "thresholds": r.thresholds}
                for r in self.rules
            ],
        }


def _candidate_paths(version: str, explicit: str | None) -> list[Path]:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit))
    # `version` already carries the "ryde-policy-" prefix (e.g. "ryde-policy-0.1.0"), so the
    # filename uses it verbatim rather than re-prefixing it.
    paths.append(_REPO_ROOT / "database" / "seed" / "policy" / f"{version}.json")
    paths.append(_BACKEND_DIR / "tests" / "fixtures" / "policy" / f"{version}.json")
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
