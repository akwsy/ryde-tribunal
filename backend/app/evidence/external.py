"""External information quarantine (integrity rule I-8).

External LLM/API content is stored and passed in a SEPARATE `external_findings` collection,
never merged into case evidence. Each finding carries source_url, retrieved_at, reliability,
and an `evaluation` verdict recorded before it may be cited. It cannot override case evidence
or policy. If the external call fails, the ruling proceeds on native evidence when safe,
records `external_unavailable: true`, and fabricates nothing.

External retrieval is disabled by default (`EXTERNAL_INFO_ENABLED=false`). When enabled, findings
remain separate from case evidence and cannot override verified records or policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ExternalFinding:
    source_url: str
    retrieved_at: str
    reliability: str          # high | medium | low
    evaluation: str           # verdict recorded BEFORE citation is allowed
    content: str


@dataclass
class ExternalResult:
    findings: list[ExternalFinding] = field(default_factory=list)
    unavailable: bool = False


class ExternalInfoSource(Protocol):
    def fetch(self, category: str, features: dict[str, Any]) -> ExternalResult: ...


class DisabledExternalSource:
    """Default: external info off (EXTERNAL_INFO_ENABLED=false). Returns nothing, not failure —
    the feature is simply not enabled, so `unavailable` is False and findings are empty."""

    def fetch(self, category: str, features: dict[str, Any]) -> ExternalResult:
        return ExternalResult(findings=[], unavailable=False)


class FailingExternalSource:
    """Represents an enabled-but-unreachable external provider. Used by the I-8 test: the
    ruling must still return with empty findings and external_unavailable=true."""

    def fetch(self, category: str, features: dict[str, Any]) -> ExternalResult:
        return ExternalResult(findings=[], unavailable=True)
