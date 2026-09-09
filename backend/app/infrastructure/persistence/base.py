"""The declarative base and the conventions every table follows.

Two things live here and nothing else: the `Base` that Alembic autogenerates
against, and a naming convention for constraints.

The naming convention matters more than it looks. Without it PostgreSQL invents
constraint names, Alembic emits migrations that reference those invented names,
and a later `ALTER` cannot find the constraint it wants to drop on a database
built by a different PostgreSQL version. Fixing the names here makes every
migration reproducible.
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Deterministic constraint names, so migrations can always name what they alter.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every MDR table."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _now_column(**kwargs) -> Mapped[_dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(),
                         nullable=False, **kwargs)


class TimestampMixin:
    """`created_at` / `updated_at`, both set by the database.

    Defaulted server-side rather than in Python so a row written by a migration,
    by `psql` or by a future service all carry the same clock. `updated_at` is
    refreshed by SQLAlchemy on flush; there is no database trigger, because a
    trigger would be invisible to anyone reading the model.
    """

    created_at: Mapped[_dt.datetime] = _now_column()
    updated_at: Mapped[_dt.datetime] = _now_column(onupdate=func.now())
