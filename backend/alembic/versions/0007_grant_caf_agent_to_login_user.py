"""grant caf_agent to the login user

NFR-25: the agent's transactions run `SET LOCAL ROLE caf_agent`
(app/modules/agent/repository.py), so the login user must be a member of the
role. A superuser already may. On a managed database (RDS) the login user is
not a superuser, and since PostgreSQL 16 creating a role does not let its
creator switch to it, so every agent run failed with "permission denied to set
role". 0005 grants caf_app the same way.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05 23:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("GRANT caf_agent TO CURRENT_USER")


def downgrade() -> None:
    """Downgrade schema."""
    # Left in place: a superuser never needed it, and on RDS 0002 cannot work without it.
    pass
