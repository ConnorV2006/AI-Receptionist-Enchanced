"""Flask‑Migrate environment configuration.

This file sets up Alembic with the Flask application context and metadata so
that migrations can be autogenerate and applied. It is a simplified version
of the env.py that would normally be created by ``flask db init``. Adjust
configuration options as needed.
"""
from __future__ import with_statement

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

# Alembic Config object provides access to values within the .ini file in
# use by Alembic. This module uses the config object for referencing
# configuration values.
config = context.config

# Interpret the config file for Python logging. This line sets up loggers
# basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

# Provide the metadata for 'autogenerate' support. Flask‑Migrate adds a
# ``extensions['migrate'].db`` attribute to the Flask application which has the
# SQLAlchemy metadata. If this attribute is missing the app might not be
# configured properly.
try:
    target_metadata = current_app.extensions['migrate'].db.metadata
except Exception:
    target_metadata = None


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a connection
    with the context. Flask‑Migrate takes care of binding the engine via
    ``current_app.extensions['migrate'].db.engine`` when the app context is
    active.
    """
    # Use the engine associated with the Flask application
    connectable = current_app.extensions['migrate'].db.engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# Run the migrations. Since Flask automatically manages the app context when
# using the 'flask db' commands, we don't have to handle offline mode here.
run_migrations_online()