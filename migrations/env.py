import os
from logging.config import fileConfig
from urllib.parse import quote_plus

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from app.core.config import Settings

# ================================
# MODELS
# ================================
from app.modules.user.models import User
from app.modules.wallet.models import Transaction, Wallet, ExchangeRate
from app.modules.group.models import Group, GroupMember, GroupTransactionMessage
from app.modules.ims.models import IMSAction
from app.modules.ims.models import ScheduledTransaction
from app.modules.gdpr.models import UserConsentAudit
# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
settings = Settings()

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url():
    # URL encode the password to handle special characters
    password = quote_plus(settings.POSTGRES_PASSWORD)  # type: ignore
    return f"postgresql://{settings.POSTGRES_USER}:{password}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.POSTGRES_DB}"


# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
