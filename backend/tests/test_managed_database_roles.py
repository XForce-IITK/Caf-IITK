"""Migrations on a managed database such as RDS (CAFIITK-190, NFR-40).

There the login user is not a superuser, only CREATEROLE and CREATEDB, so it may
switch to caf_app and caf_agent only if the migrations grant it the roles. The
roles are cluster-wide, so this needs its own server: on the shared test
container a superuser created them already.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer

BACKEND_DIR = Path(__file__).resolve().parent.parent
LOGIN_USER = "master"


@pytest.fixture(scope="module")
def managed_engine() -> Iterator[Engine]:
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        superuser = create_engine(postgres.get_connection_url(), isolation_level="AUTOCOMMIT")
        with superuser.connect() as conn:
            conn.execute(text(f"CREATE ROLE {LOGIN_USER} LOGIN PASSWORD 'pw' CREATEROLE CREATEDB"))
            conn.execute(text(f"CREATE DATABASE managed OWNER {LOGIN_USER}"))
        superuser.dispose()

        url = (
            make_url(postgres.get_connection_url())
            .set(username=LOGIN_USER, password="pw", database="managed")
            .render_as_string(hide_password=False)
        )
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")

        engine = create_engine(url)
        yield engine
        engine.dispose()


@pytest.mark.parametrize("role", ["caf_app", "caf_agent"])
def test_the_login_user_may_switch_to_each_role(managed_engine: Engine, role: str) -> None:
    with managed_engine.connect() as conn, conn.begin():
        conn.execute(text(f"SET LOCAL ROLE {role}"))
        assert conn.scalar(text("SELECT current_user")) == role


def test_the_audit_log_stays_append_only(managed_engine: Engine) -> None:
    with managed_engine.connect() as conn:
        assert not conn.scalar(text("SELECT has_table_privilege('caf_app', 'audit_log', 'UPDATE')"))
        assert not conn.scalar(text("SELECT has_table_privilege('caf_app', 'audit_log', 'DELETE')"))
