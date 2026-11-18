"""Isolated PostgreSQL migration checks using disposable schemas only."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from tests.postgres_safety import postgres_test_url

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_goal_migration_upgrade_and_downgrade_in_isolated_postgres_schema():
    test_url = postgres_test_url()

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
            transaction_columns = {
                column["name"] for column in inspector.get_columns("transactions")
            }
            assert {"idempotency_key", "request_fingerprint"} <= transaction_columns
            unique_constraints = {
                item["name"]
                for item in inspector.get_unique_constraints("transactions")
            }
            assert "uq_transactions_user_idempotency_key" in unique_constraints
            check_constraints = {
                item["name"]
                for item in inspector.get_check_constraints("transactions")
            }
            assert "ck_transactions_idempotency_pair" in check_constraints

            command.downgrade(config, "6b9c2f1d4a80")
            transaction_columns = {
                column["name"] for column in inspect(connection).get_columns("transactions")
            }
            assert "idempotency_key" not in transaction_columns
            assert "request_fingerprint" not in transaction_columns
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
