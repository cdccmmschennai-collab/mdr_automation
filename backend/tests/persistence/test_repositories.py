"""What Delivery Phase 2 must actually be able to store, stored and read back.

Organised by the question each group answers rather than by class-under-test,
because the requirement is about the product ("can MDR #6 still be explained?")
rather than about a method.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from app.domain.enums.lifecycle import SubmissionStatus
from app.domain.models.automation import AutomationRow, CheckStatusNotEvaluated
from app.domain.models.document import DocumentRecord
from app.infrastructure.persistence.models import MdrSubmission
from app.infrastructure.persistence.repositories import (
    DocumentRowRepository, PlantRepository, ProcessingSummaryRepository,
    RuleSetRepository, SubmissionRepository,
)

from .conftest import make_digest


def a_document(source_row: int, **kwargs) -> DocumentRecord:
    defaults = dict(
        document_identity=f"DOC-{source_row}",
        qatarenergy_document_no=f"QE-DOC-{source_row}",
        revision="A1", revision_raw="A1", revision_status="LATEST",
        is_latest_revision=True, document_title="P&ID Overall",
        discipline="PROCESS",
    )
    defaults.update(kwargs)
    return DocumentRecord(source_row=source_row, **defaults)


def an_automation_row(source_row: int, **kwargs) -> AutomationRow:
    defaults = dict(
        doc_with_rev=f"QE-DOC-{source_row}-A1", doc_type="P&ID",
        sow="YES", idb_status="", doc_type_rule="REQUIRED#51 TITLE 'P&ID'",
        sow_source="DOCUMENT TYPE#12", idb_source="NO_COMPLETION_SOURCE",
    )
    defaults.update(kwargs)
    return AutomationRow(source_row=source_row, **defaults)


class TestConnection:

    def test_the_database_answers(self, session):
        assert session.execute(text("SELECT 1")).scalar_one() == 1


class TestPlants:

    def test_a_plant_persists_and_is_found_by_code(self, session):
        repo = PlantRepository(session)
        created = repo.add(code="QATARENERGY-TN", name="QatarEnergy TN")
        session.flush()
        assert repo.by_code("QATARENERGY-TN").id == created.id

    def test_two_plants_cannot_share_a_code(self, session):
        repo = PlantRepository(session)
        repo.add(code="DUPLICATE", name="First")
        # `add` flushes, so the constraint is enforced on this call - not on
        # some later one. That is the point of flushing there.
        with pytest.raises(IntegrityError):
            repo.add(code="DUPLICATE", name="Second")

    def test_get_or_create_does_not_duplicate(self, session):
        repo = PlantRepository(session)
        first = repo.get_or_create("ONCE", "Plant")
        assert repo.get_or_create("ONCE", "Plant").id == first.id


class TestSubmissionAndItsWorkbookMetadata:

    def test_a_submission_persists_with_its_plant(self, session, plant):
        repo = SubmissionRepository(session)
        created = repo.add(plant_id=plant.id, source_filename="log-9.xlsx",
                           source_sha256=make_digest("9"),
                           source_byte_size=12_345)
        session.flush()
        found = repo.get(created.id)
        assert found.plant_id == plant.id
        assert found.plant.code == plant.code

    def test_source_workbook_metadata_round_trips(self, session, plant):
        digest = make_digest("workbook-bytes")
        created = SubmissionRepository(session).add(
            plant_id=plant.id, source_filename="20260720-184 MDR.xlsx",
            source_sha256=digest, source_byte_size=12_345_678,
            stored_path="/srv/mdr/uploads/abc.xlsx")
        session.flush()
        session.expire(created)

        assert created.source_filename == "20260720-184 MDR.xlsx"
        assert created.source_sha256 == digest
        assert created.source_byte_size == 12_345_678
        assert created.stored_path == "/srv/mdr/uploads/abc.xlsx"

    def test_a_new_submission_is_uploaded_and_nothing_else(self, session,
                                                           submission):
        assert submission.status == SubmissionStatus.UPLOADED
        assert submission.extracted_at is None
        assert submission.automated_at is None
        assert submission.failure_reason == ""

    def test_an_unknown_plant_is_rejected(self, session):
        """The foreign key is enforced, not decorative."""
        with pytest.raises(IntegrityError):
            SubmissionRepository(session).add(
                plant_id=uuid.uuid4(), source_filename="orphan.xlsx",
                source_sha256=make_digest("orphan"), source_byte_size=1)

    def test_a_plant_with_submissions_cannot_be_deleted(self, session, plant,
                                                        submission):
        """ON DELETE RESTRICT: history does not vanish with its plant."""
        session.flush()
        with pytest.raises(IntegrityError):
            session.execute(text("DELETE FROM plants WHERE id = :id"),
                            {"id": plant.id})

    def test_a_short_digest_is_rejected(self, session, plant):
        """The CHECK constraint refuses anything that is not a SHA-256."""
        with pytest.raises((IntegrityError, DataError)):
            SubmissionRepository(session).add(
                plant_id=plant.id, source_filename="x.xlsx",
                source_sha256="tooshort", source_byte_size=1)

    def test_an_empty_workbook_is_rejected(self, session, plant):
        with pytest.raises(IntegrityError):
            SubmissionRepository(session).add(
                plant_id=plant.id, source_filename="empty.xlsx",
                source_sha256=make_digest("empty"), source_byte_size=0)


class TestLifecycle:

    def test_extraction_records_what_the_workbook_contained(self, session,
                                                            submission):
        SubmissionRepository(session).mark_extracted(
            submission, sheet_name="QatarEnergy-TN", header_row=5,
            row_count=21_718)
        assert submission.status == SubmissionStatus.EXTRACTED
        assert submission.source_sheet_name == "QatarEnergy-TN"
        assert submission.source_header_row == 5
        assert submission.source_row_count == 21_718
        assert submission.extracted_at is not None

    def test_automation_stamps_its_own_time(self, session, submission):
        repo = SubmissionRepository(session)
        repo.mark_extracted(submission, sheet_name="QatarEnergy-TN")
        repo.mark_automated(submission)
        assert submission.status == SubmissionStatus.AUTOMATED
        assert submission.automated_at >= submission.extracted_at

    def test_a_failure_must_say_why(self, session, submission):
        with pytest.raises(ValueError):
            SubmissionRepository(session).mark_failed(submission, "   ")

    def test_a_failure_is_recorded_with_its_reason(self, session, submission):
        SubmissionRepository(session).mark_failed(
            submission, "QatarEnergy-TN sheet not found")
        assert submission.status == SubmissionStatus.FAILED
        assert "not found" in submission.failure_reason

    def test_an_unknown_status_is_rejected_by_the_database(self, session,
                                                           submission):
        """The CHECK constraint is the backstop for the domain enum."""
        session.flush()
        with pytest.raises(IntegrityError):
            session.execute(text(
                "UPDATE mdr_submissions SET status = 'NONSENSE' "
                "WHERE id = :id"), {"id": submission.id})


class TestHistoricalSubmissionsStayIndependent:
    """The requirement that shaped the schema: MDR #6, #7 and #8 side by side."""

    def test_submission_numbers_increment_per_plant(self, session, plant):
        repo = SubmissionRepository(session)
        numbers = [
            repo.add(plant_id=plant.id, source_filename=f"log-{n}.xlsx",
                     source_sha256=make_digest(f"log-{n}"),
                     source_byte_size=1000 + n).submission_no
            for n in range(3)
        ]
        assert numbers == [1, 2, 3]

    def test_each_plant_numbers_its_own_submissions(self, session):
        plants_repo = PlantRepository(session)
        subs = SubmissionRepository(session)
        first = plants_repo.add(code=f"A-{uuid.uuid4().hex[:6]}", name="A")
        second = plants_repo.add(code=f"B-{uuid.uuid4().hex[:6]}", name="B")

        subs.add(plant_id=first.id, source_filename="a.xlsx",
                 source_sha256=make_digest("a"), source_byte_size=1)
        on_second = subs.add(plant_id=second.id, source_filename="b.xlsx",
                             source_sha256=make_digest("b"), source_byte_size=1)
        assert on_second.submission_no == 1, (
            "a second plant must start at #1, not continue the first plant's "
            "numbering")

    def test_two_plants_may_both_have_an_mdr_6(self, session):
        plants_repo = PlantRepository(session)
        subs = SubmissionRepository(session)
        for code in (f"P1-{uuid.uuid4().hex[:6]}", f"P2-{uuid.uuid4().hex[:6]}"):
            p = plants_repo.add(code=code, name=code)
            subs.add(plant_id=p.id, submission_no=6, source_filename="6.xlsx",
                     source_sha256=make_digest(code), source_byte_size=1)
        session.flush()      # no unique violation: the key is (plant, number)

    def test_one_plant_cannot_have_two_mdr_6(self, session, plant):
        repo = SubmissionRepository(session)
        repo.add(plant_id=plant.id, submission_no=6, source_filename="6.xlsx",
                 source_sha256=make_digest("first-six"), source_byte_size=1)
        with pytest.raises(IntegrityError):
            repo.add(plant_id=plant.id, submission_no=6,
                     source_filename="6-again.xlsx",
                     source_sha256=make_digest("second-six"),
                     source_byte_size=1)

    def test_an_older_submission_is_untouched_by_a_newer_one(self, session,
                                                             plant):
        repo = SubmissionRepository(session)
        sixth = repo.add(plant_id=plant.id, submission_no=6,
                         source_filename="six.xlsx",
                         source_sha256=make_digest("six"), source_byte_size=6)
        repo.mark_extracted(sixth, sheet_name="QatarEnergy-TN", row_count=100)
        repo.mark_automated(sixth)
        session.flush()
        automated_at = sixth.automated_at

        repo.add(plant_id=plant.id, submission_no=7, source_filename="seven.xlsx",
                 source_sha256=make_digest("seven"), source_byte_size=7)
        session.flush()
        session.expire_all()

        again = repo.by_number(plant.id, 6)
        assert again.status == SubmissionStatus.AUTOMATED
        assert again.automated_at == automated_at
        assert again.source_row_count == 100

    def test_history_reads_back_in_order(self, session, plant):
        repo = SubmissionRepository(session)
        for n in (1, 2, 3):
            repo.add(plant_id=plant.id, submission_no=n,
                     source_filename=f"{n}.xlsx",
                     source_sha256=make_digest(f"h{n}"), source_byte_size=n)
        session.flush()
        assert [s.submission_no for s in repo.by_plant(plant.id)] == [1, 2, 3]

    def test_the_same_workbook_may_be_submitted_twice(self, session, plant):
        """Re-processing identical bytes under new rules is legitimate."""
        repo = SubmissionRepository(session)
        digest = make_digest("identical")
        for _ in range(2):
            repo.add(plant_id=plant.id, source_filename="same.xlsx",
                     source_sha256=digest, source_byte_size=99)
        session.flush()
        assert len(repo.by_digest(digest)) == 2


class TestProcessedRows:

    def test_rows_persist_with_all_four_automation_columns(self, session,
                                                           submission):
        documents = [a_document(10), a_document(11)]
        rows = [
            an_automation_row(10, doc_type="P&ID", sow="YES", idb_status=""),
            an_automation_row(11, doc_type="DATASHEET", sow="NO",
                              idb_status="NO NEED TO CHECK"),
        ]
        repo = DocumentRowRepository(session)
        assert repo.add_rows(submission.id, documents, rows) == 2

        stored = {r.source_row: r for r in repo.for_submission(submission.id)}
        assert stored[10].doc_with_rev == "QE-DOC-10-A1"
        assert stored[10].doc_type == "P&ID"
        assert stored[10].sow == "YES"
        assert stored[10].idb_completed_status == ""
        assert stored[11].idb_completed_status == "NO NEED TO CHECK"

    def test_identity_and_revision_context_persists(self, session, submission):
        DocumentRowRepository(session).add_rows(
            submission.id, [a_document(10)], [an_automation_row(10)])
        row = DocumentRowRepository(session).by_source_row(submission.id, 10)
        assert row.document_identity == "DOC-10"
        assert row.qatarenergy_document_no == "QE-DOC-10"
        assert row.revision == "A1"
        assert row.revision_status == "LATEST"
        assert row.is_latest_revision is True

    def test_provenance_persists(self, session, submission):
        """Which rule decided what, kept alongside the verdict."""
        DocumentRowRepository(session).add_rows(
            submission.id, [a_document(10)], [an_automation_row(10)])
        row = DocumentRowRepository(session).by_source_row(submission.id, 10)
        assert row.doc_type_rule == "REQUIRED#51 TITLE 'P&ID'"
        assert row.sow_source == "DOCUMENT TYPE#12"
        assert row.idb_source == "NO_COMPLETION_SOURCE"

    def test_rows_are_joined_on_source_row_not_position(self, session,
                                                        submission):
        """Automation rows supplied out of order still land on the right row."""
        documents = [a_document(10), a_document(20)]
        rows = [an_automation_row(20, doc_type="TWENTY"),
                an_automation_row(10, doc_type="TEN")]
        DocumentRowRepository(session).add_rows(submission.id, documents, rows)

        repo = DocumentRowRepository(session)
        assert repo.by_source_row(submission.id, 10).doc_type == "TEN"
        assert repo.by_source_row(submission.id, 20).doc_type == "TWENTY"

    def test_check_status_is_blank_and_the_database_enforces_it(self, session,
                                                                submission):
        DocumentRowRepository(session).add_rows(
            submission.id, [a_document(10)], [an_automation_row(10)])
        session.flush()
        assert DocumentRowRepository(session).by_source_row(
            submission.id, 10).check_status == ""

        with pytest.raises(IntegrityError):
            session.execute(text(
                "UPDATE mdr_document_rows SET check_status = 'RECEIVED' "
                "WHERE submission_id = :id"), {"id": submission.id})

    def test_the_domain_refuses_a_check_status_too(self, session):
        """The same rule, stated in the dataclass and in the schema."""
        with pytest.raises(CheckStatusNotEvaluated):
            AutomationRow(source_row=1, check_status="RECEIVED")

    def test_one_source_row_cannot_be_stored_twice(self, session, submission):
        repo = DocumentRowRepository(session)
        repo.add_rows(submission.id, [a_document(10)], [an_automation_row(10)])
        with pytest.raises(IntegrityError):
            repo.add_rows(submission.id, [a_document(10)],
                          [an_automation_row(10)])

    def test_rows_of_an_unknown_submission_are_rejected(self, session):
        with pytest.raises(IntegrityError):
            DocumentRowRepository(session).add_rows(
                uuid.uuid4(), [a_document(10)], [an_automation_row(10)])

    def test_two_submissions_rows_do_not_mix(self, session, plant):
        subs = SubmissionRepository(session)
        rows = DocumentRowRepository(session)
        sixth = subs.add(plant_id=plant.id, submission_no=6,
                         source_filename="6.xlsx",
                         source_sha256=make_digest("s6"), source_byte_size=6)
        seventh = subs.add(plant_id=plant.id, submission_no=7,
                           source_filename="7.xlsx",
                           source_sha256=make_digest("s7"), source_byte_size=7)
        rows.add_rows(sixth.id, [a_document(10)],
                      [an_automation_row(10, doc_type="SIX")])
        rows.add_rows(seventh.id, [a_document(10)],
                      [an_automation_row(10, doc_type="SEVEN")])
        session.flush()

        assert rows.by_source_row(sixth.id, 10).doc_type == "SIX"
        assert rows.by_source_row(seventh.id, 10).doc_type == "SEVEN"
        assert rows.count_for(sixth.id) == 1

    def test_deleting_a_submission_takes_its_rows(self, session, submission):
        """ON DELETE CASCADE: rows have no meaning without their submission."""
        repo = DocumentRowRepository(session)
        repo.add_rows(submission.id, [a_document(10)], [an_automation_row(10)])
        session.flush()
        session.execute(text("DELETE FROM mdr_submissions WHERE id = :id"),
                        {"id": submission.id})
        session.flush()
        assert repo.count_for(submission.id) == 0

    def test_a_bulk_insert_larger_than_one_chunk_works(self, session,
                                                       submission):
        """The real workbook is ~22k rows; the chunking must not drop any."""
        from app.infrastructure.persistence.repositories.document_rows import (
            INSERT_CHUNK,
        )
        count = INSERT_CHUNK + 7
        documents = [a_document(n) for n in range(1, count + 1)]
        rows = [an_automation_row(n) for n in range(1, count + 1)]
        repo = DocumentRowRepository(session)
        assert repo.add_rows(submission.id, documents, rows) == count
        assert repo.count_for(submission.id) == count

    def test_doc_type_counts_are_queryable(self, session, submission):
        documents = [a_document(n) for n in (1, 2, 3)]
        rows = [an_automation_row(1, doc_type="P&ID"),
                an_automation_row(2, doc_type="P&ID"),
                an_automation_row(3, doc_type="DATASHEET")]
        DocumentRowRepository(session).add_rows(submission.id, documents, rows)
        assert DocumentRowRepository(session).doc_type_counts(submission.id) == {
            "P&ID": 2, "DATASHEET": 1}


class TestProcessingSummary:

    SUMMARY = {
        "rows": 21_718, "doc_with_rev_populated": 21_718,
        "doc_type_populated": 20_004, "sow_populated": 19_500,
        "sow_unresolved": 2_218, "idb_populated": 8_000, "idb_unmapped": 1_714,
        "idb_manual_check_required": 11_500, "check_status_populated": 0,
        "doc_type_counts": {"P&ID": 900, "DATASHEET": 400},
        "sow_counts": {"YES": 19_000, "NO": 500},
        "idb_counts": {"NO NEED TO CHECK": 8_000},
    }

    def test_a_summary_persists_with_its_counts(self, session, submission,
                                                rule_set):
        stored = ProcessingSummaryRepository(session).add(
            submission_id=submission.id, rule_set_id=rule_set.id,
            summary=self.SUMMARY, engine_version="0.2.0",
            discovery={"qe_sheet": "QatarEnergy-TN", "qe_header_row": 5})
        session.flush()

        assert stored.row_count == 21_718
        assert stored.doc_type_populated == 20_004
        assert stored.idb_manual_check_required == 11_500
        assert stored.engine_version == "0.2.0"

    def test_the_per_value_breakdowns_survive_as_jsonb(self, session,
                                                       submission, rule_set):
        stored = ProcessingSummaryRepository(session).add(
            submission_id=submission.id, rule_set_id=rule_set.id,
            summary=self.SUMMARY,
            discovery={"qe_sheet": "QatarEnergy-TN"})
        session.flush()
        session.expire(stored)

        assert stored.counts["doc_type_counts"]["P&ID"] == 900
        assert stored.counts["sow_counts"]["YES"] == 19_000
        assert stored.counts["discovery"]["qe_sheet"] == "QatarEnergy-TN"

    def test_a_summary_is_found_from_its_submission(self, session, submission,
                                                    rule_set):
        ProcessingSummaryRepository(session).add(
            submission_id=submission.id, rule_set_id=rule_set.id,
            summary=self.SUMMARY)
        session.flush()
        assert ProcessingSummaryRepository(session).for_submission(
            submission.id).row_count == 21_718

    def test_a_submission_has_at_most_one_summary(self, session, submission,
                                                  rule_set):
        repo = ProcessingSummaryRepository(session)
        repo.add(submission_id=submission.id, rule_set_id=rule_set.id,
                 summary=self.SUMMARY)
        with pytest.raises(IntegrityError):
            repo.add(submission_id=submission.id, rule_set_id=rule_set.id,
                     summary=self.SUMMARY)

    def test_check_status_populated_cannot_be_nonzero(self, session,
                                                      submission, rule_set):
        """Nothing evaluates CHECK STATUS, so nothing may claim it counted any."""
        with pytest.raises(IntegrityError):
            ProcessingSummaryRepository(session).add(
                submission_id=submission.id, rule_set_id=rule_set.id,
                summary={**self.SUMMARY, "check_status_populated": 5})

    def test_a_summary_needs_a_real_rule_set(self, session, submission):
        with pytest.raises(IntegrityError):
            ProcessingSummaryRepository(session).add(
                submission_id=submission.id, rule_set_id=uuid.uuid4(),
                summary=self.SUMMARY)


class TestSurvivesRestart:

    def test_records_are_still_there_through_a_new_connection(
            self, migrated_engine, plant):
        """Written, committed, then read back on a connection opened fresh.

        `plant` is unused directly - the point is that this test uses neither
        the shared session nor its transaction. It writes on one connection,
        closes it, and opens another, which is what an application restart
        looks like from the database's side.
        """
        from sqlalchemy.orm import Session as PlainSession

        code = f"RESTART-{uuid.uuid4().hex[:8]}"
        with PlainSession(migrated_engine) as first:
            created = PlantRepository(first).add(code=code, name="Restart")
            subs = SubmissionRepository(first)
            submission = subs.add(plant_id=created.id, submission_no=6,
                                  source_filename="restart.xlsx",
                                  source_sha256=make_digest(code),
                                  source_byte_size=4_096)
            DocumentRowRepository(first).add_rows(
                submission.id, [a_document(10)],
                [an_automation_row(10, doc_type="P&ID")])
            first.commit()
            submission_id = submission.id

        try:
            with PlainSession(migrated_engine) as second:
                found = second.get(MdrSubmission, submission_id)
                assert found is not None
                assert found.submission_no == 6
                assert found.source_byte_size == 4_096
                row = DocumentRowRepository(second).by_source_row(
                    submission_id, 10)
                assert row.doc_type == "P&ID"
        finally:
            # Committed outside the fixture's transaction, so clean up by hand.
            with PlainSession(migrated_engine) as cleanup:
                cleanup.execute(
                    text("DELETE FROM mdr_submissions WHERE id = :id"),
                    {"id": submission_id})
                cleanup.execute(text("DELETE FROM plants WHERE code = :code"),
                                {"code": code})
                cleanup.commit()
