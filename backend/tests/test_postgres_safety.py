"""Connection-free regression tests for both PostgreSQL integration safeguards."""

from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine, URL

from tests import postgres_safety


class DatabaseConnectionAttempt(RuntimeError):
    """A safety regression attempted forbidden database access."""


@pytest.fixture(autouse=True)
def connection_guard(monkeypatch):
    attempts = []

    def forbid_connection(*args, **kwargs):
        # Record no arguments: they could contain private connection details.
        attempts.append(True)
        raise DatabaseConnectionAttempt("Safety validation attempted database access")

    monkeypatch.setattr(Engine, "connect", forbid_connection)
    monkeypatch.setattr(Engine, "raw_connection", forbid_connection)
    yield
    # A swallowed exception must still fail the test during fixture teardown.
    assert not attempts, "Safety validation attempted database access"


@pytest.fixture
def configured_target(monkeypatch):
    monkeypatch.setenv("RUN_POSTGRES_INTEGRATION", "1")
    target = URL.create(
        "postgresql+psycopg",
        username="vibewealth_app",
        password="synthetic-test-password",
        host="localhost",
        port=5432,
        database="vibewealth_test",
    )
    monkeypatch.setenv(
        "POSTGRES_TEST_DATABASE_URL", target.render_as_string(hide_password=False)
    )
    monkeypatch.setattr(
        postgres_safety,
        "get_settings",
        lambda: SimpleNamespace(sqlalchemy_url=target.set(database="vibewealth")),
    )
    return target


@pytest.mark.parametrize("opt_in", [None, "", "0", "true"])
def test_postgres_safety_requires_exact_explicit_opt_in(monkeypatch, configured_target, opt_in):
    if opt_in is None:
        monkeypatch.delenv("RUN_POSTGRES_INTEGRATION")
    else:
        monkeypatch.setenv("RUN_POSTGRES_INTEGRATION", opt_in)
    # Skip before even parsing the URL or reading application settings.
    monkeypatch.setattr(postgres_safety, "make_url", lambda _: pytest.fail("URL parsed before opt-in"))
    monkeypatch.setattr(postgres_safety, "get_settings", lambda: pytest.fail("Settings read before opt-in"))
    with pytest.raises(pytest.skip.Exception, match="RUN_POSTGRES_INTEGRATION"):
        postgres_safety.postgres_test_url()


@pytest.mark.parametrize("raw_url", [None, ""])
def test_postgres_safety_requires_test_url_without_application_fallback(monkeypatch, configured_target, raw_url):
    if raw_url is None:
        monkeypatch.delenv("POSTGRES_TEST_DATABASE_URL")
    else:
        monkeypatch.setenv("POSTGRES_TEST_DATABASE_URL", raw_url)
    monkeypatch.setattr(postgres_safety, "get_settings", lambda: pytest.fail("Application fallback attempted"))
    with pytest.raises(pytest.skip.Exception, match="POSTGRES_TEST_DATABASE_URL"):
        postgres_safety.postgres_test_url()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_postgres_safety_accepts_only_dedicated_local_target(monkeypatch, configured_target, host):
    target = configured_target.set(host=host)
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_URL", target.render_as_string(hide_password=False))
    assert postgres_safety.postgres_test_url() == target


@pytest.mark.parametrize("parameter", [
    "dbname", "database", "user", "username", "host", "hostaddr", "port",
    "service", "options", "password", "sslmode", "application_name",
])
def test_postgres_safety_rejects_all_query_parameters(monkeypatch, configured_target, parameter):
    target = configured_target.set(query={parameter: "override"})
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_URL", target.render_as_string(hide_password=False))
    with pytest.raises(pytest.fail.Exception, match="must not contain query parameters"):
        postgres_safety.postgres_test_url()


@pytest.mark.parametrize("changes", [
    {"drivername": "postgresql"},
    {"host": "db.example.test"},
    {"port": 5433},
    {"username": "postgres"},
    {"database": "vibewealth"},
    {"password": ""},
])
def test_postgres_safety_rejects_wrong_identity(monkeypatch, configured_target, changes):
    target = configured_target.set(**changes)
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_URL", target.render_as_string(hide_password=False))
    with pytest.raises(pytest.fail.Exception):
        postgres_safety.postgres_test_url()


def test_postgres_safety_suppresses_malformed_url_details(monkeypatch, configured_target):
    monkeypatch.setenv("POSTGRES_TEST_DATABASE_URL", "not-a-valid-url")
    with pytest.raises(pytest.fail.Exception, match="could not be parsed safely"):
        postgres_safety.postgres_test_url()


@pytest.mark.parametrize("changes", [
    {"database": "vibewealth_test"},
    {"database": ""},
    {"port": 5433},
    {"query": {"dbname": "vibewealth_test"}},
])
def test_postgres_safety_requires_unambiguous_separate_application_database(monkeypatch, configured_target, changes):
    application = configured_target.set(database="vibewealth").set(**changes)
    monkeypatch.setattr(postgres_safety, "get_settings", lambda: SimpleNamespace(sqlalchemy_url=application))
    with pytest.raises(pytest.fail.Exception):
        postgres_safety.postgres_test_url()


def test_postgres_safety_fails_closed_when_application_settings_cannot_load(monkeypatch, configured_target):
    def invalid_settings():
        raise ValueError("Synthetic private configuration detail")

    monkeypatch.setattr(postgres_safety, "get_settings", invalid_settings)
    with pytest.raises(pytest.fail.Exception, match="could not be validated safely") as error:
        postgres_safety.postgres_test_url()
    assert "private configuration" not in str(error.value)
