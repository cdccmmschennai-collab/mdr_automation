"""Database fixtures for the persistence suite.

**Isolation strategy.** The suite connects to the server named by
`MDR_TEST_DATABASE_URL`, creates a throwaway database of its own for the
session, builds the schema in it *by running the Alembic migrations*, and drops
it at the end. Nothing runs against a database anyone else is using, and the
schema under test is the schema production will get - not one built by
`create_all`, which could pass while the migration was broken.

Each test then runs inside a transaction that is rolled back afterwards, so
tests cannot see each other's rows and the order they run in does not matter.

**Skipping.** With no `MDR_TEST_DATABASE_URL` the whole suite skips, loudly
enough to say what to set. A PostgreSQL server is a real prerequisite; the
alternative - falling back to SQLite - would mean testing a database the
product does not use, and would silently pass on JSONB, `TIMESTAMPTZ` and
`ondelete` behaviour that SQLite handles differently or not at all.

    docker run -d --name mdr-postgres-test -e POSTGRES_USER=mdr \\
        -e POSTGRES_PASSWORD=mdr -e POSTGRES_DB=mdr -p 55432:5432 postgres:16
    set MDR_TEST_DATABASE_URL=postgresql+psycopg://mdr:mdr@localhost:55432/mdr
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

BACKEND = Path(__file__).resolve().parents[2]

#: Where the persistence suite is allowed to create databases.
TEST_URL_ENV = "MDR_TEST_DATABASE_URL"

SKIP_REASON = (
    f"{TEST_URL_ENV} is not set: the persistence suite needs a PostgreSQL "
    f"server. e.g. {TEST_URL_ENV}="
    "postgresql+psycopg://mdr:mdr@localhost:55432/mdr"
)


def _configured_url() -> str | None:
    return os.environ.get(TEST_URL_ENV, "").strip() or None


@pytest.fixture(scope="session")
def database_url() -> str:
    """A URL for a freshly created, session-scoped throwaway database.

    Created and dropped through the maintenance connection on `postgres`, with
    AUTOCOMMIT: `CREATE DATABASE` cannot run inside a transaction.
    """
    configured = _configured_url()
    if configured is None:
        pytest.skip(SKIP_REASON, allow_module_level=True)

    url = make_url(configured)
    name = f"mdr_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url.set(database="postgres"),
                          isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:                       # pragma: no cover
        pytest.skip(f"cannot reach the PostgreSQL server at "
                    f"{url.render_as_string(hide_password=True)}: {exc}",
                    allow_module_level=True)

    try:
        yield url.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            # Terminate stragglers first: DROP DATABASE fails while anything
            # is still connected, and a failure here leaves litter behind.
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"),
                {"name": name})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


@pytest.fixture(scope="session")
def alembic_config(database_url: str):
    """An Alembic config pointed at the throwaway database."""
    from alembic.config import Config

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    # env.py reads this variable in preference to the application settings.
    os.environ["MDR_ALEMBIC_DATABASE_URL"] = database_url
    return config


@pytest.fixture(scope="session")
def migrated_engine(database_url: str, alembic_config):
    """The throwaway database with every migration applied.

    Session-scoped: the migrations run once. Tests get isolation from the
    per-test transaction below, not from rebuilding the schema each time.
    """
    from alembic import command

    command.upgrade(alembic_config, "head")
    engine = create_engine(database_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(migrated_engine) -> Session:
    """A session in a transaction that is rolled back when the test ends.

    The outer transaction belongs to the fixture and is never committed, so a
    test may call `session.commit()` - which commits only into the enclosing
    transaction - and still leave the database as it found it.
    """
    connection = migrated_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, expire_on_commit=False,
                           join_transaction_mode="create_savepoint")
    db = factory()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


# -- small builders, so the tests read as what they are testing --------------

def make_digest(seed: str) -> str:
    """A valid-looking 64-character digest derived from `seed`."""
    import hashlib
    return hashlib.sha256(seed.encode()).hexdigest()


@pytest.fixture
def plant(session):
    from app.infrastructure.persistence.repositories import PlantRepository
    return PlantRepository(session).add(code=f"PLANT-{uuid.uuid4().hex[:8]}",
                                        name="QatarEnergy TN")


@pytest.fixture
def rule_set(session):
    from app.infrastructure.persistence.repositories import RuleSetRepository
    return RuleSetRepository(session).add(
        version_label=f"A-{uuid.uuid4().hex[:8]}",
        source_filename="INPUT-KEYWORDS  FOR MDR TOOL.xlsx",
        content_sha256=make_digest(uuid.uuid4().hex),
        required_rule_count=51, not_required_rule_count=12, sow_rule_count=30,
    )


@pytest.fixture
def submission(session, plant):
    from app.infrastructure.persistence.repositories import SubmissionRepository
    return SubmissionRepository(session).add(
        plant_id=plant.id,
        source_filename="20260720-184-Transmittal Log (9) MDR.xlsx",
        source_sha256=make_digest("workbook-9"),
        source_byte_size=12_345_678,
    )
