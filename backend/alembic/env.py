"""Alembic migration environment for the VibeWealth backend."""

from logging.config import fileConfig

from alembic import context

from app.core.database import engine
from app.core.migration_config import get_migration_url, include_object, target_metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def configure_migrations(connection=None) -> None:
    """Configure Alembic using shared settings and the existing Base metadata."""

    context.configure(
        connection=connection,
        url=None if connection is not None else get_migration_url(),
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        transactional_ddl=True,
        transaction_per_migration=True,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else {},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Run migrations without opening a database connection."""

    configure_migrations()


def run_migrations_online() -> None:
    """Run migrations with either a supplied test connection or the app engine."""

    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        configure_migrations(supplied_connection)
        return

    with engine.connect() as connection:
        configure_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
