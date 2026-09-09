"""The migrations build the schema the models describe, and can be reversed.

Three things are checked, and the middle one is the reason this file exists:

1. `alembic upgrade head` produces every table Delivery Phase 2 defines.
2. The migrated schema and `Base.metadata` agree - autogenerate finds nothing
   left to do. Without this, a model can gain a column that no migration
   creates, every test that uses `create_all` still passes, and the failure
   appears in production.
3. `downgrade base` removes what it created.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from app.infrastructure.persistence.base import Base

EXPECTED_TABLES = {
    "plants",
    "rule_sets",
    "mdr_submissions",
    "mdr_document_rows",
    "mdr_processing_summaries",
}


class TestMigrationApplies:

    def test_every_table_exists_after_upgrade(self, migrated_engine):
        tables = set(inspect(migrated_engine).get_table_names())
        assert EXPECTED_TABLES <= tables

    def test_alembic_version_is_recorded(self, migrated_engine):
        """The stamp exists, so a later `upgrade` knows where it is starting."""
        assert "alembic_version" in inspect(migrated_engine).get_table_names()

    def test_the_migration_matches_the_models(self, migrated_engine):
        """Autogenerate against the migrated database must find no difference.

        A model can otherwise gain a column that no migration creates: the ORM
        would keep working against a database it built itself, and the gap
        would only appear on a deployment that runs the migrations.
        """
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext

        with migrated_engine.connect() as conn:
            context = MigrationContext.configure(
                conn, opts={"compare_type": True,
                            "compare_server_default": True})
            diff = compare_metadata(context, Base.metadata)

        assert diff == [], f"models and migration disagree: {diff}"


class TestMigrationReverses:

    def test_downgrade_then_upgrade_restores_the_schema(self, alembic_config,
                                                        migrated_engine):
        """Step all the way down and back up again.

        Runs last-ish by design; it leaves the schema as it found it, so the
        session-scoped `migrated_engine` other tests share is unaffected.
        """
        from alembic import command

        command.downgrade(alembic_config, "base")
        remaining = set(inspect(migrated_engine).get_table_names())
        assert not (EXPECTED_TABLES & remaining), (
            f"downgrade left tables behind: {EXPECTED_TABLES & remaining}")

        command.upgrade(alembic_config, "head")
        assert EXPECTED_TABLES <= set(inspect(migrated_engine).get_table_names())


class TestSchemaIsPostgreSQL:

    def test_the_database_under_test_is_postgresql(self, migrated_engine):
        """Guards the suite itself.

        If this ever passes against SQLite, the JSONB, `TIMESTAMPTZ` and
        `ondelete` assertions elsewhere in this suite are no longer testing
        what they claim to.
        """
        assert migrated_engine.dialect.name == "postgresql"

    @pytest.mark.parametrize("table,column,expected", [
        ("mdr_processing_summaries", "counts", "JSONB"),
        ("mdr_submissions", "uploaded_at", "TIMESTAMP"),
        ("mdr_document_rows", "id", "BIGINT"),
    ])
    def test_column_types_survived_the_migration(self, migrated_engine, table,
                                                 column, expected):
        columns = {c["name"]: c for c in inspect(migrated_engine)
                   .get_columns(table)}
        assert expected in str(columns[column]["type"]).upper()

    def test_timestamps_are_timezone_aware(self, migrated_engine):
        """A naive `uploaded_at` would make two time zones incomparable."""
        columns = {c["name"]: c for c in inspect(migrated_engine)
                   .get_columns("mdr_submissions")}
        assert columns["uploaded_at"]["type"].timezone is True
