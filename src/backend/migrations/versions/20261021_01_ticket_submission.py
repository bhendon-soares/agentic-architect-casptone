"""Record ticket submission initiation and measured cache writes.

Revision ID: 20261021_01
Revises: 20261019_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20261021_01"
down_revision = "20261019_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_run_telemetry", sa.Column("tokens_cache_write", sa.Integer()))
    op.add_column(
        "tickets", sa.Column("submission_started_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("tickets", "submission_started_at")
    op.drop_column("agent_run_telemetry", "tokens_cache_write")
