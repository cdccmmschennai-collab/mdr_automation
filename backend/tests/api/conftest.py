"""Fixtures for the Delivery Phase 3 workflow tests.

The workflow services own their transactions and reach PostgreSQL through the
process-wide engine in `infrastructure.persistence.database`, so these tests
cannot borrow the persistence suite's rolled-back `session`. Instead the whole
API is pointed at a throwaway database for the session:

* the database itself is the persistence suite's `database_url` /
  `migrated_engine` pair, imported here so it is built the same way - by
  running the Alembic migrations, never `create_all`;
* `MDR_DATABASE_URL` and `MDR_UPLOADS_DIR` are set to that database and to a
  temporary directory, the process-wide engine is reset, and a `Settings`
  built from that environment is what the routes receive through
  `app.dependency_overrides[get_settings]`.

Writes are real commits into the throwaway database, which is dropped when the
session ends. Tests therefore never assume an empty database: each creates its
own plant and its own submissions.

With no `MDR_TEST_DATABASE_URL` the suite skips, exactly as the persistence
suite does.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.persistence.conftest import (   # noqa: F401 - re-registered here
    alembic_config, database_url, migrated_engine,
)
from tests.support.automation import build_source_workbook


@pytest.fixture(scope="session")
def workflow_settings(database_url, migrated_engine, tmp_path_factory):
    """Settings pointing the workflow at the throwaway database and a
    temporary upload directory. Session-scoped: the engine is process-wide."""
    from app.core.config import load_settings
    from app.infrastructure.persistence.database import reset_engine

    uploads = tmp_path_factory.mktemp("uploads")
    saved = {k: os.environ.get(k) for k in ("MDR_DATABASE_URL",
                                            "MDR_UPLOADS_DIR")}
    os.environ["MDR_DATABASE_URL"] = database_url
    os.environ["MDR_UPLOADS_DIR"] = str(uploads)
    reset_engine()
    try:
        yield load_settings()
    finally:
        reset_engine()
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def client(workflow_settings) -> TestClient:
    """The API, with every route's `Settings` replaced by the test's."""
    from app.api.deps import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: workflow_settings
    try:
        # raise_server_exceptions=False: a 500 must arrive as a 500 response,
        # which is what the tests of failure handling assert on.
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def plant(workflow_settings):
    """A plant of this test's own, committed to the throwaway database."""
    from app.infrastructure.persistence.database import session_scope
    from app.infrastructure.persistence.repositories import PlantRepository

    with session_scope(workflow_settings) as session:
        return PlantRepository(session).add(
            code=f"PLANT-{uuid.uuid4().hex[:8]}", name="QatarEnergy TN")


@pytest.fixture(scope="session")
def small_workbook(tmp_path_factory) -> Path:
    """The nine-row MDR-shaped workbook the export tests already use: four
    document rows at Excel rows 6, 7, 8 and 10, one spacer row without a
    DOCUMENT NO., and the three companion sheets the reader looks for."""
    return build_source_workbook(
        tmp_path_factory.mktemp("workbooks") / "small-mdr.xlsx")


def upload(client: TestClient, plant, workbook: Path, *,
           filename: str | None = None):
    """POST the workbook for the plant; return the response."""
    return client.post(
        "/api/v1/mdr/upload",
        data={"plant_id": str(plant.id)},
        files={"mdr_file": (filename or workbook.name, workbook.read_bytes(),
                            "application/vnd.openxmlformats-officedocument"
                            ".spreadsheetml.sheet")})


def stored_rows(settings, mdr_id):
    """Every `mdr_document_rows` row of one submission, in source order."""
    from app.infrastructure.persistence.database import session_scope
    from app.infrastructure.persistence.repositories import (
        DocumentRowRepository,
    )

    with session_scope(settings) as session:
        return DocumentRowRepository(session).for_submission(uuid.UUID(str(mdr_id)))


def stored_submission(settings, mdr_id):
    from app.infrastructure.persistence.database import session_scope
    from app.infrastructure.persistence.repositories import (
        SubmissionRepository,
    )

    with session_scope(settings) as session:
        return SubmissionRepository(session).get(uuid.UUID(str(mdr_id)))
