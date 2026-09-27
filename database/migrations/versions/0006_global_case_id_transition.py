"""allow canonical global case IDs during the coordinated archive remap

Revision ID: 0006_global_case_id_transition
Revises: 0005_archive_history
Create Date: 2026-09-26

The one-time cross-schema remap is coordinated outside this database package. Keep the
legacy archive form valid during the brief migration window so this schema migration can
be applied before the remap; all newly imported and seeded archive cases use DSP-######.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision = "0006_global_case_id_transition"
down_revision = "0005_archive_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE case_archive.archive_cases "
        "DROP CONSTRAINT archive_cases_archive_case_id_check"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_cases "
        "ADD CONSTRAINT archive_cases_archive_case_id_check "
        "CHECK (archive_case_id ~ '^DSP-(ARCH-)?[0-9]{6}$')"
    )


def downgrade() -> None:
    # Downgrade is valid only before any canonical DSP-###### archive IDs are written.
    op.execute(
        "ALTER TABLE case_archive.archive_cases "
        "DROP CONSTRAINT archive_cases_archive_case_id_check"
    )
    op.execute(
        "ALTER TABLE case_archive.archive_cases "
        "ADD CONSTRAINT archive_cases_archive_case_id_check "
        "CHECK (archive_case_id ~ '^DSP-ARCH-[0-9]{6}$')"
    )
