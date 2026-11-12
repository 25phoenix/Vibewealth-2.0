import shutil
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings
from app.core.database import engine
from app.core.migration_config import get_migration_url, include_object, target_metadata
from app.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"


def load_alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def test_alembic_configuration_loads_without_embedded_database_url() -> None:
    config = load_alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    assert Path(script_directory.dir).resolve() == (BACKEND_DIR / "alembic").resolve()
    assert config.get_main_option("sqlalchemy.url") is None


def test_alembic_uses_application_metadata_and_settings() -> None:
    assert target_metadata is Base.metadata
    assert {table.name for table in target_metadata.sorted_tables} == {
        "accounts",
        "auth_sessions",
        "assistant_conversations",
        "assistant_messages",
        "budgets",
        "categories",
        "goal_entries",
        "savings_goals",
        "transactions",
        "users",
    }
    assert get_migration_url() == get_settings().sqlalchemy_url
    assert engine.url == get_migration_url()
    assert get_migration_url().drivername == "postgresql+psycopg"


def test_autogeneration_ignores_unmodeled_reflected_tables() -> None:
    assert include_object(object(), "existing_table", "table", True, None) is False
    assert include_object(object(), "modeled_table", "table", True, object()) is True
    assert include_object(object(), "new_table", "table", False, None) is True


def test_goal_migration_follows_auth_session_revision() -> None:
    script_directory = ScriptDirectory.from_config(load_alembic_config())

    revisions = list(script_directory.walk_revisions())
    assert len(revisions) == 3
    assert script_directory.get_heads() == [revisions[0].revision]
    assert revisions[0].revision == "6b9c2f1d4a80"
    assert revisions[0].down_revision == "e7a30067c81c"
    assert revisions[0].doc == "add goal descriptions and goal-scoped ledger index"
    assert revisions[1].revision == "e7a30067c81c"
    assert revisions[1].down_revision == "4da570f34c63"
    assert revisions[1].doc == "add authentication sessions"
    assert revisions[2].revision == "4da570f34c63"
    assert revisions[2].down_revision is None
    assert revisions[2].doc == "initial schema"


def test_upgrade_and_downgrade_use_isolated_sqlite_database(tmp_path: Path) -> None:
    """Exercise migration execution using a temporary script and in-memory DB."""

    script_location = tmp_path / "test_migrations"
    versions_directory = script_location / "versions"
    versions_directory.mkdir(parents=True)
    shutil.copyfile(ALEMBIC_DIR / "env.py", script_location / "env.py")
    migration = versions_directory / "0001_migration_probe.py"
    migration.write_text(
        """from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('migration_probe', sa.Column('id', sa.Integer(), primary_key=True))

def downgrade():
    op.drop_table('migration_probe')
""",
        encoding="utf-8",
    )

    test_engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with test_engine.connect() as connection:
            config = load_alembic_config()
            config.set_main_option("script_location", str(script_location))
            config.attributes["connection"] = connection

            command.upgrade(config, "head")
            assert inspect(connection).has_table("migration_probe")

            command.downgrade(config, "base")
            assert not inspect(connection).has_table("migration_probe")
    finally:
        test_engine.dispose()
