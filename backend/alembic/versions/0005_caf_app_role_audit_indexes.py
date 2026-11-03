"""caf_app role, append-only on audit_log; audit search indexes

NFR-26, FR-48: the application's database role has no UPDATE or DELETE on the
audit table. Every application transaction runs `SET LOCAL ROLE caf_app`
(app/db/session.py), so PostgreSQL itself refuses to change an audit entry,
whatever the code tries.

FR-49: indexes for searching the log by entity, the order an entry concerns,
actor, action and time.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-03 21:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "caf_app"

# Counter and security entries name their order in after.order_id (FR-47).
ORDER_ID_INDEX = "ix_audit_log_after_order_id"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_at", "audit_log", ["at"])
    op.execute(f"CREATE INDEX {ORDER_ID_INDEX} ON audit_log ((after ->> 'order_id'))")

    # Roles are cluster-wide, so another database on the server may already have it.
    op.execute(
        "DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') "
        f"THEN CREATE ROLE {ROLE} NOLOGIN; END IF; END $$"
    )
    # The login user switches to caf_app per transaction, so it must be a member. A
    # superuser already may; on a managed database (RDS) the creator needs the grant.
    op.execute(f"GRANT {ROLE} TO CURRENT_USER")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")
    # Append-only: the audit log may be read and added to, never changed (FR-48).
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM {ROLE}")
    # Migrations are not the application's business.
    op.execute(f"REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM {ROLE}")
    # Tables later migrations create get the same rights; audit_log already exists.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {ROLE}"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
    # The role itself is left in place: it is cluster-wide and may serve other databases.
    op.drop_index(ORDER_ID_INDEX, table_name="audit_log")
    for name in ("ix_audit_log_at", "ix_audit_log_action", "ix_audit_log_actor_id"):
        op.drop_index(name, table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
