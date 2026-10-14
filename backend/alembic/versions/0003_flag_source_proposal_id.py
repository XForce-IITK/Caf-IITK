"""widen menu_items.unavailable_source to hold a proposal ID

FR-53: approving an item-disable proposal records the proposal's ID (36
characters) as the flag's source; the column was VARCHAR(20).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "menu_items",
        "unavailable_source",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # A proposal ID does not fit back into 20 characters; record such flags as STAFF.
    op.execute(
        "UPDATE menu_items SET unavailable_source = 'STAFF' WHERE length(unavailable_source) > 20"
    )
    op.alter_column(
        "menu_items",
        "unavailable_source",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
