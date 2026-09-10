"""The real MDR workbook through the real HTTP workflow into PostgreSQL.

`test_workflow_api.py` proves the workflow on nine rows. This proves it on the
~22k-row workbook Delivery Phase 1 was verified against: uploaded over HTTP,
extracted, automated, and the database compared with what `run_automation`
says about the same file. It is the slowest test module in the repository
and runs the engine three times (extract, automate, oracle); it skips when the
workbook or the rules workbook is not present, and it never writes to either.
"""

from __future__ import annotations

import hashlib

import pytest

from app.domain.enums.lifecycle import SubmissionStatus
from app.services.automation_service import run_automation
from app.services.rule_set_service import file_digest
from tests.support.workbook import (
    PHASE1_WORKBOOK, RULES_WORKBOOK, requires_rules_workbook,
    requires_workbook,
)

from .conftest import stored_rows, stored_submission, upload

pytestmark = [requires_workbook, requires_rules_workbook]


@pytest.fixture(scope="module")
def oracle():
    """One run of the existing engine over the real workbook."""
    return run_automation(PHASE1_WORKBOOK)


@pytest.fixture(scope="module")
def processed(workflow_settings):
    """upload -> extract -> automate, once for the module; hands back the
    three response bodies, the plant and the source digest taken before."""
    import uuid

    from fastapi.testclient import TestClient

    from app.api.deps import get_settings
    from app.infrastructure.persistence.database import session_scope
    from app.infrastructure.persistence.repositories import PlantRepository
    from app.main import app

    with session_scope(workflow_settings) as session:
        plant = PlantRepository(session).add(
            code=f"REAL-{uuid.uuid4().hex[:8]}", name="QatarEnergy TN")

    before = file_digest(PHASE1_WORKBOOK)
    mtime = PHASE1_WORKBOOK.stat().st_mtime_ns
    app.dependency_overrides[get_settings] = lambda: workflow_settings
    try:
        client = TestClient(app, raise_server_exceptions=False)
        up = upload(client, plant, PHASE1_WORKBOOK)
        assert up.status_code == 201, up.text
        mdr_id = up.json()["mdr_id"]
        ex = client.post(f"/api/v1/mdr/{mdr_id}/extract")
        assert ex.status_code == 200, ex.text
        au = client.post(f"/api/v1/mdr/{mdr_id}/automate")
        assert au.status_code == 200, au.text
        su = client.get(f"/api/v1/mdr/{mdr_id}/summary")
        assert su.status_code == 200, su.text
    finally:
        app.dependency_overrides.pop(get_settings, None)
    return {"upload": up.json(), "extract": ex.json(), "automate": au.json(),
            "summary": su.json(), "plant": plant, "digest_before": before,
            "mtime_before": mtime}


class TestTheSourceIsUntouched:

    def test_the_source_digest_is_unchanged(self, processed):
        assert file_digest(PHASE1_WORKBOOK) == processed["digest_before"]

    def test_the_source_file_was_not_rewritten(self, processed):
        assert PHASE1_WORKBOOK.stat().st_mtime_ns == processed["mtime_before"]

    def test_the_upload_digest_is_the_source_digest(self, processed):
        assert processed["upload"]["source_sha256"] == processed["digest_before"]
        assert processed["upload"]["source_byte_size"] == PHASE1_WORKBOOK.stat().st_size

    def test_the_stored_copy_is_byte_identical(self, processed,
                                               workflow_settings):
        stored = stored_submission(workflow_settings, processed["upload"]["mdr_id"])
        copy = workflow_settings.uploads_dir / stored.stored_path
        assert copy != PHASE1_WORKBOOK
        assert hashlib.sha256(copy.read_bytes()).hexdigest() == processed[
            "digest_before"]


class TestExtraction:

    def test_the_discovery_matches_the_engine(self, processed, oracle):
        discovery = oracle.result.discovery
        assert processed["extract"]["source_sheet_name"] == discovery["qe_sheet"]
        assert processed["extract"]["source_header_row"] == discovery["qe_header_row"]
        assert processed["extract"]["source_row_count"] == discovery["qe_data_rows"]

    def test_every_document_row_is_stored_once_by_source_row(
            self, processed, oracle, workflow_settings):
        rows = stored_rows(workflow_settings, processed["upload"]["mdr_id"])
        assert len(rows) == len(oracle.result.documents)
        assert sorted(r.source_row for r in rows) == sorted(
            d.source_row for d in oracle.result.documents)


class TestAutomation:

    def test_the_row_count_is_the_engines(self, processed, oracle):
        assert processed["automate"]["row_count"] == len(oracle.rows)
        assert processed["automate"]["status"] == SubmissionStatus.AUTOMATED

    def test_every_stored_verdict_matches_the_engine(self, processed, oracle,
                                                     workflow_settings):
        """All ~22k rows, all four columns and the three provenance fields."""
        stored = {r.source_row: r for r in
                  stored_rows(workflow_settings, processed["upload"]["mdr_id"])}
        assert len(stored) == len(oracle.rows)
        mismatches = [
            row.source_row for row in oracle.rows
            if (stored[row.source_row].doc_with_rev, stored[row.source_row].doc_type,
                stored[row.source_row].sow,
                stored[row.source_row].idb_completed_status,
                stored[row.source_row].doc_type_rule,
                stored[row.source_row].sow_source,
                stored[row.source_row].idb_source)
            != (row.doc_with_rev, row.doc_type, row.sow, row.idb_status,
                row.doc_type_rule, row.sow_source, row.idb_source)
        ]
        assert mismatches == []

    def test_check_status_is_blank_on_every_row(self, processed,
                                                workflow_settings):
        rows = stored_rows(workflow_settings, processed["upload"]["mdr_id"])
        assert {r.check_status for r in rows} == {""}

    def test_the_rule_set_is_the_real_rules_workbook(self, processed):
        rule_set = processed["automate"]["rule_set"]
        assert rule_set["content_sha256"] == file_digest(RULES_WORKBOOK)
        assert rule_set["source_filename"] == RULES_WORKBOOK.name


class TestSummary:

    def test_the_summary_is_the_engines_summary(self, processed, oracle):
        body = processed["summary"]
        expected = oracle.summary()
        for key in ("doc_with_rev_populated", "doc_type_populated",
                    "sow_populated", "sow_unresolved", "idb_populated",
                    "idb_unmapped", "idb_manual_check_required"):
            assert body[key] == expected[key], key
        assert body["row_count"] == expected["rows"]
        assert body["check_status_populated"] == 0
        assert body["counts"]["doc_type_counts"] == expected["doc_type_counts"]
        assert body["counts"]["sow_counts"] == expected["sow_counts"]
        assert body["counts"]["idb_counts"] == expected["idb_counts"]

    def test_the_summary_names_plant_status_and_rules(self, processed):
        body = processed["summary"]
        assert body["plant_code"] == processed["plant"].code
        assert body["status"] == SubmissionStatus.AUTOMATED
        assert body["rule_set"] == processed["automate"]["rule_set"]
        assert body["failure_reason"] == ""
