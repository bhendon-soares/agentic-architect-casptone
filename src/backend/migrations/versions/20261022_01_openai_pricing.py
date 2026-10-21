"""Activate standard direct OpenAI gpt-4.1-mini rates for new runs.

Revision ID: 20261022_01
Revises: 20261021_01
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "20261022_01"
down_revision = "20261021_01"
branch_labels = None
depends_on = None

PRICES = {
    "input": ("1858a2ac-c6c3-4b91-8f4e-94e3a646d531", "0.40"),
    "cache": ("1858a2ac-c6c3-4b91-8f4e-94e3a646d532", "0.10"),
    "output": ("1858a2ac-c6c3-4b91-8f4e-94e3a646d533", "1.60"),
}


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    pricing = sa.table(
        "pricing_config_versions",
        sa.column("pricing_config_id", sa.String),
        sa.column("model", sa.String),
        sa.column("deployment_id", sa.String),
        sa.column("currency", sa.String),
        sa.column("token_type", sa.String),
        sa.column("rate_per_million", sa.Numeric),
        sa.column("valid_from", sa.DateTime(timezone=True)),
        sa.column("valid_until", sa.DateTime(timezone=True)),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
    )
    op.bulk_insert(
        pricing,
        [
            {
                "pricing_config_id": price_id,
                "model": "openai/gpt-4.1-mini",
                "deployment_id": "openai",
                "currency": "USD",
                "token_type": kind,
                "rate_per_million": rate,
                "valid_from": now,
                "valid_until": None,
                "active": True,
                "created_at": now,
            }
            for kind, (price_id, rate) in PRICES.items()
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM pricing_config_versions WHERE pricing_config_id IN :ids")
        .bindparams(sa.bindparam("ids", expanding=True))
        .params(ids=[price_id for price_id, _ in PRICES.values()])
    )
