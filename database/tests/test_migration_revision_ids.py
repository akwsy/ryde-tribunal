from __future__ import annotations

import ast
from pathlib import Path


VERSIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"
ALEMBIC_VERSION_COLUMN_LIMIT = 32


def test_migration_revision_ids_fit_alembic_version_column() -> None:
    revisions: dict[str, Path] = {}

    for migration_path in sorted(VERSIONS_DIR.glob("*.py")):
        tree = ast.parse(migration_path.read_text(encoding="utf-8"))
        values: dict[str, object] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                        values[target.id] = ast.literal_eval(node.value)

        revision = values.get("revision")
        assert isinstance(revision, str), f"{migration_path.name} has no string revision ID"
        assert len(revision) <= ALEMBIC_VERSION_COLUMN_LIMIT, (
            f"{migration_path.name} revision ID {revision!r} exceeds Alembic's "
            f"{ALEMBIC_VERSION_COLUMN_LIMIT}-character version column"
        )
        assert revision not in revisions, f"duplicate revision ID {revision!r}"
        revisions[revision] = migration_path

        down_revision = values.get("down_revision")
        down_revisions = down_revision if isinstance(down_revision, tuple) else (down_revision,)
        for parent_revision in down_revisions:
            if parent_revision is not None:
                assert isinstance(parent_revision, str)
                assert len(parent_revision) <= ALEMBIC_VERSION_COLUMN_LIMIT, (
                    f"{migration_path.name} references overlong down_revision "
                    f"{parent_revision!r}"
                )
