"""add discount_rules.name

FR-22: every time-of-day discount rule has a name the Administrator sees, such as
"Early bird". Rules created before this revision are named "Discount".

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-04 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "discount_rules",
        sa.Column("name", sa.String(length=60), nullable=False, server_default="Discount"),
    )
    # The default only names existing rows; new rules must be given a name.
    op.alter_column("discount_rules", "name", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("discount_rules", "name")
