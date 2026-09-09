"""Engine, sessions and transactions.

One `Engine` per process, created lazily the first time something asks for a
session, so that importing the application does not open a socket. A backend
started with no `MDR_DATABASE_URL` runs exactly as before; the failure happens
when persistence is used, and it names the variable to set.

**Schema is never created here.** There is no `create_all` in this module and
none anywhere in the application - not even for tests, which build their
throwaway database by running the migrations. The schema has exactly one
source, so a production database and a test database cannot be built from
different instructions and diverge without anything failing.

**Transactions are explicit.** `session_scope` commits on success and rolls
back on any exception, and it re-raises. Nothing here swallows a database
error: a failed write that returns quietly is worse than one that stops the
caller, because the caller then reports success.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ...core.config import Settings, settings as default_settings

#: Process-wide engine and session factory, built on first use.
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def get_engine(settings: Optional[Settings] = None) -> Engine:
    """The process-wide SQLAlchemy engine, created on first call.

    `pool_pre_ping` is on: a pooled connection that a restarted PostgreSQL has
    already closed would otherwise surface as a random failure on whichever
    request happened to draw it.
    """
    global _engine
    if _engine is None:
        url = (settings or default_settings).require_database_url()
        _engine = create_engine(url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory(settings: Optional[Settings] = None
                        ) -> sessionmaker[Session]:
    """The process-wide session factory.

    `expire_on_commit=False`: a caller that commits and then reads an attribute
    off the object it just wrote should not trigger a second round trip - or
    fail outright, once the session is closed.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(settings),
                                        expire_on_commit=False, future=True)
    return _session_factory


def reset_engine() -> None:
    """Dispose of the engine and forget it. For tests and for reconfiguration."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope(settings: Optional[Settings] = None) -> Iterator[Session]:
    """A session wrapped in one transaction: commit on success, roll back on error.

    The exception is always re-raised. A caller that wants to continue after a
    database failure must say so at the call site, where the decision is
    visible.
    """
    session = get_session_factory(settings)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection(settings: Optional[Settings] = None) -> bool:
    """`SELECT 1`. True when the database answers; raises when it does not.

    Deliberately not a boolean-swallowing helper: a caller asking whether the
    database is reachable wants the driver's error when it is not.
    """
    with get_engine(settings).connect() as conn:
        return conn.execute(text("SELECT 1")).scalar_one() == 1
