"""Add local identities and owned conversations.

Revision ID: 20261022_02
Revises: 20261022_01
"""

import sqlalchemy as sa
from alembic import op

revision = "20261022_02"
down_revision = "20261022_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    count = connection.scalar(sa.text("SELECT count(*) FROM chat_sessions"))
    if count:
        raise RuntimeError(
            "Legacy sessions exist; back up the database and run "
            "python -m app.cli purge-legacy --confirm before upgrading"
        )
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.user_id")),
        sa.CheckConstraint("role IN ('user', 'admin')"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "login_attempts",
        sa.Column("attempt_id", sa.String(36), primary_key=True),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("email_normalized", sa.String(255), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(timezone=True)),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("unlocked_at", sa.DateTime(timezone=True)),
        sa.Column("unlocked_by", sa.String(36), sa.ForeignKey("users.user_id")),
        sa.UniqueConstraint("ip", "email_normalized"),
    )
    op.create_index(
        "ix_login_attempts_email_normalized", "login_attempts", ["email_normalized"]
    )
    op.create_table(
        "auth_audit",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.user_id")),
        sa.Column("target_id", sa.String(36), sa.ForeignKey("users.user_id")),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
    )
    op.add_column("chat_sessions", sa.Column("user_id", sa.String(36), nullable=False))
    op.create_foreign_key(
        "fk_chat_sessions_user_id", "chat_sessions", "users", ["user_id"], ["user_id"]
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_constraint("fk_chat_sessions_user_id", "chat_sessions", type_="foreignkey")
    op.drop_column("chat_sessions", "user_id")
    op.drop_table("auth_audit")
    op.drop_index("ix_login_attempts_email_normalized", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
