"""Shared, connection-free safeguards for destructive PostgreSQL test fixtures."""

import os

import pytest
from sqlalchemy.engine import URL, make_url

from app.core.config import get_settings


def postgres_test_url() -> URL:
    """Require explicit opt-in and establish the target before creating an engine."""

    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION=1 to enable PostgreSQL integration")

    raw_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Set POSTGRES_TEST_DATABASE_URL to the dedicated test database")

    try:
        test_url = make_url(raw_url)
    except Exception:
        pytest.fail("POSTGRES_TEST_DATABASE_URL could not be parsed safely", pytrace=False)

    # SQLAlchemy merges URL query values into driver connection arguments.
    # No query options are needed here, including otherwise harmless ones.
    if test_url.query:
        pytest.fail("POSTGRES_TEST_DATABASE_URL must not contain query parameters", pytrace=False)
    if test_url.drivername != "postgresql+psycopg":
        pytest.fail("POSTGRES_TEST_DATABASE_URL must use postgresql+psycopg", pytrace=False)
    if test_url.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("POSTGRES_TEST_DATABASE_URL must target localhost", pytrace=False)
    if test_url.port != 5432:
        pytest.fail("POSTGRES_TEST_DATABASE_URL must use port 5432", pytrace=False)
    if test_url.username != "vibewealth_app":
        pytest.fail("POSTGRES_TEST_DATABASE_URL must use the vibewealth_app user", pytrace=False)
    if test_url.database != "vibewealth_test":
        pytest.fail("POSTGRES_TEST_DATABASE_URL must target vibewealth_test", pytrace=False)
    if not test_url.password:
        pytest.fail("POSTGRES_TEST_DATABASE_URL must include a password", pytrace=False)

    try:
        application_url = get_settings().sqlalchemy_url
    except Exception:
        pytest.fail("Application database configuration could not be validated safely", pytrace=False)
    if application_url.query:
        pytest.fail("Application database URL must not contain query parameters during integration tests", pytrace=False)
    if application_url.database in {None, "", "vibewealth_test"}:
        pytest.fail("The configured application database must remain separate from vibewealth_test", pytrace=False)
    if application_url.port != 5432:
        pytest.fail("The configured application database must use port 5432", pytrace=False)

    return test_url
