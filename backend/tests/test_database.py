import os
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import Session

from app.core import database
from app.core.config import Settings


def test_database_url_uses_url_create_for_password_with_special_characters() -> None:
    settings = Settings(
        _env_file=None,
        database_url=None,
        postgres_db="test_db",
        postgres_user="test_user",
        postgres_password=SecretStr("p@ss:/?#% word"),
        postgres_port=5433,
    )

    url = settings.sqlalchemy_url

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "test_user"
    assert url.password == "p@ss:/?#% word"
    assert url.host == "localhost"
    assert url.port == 5433
    assert url.database == "test_db"
    assert "p@ss:/?#% word" not in repr(settings)


def test_supplied_database_url_is_parsed_and_preserved() -> None:
    supplied_url = URL.create(
        "postgresql+psycopg",
        username="configured_user",
        password="p@ss:/?#%",
        host="db.example.test",
        port=5544,
        database="configured_db",
    )
    settings = Settings(
        _env_file=None,
        database_url=supplied_url.render_as_string(hide_password=False),
    )

    assert settings.sqlalchemy_url == supplied_url


def test_invalid_database_url_is_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///not-postgres.db")


def test_sqlalchemy_connection_can_execute_select_one() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_postgresql_connection_when_integration_enabled() -> None:
    """Opt-in integration check against the configured local PostgreSQL service."""

    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION=1 to check the configured PostgreSQL service")

    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_get_db_creates_and_closes_request_session(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=Session)
    session.in_transaction.return_value = False
    monkeypatch.setattr(database, "SessionLocal", lambda: session)

    dependency = database.get_db()
    assert next(dependency) is session
    with pytest.raises(StopIteration):
        next(dependency)

    session.close.assert_called_once()
    session.rollback.assert_not_called()


def test_get_db_rolls_back_unfinished_transaction_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    session.in_transaction.return_value = True
    monkeypatch.setattr(database, "SessionLocal", lambda: session)

    dependency = database.get_db()
    next(dependency)
    with pytest.raises(StopIteration):
        next(dependency)

    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_get_db_rolls_back_and_closes_after_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=Session)
    session.in_transaction.side_effect = [False]
    monkeypatch.setattr(database, "SessionLocal", lambda: session)

    dependency = database.get_db()
    next(dependency)
    with pytest.raises(RuntimeError, match="request failed"):
        dependency.throw(RuntimeError("request failed"))

    session.rollback.assert_called_once()
    session.close.assert_called_once()
