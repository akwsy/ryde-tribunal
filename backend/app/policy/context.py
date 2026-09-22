"""Policy layer.

Integrity rule I-1 is the reason this package exists as its own layer: the policy layer may
return ONLY (a) the set of applicable policy rule ids + their text and (b) factual
measurements. It may NEVER return a ruling type, a recommended action, a monetary amount, or
a fault attribution. The mapping from measurement + policy text to a ruling belongs to the
Judge alone.

`PolicyContext` is a frozen structure whose fields are measurements and rule references only.
The forbidden-field guard below is enforced both at construction (runtime) and by
`tests/test_i1_no_precomputed_verdict.py` (static, over the class definition).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A field name matching this pattern would let the policy layer smuggle a verdict. I-1 test
# asserts PolicyContext (and PolicyRule / Measurement) carry no such field.
FORBIDDEN_FIELD_RE = re.compile(
    r"rul(e|ing)_type|verdict|recommend|action|amount|fault|refund|remedy|award|"
    r"decision|outcome|resolution",
    re.IGNORECASE,
)

# A measurement value must be a number, a bool, or a string LABEL for a factual reading —
# never a verdict. Measurement *values* are additionally screened for verdict-shaped strings.
FORBIDDEN_VALUE_RE = re.compile(
    r"refund|compensat|no_action|guilty|liable|at fault|grant|deny|approved|rejected",
    re.IGNORECASE,
)


class PolicyRule(BaseModel):
    """A single applicable policy rule: its id and its text, nothing else."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    text: str

    @model_validator(mode="after")
    def _no_verdict_field(self) -> "PolicyRule":
        for name in type(self).model_fields:
            if FORBIDDEN_FIELD_RE.search(name):
                raise TypeError(f"PolicyRule field '{name}' is verdict-shaped (I-1)")
        return self


class Measurement(BaseModel):
    """A single factual measurement read from case telemetry/fare data.

    `key` names the quantity (e.g. 'deviation_pct'); `value` is the reading; `unit` and
    `source_field` document provenance. No field here may name a verdict, and the value is
    screened so a string measurement cannot smuggle one.
    """

    model_config = ConfigDict(frozen=True)

    key: str
    value: float | int | bool | str
    unit: str | None = None
    source_field: str | None = None

    @model_validator(mode="after")
    def _factual_only(self) -> "Measurement":
        if FORBIDDEN_FIELD_RE.search(self.key):
            raise TypeError(f"Measurement key '{self.key}' is verdict-shaped (I-1)")
        if isinstance(self.value, str) and FORBIDDEN_VALUE_RE.search(self.value):
            raise TypeError(
                f"Measurement '{self.key}' carries a verdict-shaped value (I-1)"
            )
        return self


class PolicyContext(BaseModel):
    """Frozen: applicable rules + factual measurements only. Structurally verdict-incapable.

    This is what the policy layer hands the Judge. It carries no ruling, action, amount, or
    fault. The Judge maps (measurements + rule text) -> ruling; the policy layer never does.
    """

    model_config = ConfigDict(frozen=True)

    policy_version: str
    category: str
    applicable_rules: tuple[PolicyRule, ...] = Field(default_factory=tuple)
    measurements: tuple[Measurement, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _no_verdict_field(self) -> "PolicyContext":
        for name in type(self).model_fields:
            if FORBIDDEN_FIELD_RE.search(name):
                raise TypeError(f"PolicyContext field '{name}' is verdict-shaped (I-1)")
        return self

    def measurement(self, key: str) -> Measurement | None:
        for m in self.measurements:
            if m.key == key:
                return m
        return None

    def measurement_map(self) -> dict[str, float | int | bool | str]:
        return {m.key: m.value for m in self.measurements}

    def rule_ids(self) -> list[str]:
        return [r.rule_id for r in self.applicable_rules]
