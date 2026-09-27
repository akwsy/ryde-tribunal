"""Configurable Judge weighting for policy, precedent, recency, and fraud context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "judging.json"


@dataclass(frozen=True)
class JudgingConfig:
    policy_priority: float = 100.0
    human_approved_weight: float = 2.0
    model_proposed_weight: float = 1.0
    recency_half_life_days: float = 365.0
    fraud_influence_weight: float = 3.0
    fraud_assessment_note: str = (
        "Use fraud-risk signals to scrutinize unverified advocate claims. Never use history to "
        "override verified evidence or deny a remedy supported by verified evidence, and never "
        "escalate solely because of fraud risk."
    )


def _positive_number(data: dict[str, Any], key: str, default: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"judging config {key} must be a positive number")
    return float(value)


@lru_cache(maxsize=8)
def load_judging_config(path: str | None = None) -> JudgingConfig:
    config_path = Path(path) if path else _DEFAULT_PATH
    data = json.loads(config_path.read_text())
    precedent = data.get("precedent", {})
    fraud = data.get("fraud", {})
    note = fraud.get("assessment_note", JudgingConfig.fraud_assessment_note)
    if not isinstance(note, str) or not note.strip():
        raise ValueError("judging config fraud.assessment_note must be non-empty text")
    return JudgingConfig(
        policy_priority=_positive_number(precedent, "policy_priority", 100.0),
        human_approved_weight=_positive_number(precedent, "human_approved_weight", 2.0),
        model_proposed_weight=_positive_number(precedent, "model_proposed_weight", 1.0),
        recency_half_life_days=_positive_number(precedent, "recency_half_life_days", 365.0),
        fraud_influence_weight=_positive_number(fraud, "influence_weight", 3.0),
        fraud_assessment_note=note,
    )
