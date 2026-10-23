"""Revoke individual JWT sessions on logout.

Revision ID: 20261022_03
Revises: 20261022_02
"""

import sqlalchemy as sa
from alembic import op

revision = "20261022_03"
down_revision = "20261022_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_sessions",
        sa.Column("jti", sa.String(36), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("revoked_sessions")
