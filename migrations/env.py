"""Flask‑Migrate environment file.

This file sets up the Alembic context to work with a Flask application.
It imports the Flask application via ``current_app`` and pulls the
``db.metadata`` from the app's SQLAlchemy extension.  When running
migrations, Alembic will use this metadata to autogenerate changes.

The offline and online migration functions are standard Alembic hooks
adapted for use with Flask's application context.
"""
from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

# This is the Alembic Config object, which provides access to values
# within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.  This line sets up loggers
# basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

# Try to retrieve the MetaData from the Flask app.  When running under
# ``flask db`` commands, ``current_app`` should be available and will
# expose the database via ``current_app.extensions['migrate'].db``.
try:
    target_metadata = current_app.extensions['migrate'].db.metadata
except Exception as exc:  # pragma: no cover
    logger.error("Could not get app metadata: %s", exc)
    target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.  By
    skipping the Engine creation we don't even need a DBAPI to be
    available.  Calls to context.execute() here emit the given string to
    the script output.
    """
    # Grab the connection URL from the app's engine if available.  The
    # ``replace('%', '%%')`` is required to escape percent signs in the
    # connection string when Alembic parses the ini file.
    url = None
    try:
        url = str(current_app.extensions['migrate'].db.engine.url)
    except Exception:
        url = config.get_main_option('sqlalchemy.url')
    if url:
        url = url.replace('%', '%%')
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
    # In online mode we need to create an Engine and associate a connection
    # with the context.  We pull the engine from the Flask app to ensure
    # the same configuration used by the application is used here.
    connectable = None
    try:
        connectable = current_app.extensions['migrate'].db.engine
    except Exception:
        connectable = None
    if connectable is None:
        url = config.get_main_option('sqlalchemy.url')
        if not url:
            raise RuntimeError(
                'No database URL provided.  Set SQLALCHEMY_DATABASE_URI or '
                'sqlalchemy.url in alembic.ini'
            )
        from sqlalchemy import create_engine
        connectable = create_engine(url)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
