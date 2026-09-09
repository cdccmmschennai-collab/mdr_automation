"""PostgreSQL persistence (Delivery Phase 2).

The only part of the backend that knows SQL exists. Everything above it -
services, the MDR engine, the domain - is unchanged by its presence, and the
engine and domain packages are forbidden from importing SQLAlchemy by an
architecture test.

    services
        v
    repositories        repositories/
        v
    session             database.py
        v
    PostgreSQL          models.py, ../../../alembic/versions/

Nothing here is imported by `app.main`, the CLI or the Excel writer: a backend
with no database configured still runs every capability Delivery Phase 1
shipped.
"""
