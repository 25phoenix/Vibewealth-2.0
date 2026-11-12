"""Isolated PostgreSQL migration checks using disposable schemas only."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_goal_migration_upgrade_and_downgrade_in_isolated_postgres_schema():
    raw_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Set POSTGRES_TEST_DATABASE_URL to the isolated local test database")

    test_url = make_url(raw_url)
    application_url = get_settings().sqlalchemy_url
    assert test_url.drivername == "postgresql+psycopg"
    assert test_url.host in {"localhost", "127.0.0.1", "::1"}
    assert test_url.port == application_url.port == 5432
    assert test_url.database == "vibewealth_test"
    assert test_url.database != application_url.database

    engine = create_engine(test_url, pool_pre_ping=True)
    schema = f"alembic_test_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        with engine.connect() as connection:
            connection.execute(text(f'SET search_path TO "{schema}"'))
            connection.commit()

            config = Config(str(BACKEND_DIR / "alembic.ini"))
            config.attributes["connection"] = connection

            command.upgrade(config, "head")
            inspector = inspect(connection)
            assert "description" in {
                column["name"] for column in inspector.get_columns("savings_goals")
            }
            indexes = {
                index["name"]
                for index in inspector.get_indexes("goal_entries")
            }
            assert "ix_goal_entries_user_goal_created" in indexes

            command.downgrade(config, "e7a30067c81c")
            inspector = inspect(connection)
            assert "description" not in {
                column["name"] for column in inspector.get_columns("savings_goals")
            }
            assert "ix_goal_entries_user_goal_created" not in {
                index["name"] for index in inspector.get_indexes("goal_entries")
            }
            assert "goal_entries" in inspector.get_table_names()

            command.upgrade(config, "head")
            assert "description" in {
                column["name"] for column in inspect(connection).get_columns("savings_goals")
            }
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
