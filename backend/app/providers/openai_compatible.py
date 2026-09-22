"""OpenAI-compatible adapter (D-04, I-6).

POSTs the structured prompt to an OpenAI-style `/chat/completions` endpoint and parses a JSON
object back. Ready but UNTESTED against a live endpoint in Phase Zero — the owner supplies
base URL / model / key at approval time (D-04). The API key is read from the environment
(`MODEL_API_KEY`); it is NEVER committed.

Labelled `kind: "llm"`, so a ruling that used it does NOT carry synthetic_reasoning.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.providers.base import Completion, ProviderMeta, ProviderUnavailable

_SYSTEM = (
    "You are one role in the Ryde Tribunal (a rider/driver dispute system). You reason ONLY "
    "from the case facts, measurements, policy rule text, and evidence given in the user "
    "message. You never invent evidence. You return a single JSON object matching the "
    "provided schema and nothing else."
)


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_s: int = 30,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url or not model:
            raise ValueError("openai_compatible requires MODEL_BASE_URL and MODEL_NAME")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._client = client
        self._meta = ProviderMeta(kind="llm", model=model)

    @property
    def meta(self) -> ProviderMeta:
        return self._meta

    def complete(
        self, prompt: dict[str, Any], response_schema: dict[str, Any]
    ) -> Completion:
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"case": prompt, "response_schema": response_schema}
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        client = self._client or httpx.Client(timeout=self._timeout_s)
        try:
            resp = client.post(
                f"{self._base_url}/chat/completions", json=body, headers=headers
            )
            resp.raise_for_status()
            payload = resp.json()
            content = payload["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable(str(exc)) from exc
        finally:
            if self._client is None:
                client.close()
        return Completion(data=data, provider=self._meta)
