"""Preserve actual Ryde service names alongside historical fictional tiers."""
from alembic import op
revision = "0009_ryde_service_names"
down_revision = "0008_canonical_record_ids"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE ride_data.rides DROP CONSTRAINT IF EXISTS rides_service_tier_check")
    op.execute("ALTER TABLE ride_data.rides ADD CONSTRAINT rides_service_tier_check CHECK (service_tier IN ('standard','premium','assist','RydeX','RydeXL','RydePET','RydePOOL','RydeFLASH','RydeHIRE','RydeSEND','RydeTAXI'))")


def downgrade():
    # Never relabel a stored service to a fictional tier or delete source records.
    op.execute("ALTER TABLE ride_data.rides DROP CONSTRAINT IF EXISTS rides_service_tier_check")
