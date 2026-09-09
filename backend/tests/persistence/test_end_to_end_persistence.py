"""The real workbook, through the real engine, into PostgreSQL.

Everything else in this suite builds rows by hand, which proves the schema
accepts what it is told to accept. This file proves the schema accepts what the
*engine actually produces* - all ~22k rows of it, with the real DOC TYPE, SOW
and IDB values, under the real rules workbook's fingerprint.

It is the slowest test in the repository and it earns that: a column too short
for a real document title, a value the CHECK constraint refuses, or a chunked
insert that loses rows would all pass every hand-built test above and fail
here.

Nothing is written to the workbook, and no API endpoint is involved. This is
`services.submission_service` - the persistence half of Delivery Phase 2 -
being handed an `AutomationRun` the existing engine produced.
"""

from __future__ import annotations

import uuid

import pytest

from app.domain.enums.lifecycle import SubmissionStatus
from app.infrastructure.persistence.repositories import (
    DocumentRowRepository, ProcessingSummaryRepository,
)
from app.services import submission_service
from app.services.automation_service import run_automation
from tests.support.workbook import PHASE1_WORKBOOK


@pytest.fixture(scope="module")
def automation_run():
    """One real automation run over the real workbook. Slow; done once."""
    return run_automation(PHASE1_WORKBOOK)


class TestARealRunPersists:

    @pytest.fixture
    def stored(self, session, automation_run):
        """Persist the run, and hand back what was written."""
        plant = submission_service.register_plant(
            session, code=f"QE-TN-{uuid.uuid4().hex[:8]}", name="QatarEnergy TN")
        rule_set = submission_service.register_rule_set(session)
        submission = submission_service.record_upload(
            session, plant=plant, workbook=PHASE1_WORKBOOK)
        summary = submission_service.record_automation_run(
            session, submission=submission, run=automation_run,
            rule_set=rule_set)
        session.flush()
        return submission, summary, rule_set

    def test_every_engine_row_is_stored(self, session, stored, automation_run):
        submission, _, _ = stored
        assert DocumentRowRepository(session).count_for(submission.id) == len(
            automation_run.result.documents)

    def test_the_submission_reaches_automated(self, session, stored):
        submission, _, _ = stored
        assert submission.status == SubmissionStatus.AUTOMATED
        assert submission.extracted_at is not None
        assert submission.automated_at is not None

    def test_the_workbook_metadata_is_the_real_file(self, session, stored):
        submission, _, _ = stored
        assert submission.source_filename == PHASE1_WORKBOOK.name
        assert submission.source_byte_size == PHASE1_WORKBOOK.stat().st_size
        assert len(submission.source_sha256) == 64

    def test_extraction_recorded_what_the_workbook_contained(self, session,
                                                             stored,
                                                             automation_run):
        submission, _, _ = stored
        discovery = automation_run.result.discovery
        assert submission.source_sheet_name == discovery["qe_sheet"]
        assert submission.source_header_row == discovery["qe_header_row"]
        assert submission.source_row_count == discovery["qe_data_rows"]

    def test_the_four_automation_columns_survive(self, session, stored,
                                                 automation_run):
        """Compare a sample of stored rows against what the engine said."""
        submission, _, _ = stored
        by_row = {r.source_row: r for r in automation_run.rows}
        stored_rows = DocumentRowRepository(session).for_submission(
            submission.id, limit=500)

        assert stored_rows, "nothing was stored"
        for row in stored_rows:
            expected = by_row[row.source_row]
            assert row.doc_with_rev == expected.doc_with_rev
            assert row.doc_type == expected.doc_type
            assert row.sow == expected.sow
            assert row.idb_completed_status == expected.idb_status

    def test_doc_with_rev_is_actually_populated(self, session, stored):
        """A stored column of empty strings would satisfy the test above."""
        submission, summary, _ = stored
        assert summary.doc_with_rev_populated > 0
        rows = DocumentRowRepository(session).for_submission(submission.id,
                                                             limit=100)
        assert any(r.doc_with_rev for r in rows)

    def test_check_status_is_blank_across_the_whole_run(self, session, stored):
        submission, summary, _ = stored
        rows = DocumentRowRepository(session).for_submission(submission.id,
                                                             limit=2000)
        assert {r.check_status for r in rows} == {""}
        assert summary.check_status_populated == 0

    def test_the_summary_matches_the_run(self, session, stored, automation_run):
        _, summary, _ = stored
        engine_summary = automation_run.summary()
        assert summary.row_count == engine_summary["rows"]
        assert summary.doc_type_populated == engine_summary["doc_type_populated"]
        assert summary.sow_populated == engine_summary["sow_populated"]
        assert summary.idb_unmapped == engine_summary["idb_unmapped"]
        assert (summary.idb_manual_check_required
                == engine_summary["idb_manual_check_required"])

    def test_the_breakdowns_and_discovery_are_queryable(self, session, stored,
                                                        automation_run):
        _, summary, _ = stored
        assert summary.counts["doc_type_counts"] == automation_run.summary()[
            "doc_type_counts"]
        assert summary.counts["discovery"]["qe_sheet"] == (
            automation_run.result.discovery["qe_sheet"])

    def test_the_result_names_the_rules_that_produced_it(self, session, stored):
        """The real rules workbook, fingerprinted and attached to the result."""
        submission, _, rule_set = stored
        found = ProcessingSummaryRepository(session).for_submission(
            submission.id)
        assert found.rule_set_id == rule_set.id
        assert found.rule_set.source_filename.endswith(".xlsx")
        assert found.rule_set.required_rule_count > 0
        assert found.engine_version

    def test_doc_type_counts_agree_with_the_summary(self, session, stored):
        """The same numbers, once from the rows and once from the summary."""
        submission, summary, _ = stored
        from_rows = DocumentRowRepository(session).doc_type_counts(
            submission.id)
        assert from_rows == summary.counts["doc_type_counts"]


class TestTheSourceWorkbookIsUntouched:

    def test_persisting_a_run_does_not_modify_the_workbook(self, session,
                                                           automation_run):
        """Phase 2D's guarantee still holds with a database in the picture."""
        import hashlib

        before = hashlib.sha256(PHASE1_WORKBOOK.read_bytes()).hexdigest()
        plant = submission_service.register_plant(
            session, code=f"UNTOUCHED-{uuid.uuid4().hex[:8]}", name="Plant")
        rule_set = submission_service.register_rule_set(session)
        submission = submission_service.record_upload(
            session, plant=plant, workbook=PHASE1_WORKBOOK)
        submission_service.record_automation_run(
            session, submission=submission, run=automation_run,
            rule_set=rule_set)
        session.flush()

        assert hashlib.sha256(
            PHASE1_WORKBOOK.read_bytes()).hexdigest() == before
