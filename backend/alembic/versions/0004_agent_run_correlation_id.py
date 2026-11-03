"""add agent_runs.correlation_id

NFR-29: an agent run records the correlation ID of the request (or scheduler job)
that queued it, so the worker can log the run under that ID.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("agent_runs", sa.Column("correlation_id", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("agent_runs", "correlation_id")
