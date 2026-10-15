"""Model provider seam.

`ModelProvider.complete(prompt, response_schema) -> structured` with two adapters:

  * `deterministic_mock` — fully offline, what CI uses. Reasons from the prompt (case facts +
    policy text + measurements + evidence) at call time and produces case-specific structured
    output. Labelled `kind: "deterministic-mock"` on every output; a ruling touched by it
    carries `synthetic_reasoning: true`.
  * `openai_compatible` — POSTs to an OpenAI-style /chat/completions endpoint and is labelled
    `kind: "llm"`.

Every component output is stamped with `provider: {kind, model}`. The provider converts a prompt
into a component's structured conclusion; rules-first decisions are recorded separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderMeta:
    kind: str   # "llm" | "deterministic-mock"
    model: str
    display_name: str | None = None

    @property
    def is_synthetic(self) -> bool:
        return self.kind == "deterministic-mock"

    def to_api(self, policy_version: str | None = None) -> dict[str, Any]:
        d = {"kind": self.kind, "model": self.model}
        if self.display_name:
            d["display_name"] = self.display_name
        if policy_version is not None:
            d["policy_version"] = policy_version
        return d


@dataclass(frozen=True)
class Completion:
    """A provider's structured answer plus its provenance stamp."""

    data: dict[str, Any]
    provider: ProviderMeta
    usage: dict[str, int] | None = None


class ProviderUnavailable(RuntimeError):
    """The external provider could not be reached. The caller decides whether a ruling can
    still proceed on native evidence (I-8) or whether to surface provider_unavailable."""


class ModelOutputInvalid(RuntimeError):
    """A provider responded, but its payload was malformed or failed its response schema."""


class ModelProvider(Protocol):
    def complete(self, prompt: dict[str, Any], response_schema: dict[str, Any]) -> Completion: ...

    @property
    def meta(self) -> ProviderMeta: ...
