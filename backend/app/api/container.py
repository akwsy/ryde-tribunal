"""Application container: builds and holds the wired dependencies. A single place to swap the
DB reader (fixtures in tests, the DB specialist's Postgres reader at integration) and the
provider/external source.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.evidence.external import DisabledExternalSource, ExternalInfoSource
from app.orchestration.orchestrator import Orchestrator
from app.persistence.reader import DatabaseReader
from app.persistence.postgres_store import PostgresResultStore
from app.persistence.store import ResultStore
from app.policy.loader import PolicyDocument, load_policy
from app.providers.base import ModelProvider
from app.providers.deterministic_mock import DeterministicMockProvider
from app.providers.factory import build_provider
from app.settings import Settings, get_settings


@dataclass
class Container:
    settings: Settings
    reader: DatabaseReader
    provider: ModelProvider
    policy: PolicyDocument
    store: ResultStore
    external: ExternalInfoSource

    def orchestrator(self) -> Orchestrator:
        return Orchestrator(
            reader=self.reader,
            provider=self.provider,
            policy=self.policy,
            external=self.external,
            store=self.store,
            settings=self.settings,
            fallback_provider=DeterministicMockProvider(model="ryde-mock-judge-1"),
        )


def build_container(
    *,
    reader: DatabaseReader,
    settings: Settings | None = None,
    provider: ModelProvider | None = None,
    external: ExternalInfoSource | None = None,
    store: ResultStore | None = None,
) -> Container:
    settings = settings or get_settings()
    policy = load_policy(settings.policy_version, explicit_path=settings.policy_path or None)
    return Container(
        settings=settings,
        reader=reader,
        provider=provider or build_provider(settings),
        policy=policy,
        store=store or (
            PostgresResultStore(settings.tribunal_database_dsn)
            if settings.tribunal_database_dsn else ResultStore()
        ),
        external=external or DisabledExternalSource(),
    )
