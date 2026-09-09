"""Alembic environment.

The URL comes from the application's settings, not from `alembic.ini`, so there
is exactly one place a database is named and no committed file holds a
credential. `MDR_ALEMBIC_DATABASE_URL` overrides it for the one case where the
migrations must run somewhere else than the application points - building a
throwaway test database.

`compare_type` and `compare_server_default` are on so that autogenerate notices
a column whose type or default changed, not only one that appeared or vanished.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

#: `backend/` on the path, so `app.*` imports the same way it does under pytest.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import load_settings                        # noqa: E402
from app.infrastructure.persistence.base import Base             # noqa: E402
from app.infrastructure.persistence import models                # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#: What autogenerate compares the database against. Importing `models` above is
#: what populates it - without that import the metadata is empty and
#: autogenerate would cheerfully propose dropping every table.
target_metadata = Base.metadata


def _database_url() -> str:
    override = os.environ.get("MDR_ALEMBIC_DATABASE_URL", "").strip()
    return override or load_settings().require_database_url()


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(), target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
        compare_type=True, compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against a live connection, in one transaction."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
