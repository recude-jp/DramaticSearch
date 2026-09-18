"""create agentkit schema

Revision ID: 0001
Revises:
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("dev_app", "biz_app")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS agentkit")
    for role in APP_ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    GRANT USAGE ON SCHEMA agentkit TO {role};
                    ALTER DEFAULT PRIVILEGES IN SCHEMA agentkit
                        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role};
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS agentkit CASCADE")
