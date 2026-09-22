"""Backend-owned persistence of model work and rulings (write matrix §6: case_*,
model_work_*, ruling_*, case_history, idempotency_keys).

Phase Zero uses an in-process store. It implements the two properties the brief tests:

  * model work is durable and retrievable after the request completes (D-05), and
  * idempotency is CONCURRENCY-safe — two simultaneous adjudications with the same key
    produce ONE ruling. We use a per-key lock plus a claim record, which is the in-memory
    analogue of "a row-level lock or a unique constraint on the key" required by the
    contract (§2), not a read-then-write check.

The SQLAlchemy-backed variant is a later integration task; this store sits behind the same
`ResultStore` surface so swapping it in is mechanical.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


class IdempotencyConflict(RuntimeError):
    """A repeated Idempotency-Key arrived with a different request body (409 conflict)."""


class ResultStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._results: dict[str, dict[str, Any]] = {}          # case_id -> CaseResult
        self._history: dict[str, list[dict[str, Any]]] = {}    # case_id -> [events]
        self._model_work: dict[str, list[dict[str, Any]]] = {} # case_id -> [payloads]
        # Idempotency: key -> {"body_hash": str, "case_id": str|None, "event": Event}
        self._idem: dict[str, dict[str, Any]] = {}
        self._idem_guard = threading.Lock()

    # --- cases ---------------------------------------------------------------
    def save_case_result(self, result: dict[str, Any]) -> None:
        with self._lock:
            self._results[result["case_id"]] = result

    def get_case_result(self, case_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self._results.get(case_id)
            return dict(r) if r is not None else None

    def list_case_results(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._results.values()]

    # --- model work (durable, retrievable) -----------------------------------
    def persist_model_work(self, case_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._model_work.setdefault(case_id, []).append(payload)

    def get_model_work(self, case_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(p) for p in self._model_work.get(case_id, [])]

    # --- history (append-only; override never destroys the original) ----------
    def append_history(self, case_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            self._history.setdefault(case_id, []).append(event)

    def get_history(self, case_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._history.get(case_id, [])]

    # --- concurrency-safe idempotency ----------------------------------------
    def claim_idempotency(self, key: str, body_hash: str) -> "Claim":
        """Atomically claim an idempotency key.

        Returns a Claim. If we are the FIRST caller for this key, `claim.first` is True and
        this caller must run the adjudication then call `complete_idempotency`. If the key is
        already claimed with the SAME body, `claim.first` is False and `claim.event` is the one
        to wait on — when it fires the result is available under the recorded case_id. A same
        key with a DIFFERENT body raises IdempotencyConflict (409).

        Only ONE caller ever gets the "first" role, because the whole check-and-insert runs
        under `_idem_guard` — this is the unique-constraint analogue, not read-then-write.
        """
        with self._idem_guard:
            existing = self._idem.get(key)
            if existing is None:
                event = threading.Event()
                self._idem[key] = {"body_hash": body_hash, "case_id": None, "event": event}
                return Claim(event=event, first=True)
            if existing["body_hash"] != body_hash:
                raise IdempotencyConflict(key)
            return Claim(event=existing["event"], first=False)

    def complete_idempotency(self, key: str, case_id: str) -> None:
        with self._idem_guard:
            rec = self._idem.get(key)
            if rec is not None:
                rec["case_id"] = case_id
                rec["event"].set()

    def idempotent_case_id(self, key: str) -> str | None:
        with self._idem_guard:
            rec = self._idem.get(key)
            return rec["case_id"] if rec else None


class _FirstClaim:  # retained name-free; see Claim below
    pass


@dataclass
class Claim:
    """The outcome of claim_idempotency: `first` says whether this caller owns the key and
    must run the adjudication; `event` fires when the owner completes."""

    event: "threading.Event"
    first: bool


def is_first_claim(obj: object) -> bool:
    return isinstance(obj, Claim) and obj.first
