"""Phase 1 -> 2A -> 2B -> 2C -> 2D over the real workbook, end to end.

One run, one generated file, and every assertion made against that file after
it has been closed and reopened. This is the suite that says the deliverable
is a deliverable: the employee's own workbook comes back with every sheet,
every row and every column it arrived with, plus five columns whose values
came from the engines and one that is deliberately empty.

Slow - the source is 22,009 rows - so the run is module-scoped and the
workbook is written into pytest's temporary directory, never over the input
and never into the configured output directory.
"""

import pytest
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from app.domain.models.automation import (
    AUTOMATION_COLUMNS, CHECK_STATUS, DOC_IDB_COMPLETED_STATUS,
    DOC_IS_REQUIRED_SOW, DOC_TYPE, DOC_WITH_REV,
)
from app.domain.models.idb import (
    CANCELLED, COMPLETED, COMPLETED_REV_UPDATED, GENERAL_SPECIFICATION,
    NO_NEED_TO_CHECK, PENDING, REFERENCE, TAG_NOT_IN_FMTL, TO_BE_CHECK,
    UNMAPPED,
)
from app.engine.identity.normalisation import doc_with_rev
from app.infrastructure.excel.output_workbook import (
    AUTOMATED_SHEET, read_automation_columns,
)
from app.infrastructure.filesystem.artifact_writer import sha256_file
from app.services.automation_service import run_automation
from app.services.export_service import export_automated_workbook
from tests.support.workbook import PHASE1_WORKBOOK, requires_workbook

pytestmark = requires_workbook

#: Statuses that need the IDB folder, the FMTL or a human judgement - none of
#: which this project reads. Every one of them appears in the *historical*
#: column of `QatarEnergy-TN WORKING`, and none may appear in an output.
HISTORICAL_ONLY = (COMPLETED, COMPLETED_REV_UPDATED, PENDING, CANCELLED,
                   TAG_NOT_IN_FMTL, REFERENCE, GENERAL_SPECIFICATION)


@pytest.fixture(scope="module")
def source_digest():
    return sha256_file(PHASE1_WORKBOOK)


@pytest.fixture(scope="module")
def exported(source_digest, tmp_path_factory):
    """The whole chain, once. Returns (run, report)."""
    run = run_automation(PHASE1_WORKBOOK)
    outdir = tmp_path_factory.mktemp("phase2d-real")
    return run, export_automated_workbook(PHASE1_WORKBOOK, run.rows, outdir)


@pytest.fixture(scope="module")
def columns(exported):
    """The five columns, read back out of the generated file."""
    _, report = exported
    header_row, letters, rows = read_automation_columns(report.destination)
    return header_row, letters, rows


class TestTheChainRuns:
    def test_every_document_row_gets_a_five_column_answer(self, exported):
        run, _ = exported
        assert len(run.rows) == len(run.result.documents)
        assert len(run.rows) > 20000

    def test_the_row_numbers_are_the_workbooks_own(self, exported):
        run, _ = exported
        assert [r.source_row for r in run.rows] == \
            [d.source_row for d in run.result.documents]

    def test_phase_1_populates_doc_with_rev_for_every_row(self, exported):
        run, _ = exported
        assert all(r.doc_with_rev for r in run.rows)

    def test_doc_with_rev_is_the_number_and_the_revision(self, exported):
        run, _ = exported
        by_row = {d.source_row: d for d in run.result.documents}
        for row in run.rows[:500]:
            doc = by_row[row.source_row]
            assert row.doc_with_rev == doc_with_rev(
                doc.qatarenergy_document_no, doc.revision_raw)

    def test_phase_2a_populates_doc_type_where_a_keyword_rule_matches(self,
                                                                     exported):
        run, _ = exported
        classified = run.result.summary()["doc_type_classified_rows"]
        assert classified > 0
        assert sum(1 for r in run.rows if r.doc_type) == classified

    def test_phase_2b_only_states_a_sow_the_rules_workbook_states(self,
                                                                  exported):
        run, _ = exported
        for row in run.rows:
            assert row.sow == "" or row.sow == "NO" or row.sow.startswith("YES")

    def test_phase_2c_emits_only_the_statuses_it_can_justify(self, exported):
        """One rule, one honest unknown, and one deliberate blank - nothing
        else is derivable from the inputs this phase has."""
        run, _ = exported
        assert {r.idb_status for r in run.rows} <= {
            NO_NEED_TO_CHECK, "", UNMAPPED}

    def test_to_be_check_never_reaches_the_column(self, exported):
        """Phase 2C's own answer for an in-scope document. It states that a
        check is *due*, and the column records how the check *went*, so it is
        not an answer to write down."""
        run, _ = exported
        assert TO_BE_CHECK not in {r.idb_status for r in run.rows}

    def test_the_sow_verdict_decides_the_idb_status(self, exported):
        run, _ = exported
        for row in run.rows:
            if row.sow == "NO":
                assert row.idb_status == NO_NEED_TO_CHECK
            elif row.sow.startswith("YES"):
                # Required: blank, because a person must still check it.
                assert row.idb_status == ""
                assert row.idb_source == "NO_COMPLETION_SOURCE"
            else:
                assert row.idb_status == UNMAPPED

    def test_the_not_required_keyword_sheet_resolves_its_own_document_types(
            self, exported):
        """`CV`, `METHOD STATEMENT`, `PLAN` and friends are on the sheet of
        types the business does not require. That is the scope verdict; none
        of them may come back `UNMAPPED` for being absent from the 22-row
        `DOCUMENT TYPE` table."""
        run, _ = exported
        by_type = {}
        for row in run.rows:
            by_type.setdefault(row.doc_type, set()).add(
                (row.sow, row.idb_status))
        # `PLOT PLAN` is deliberately absent: the `PLAN` rule sits above it on
        # the sheet, so a plot plan classifies as `PLAN`. That is Phase 2A's
        # documented precedence, and Phase 2B has no business re-deciding it.
        for doc_type in ("CV", "METHOD STATEMENT", "PLAN", "LAYOUT"):
            assert doc_type in by_type, doc_type
            assert by_type[doc_type] == {("NO", NO_NEED_TO_CHECK)}, doc_type

    def test_every_not_required_classification_is_out_of_scope(self, exported):
        """Not just the examples: every row Phase 2A matched on the
        not-required sheet, whatever its DOC TYPE."""
        run, _ = exported
        from_not_required = [r for r in run.rows
                             if r.doc_type_rule.startswith("NOT_REQUIRED#")]
        assert len(from_not_required) > 6000
        assert {(r.sow, r.idb_status) for r in from_not_required} == \
            {("NO", NO_NEED_TO_CHECK)}


class TestNoHistoricalValueReachesTheOutput:
    def test_no_row_carries_a_status_that_needs_an_absent_input(self, exported):
        run, _ = exported
        produced = {r.idb_status for r in run.rows}
        assert not produced & set(HISTORICAL_ONLY)

    def test_the_generated_file_carries_none_either(self, columns):
        _, _, rows = columns
        produced = {r[DOC_IDB_COMPLETED_STATUS] for r in rows}
        assert not produced & set(HISTORICAL_ONLY)

    def test_no_completion_source_spoke(self, exported):
        run, _ = exported
        assert all(r.idb_source in {"SOW_NOT_REQUIRED", "NO_COMPLETION_SOURCE",
                                    "UNRESOLVED_SOW", "SOW_NOT_A_VERDICT"}
                   for r in run.rows)
        assert not any(r.idb_source == "COMPLETION_SOURCE" for r in run.rows)


class TestTheGeneratedFile:
    def test_it_exists_and_opens(self, exported):
        _, report = exported
        assert report.destination.is_file()
        assert report.destination.stat().st_size > 0

    def test_the_source_workbook_is_byte_for_byte_unchanged(self, source_digest,
                                                            exported):
        assert sha256_file(PHASE1_WORKBOOK) == source_digest

    def test_the_output_is_not_the_source(self, exported):
        _, report = exported
        assert report.destination.resolve() != PHASE1_WORKBOOK.resolve()

    def test_every_original_sheet_survives(self, exported):
        _, report = exported
        wb = load_workbook(PHASE1_WORKBOOK, read_only=True)
        try:
            before = list(wb.sheetnames)
        finally:
            wb.close()
        assert set(before) <= set(report.sheet_names)
        assert set(report.sheet_names) - set(before) == {AUTOMATED_SHEET}

    def test_the_automated_sheet_is_added_at_the_end(self, exported):
        """Every sheet the employee sent keeps the position it arrived in."""
        _, report = exported
        names = list(report.sheet_names)
        assert names[-1] == AUTOMATED_SHEET
        wb = load_workbook(PHASE1_WORKBOOK, read_only=True)
        try:
            assert names[:-1] == list(wb.sheetnames)
        finally:
            wb.close()

    def test_it_is_the_only_sheet_written(self, exported):
        _, report = exported
        assert AUTOMATED_SHEET not in report.untouched_sheets
        assert report.sheet_names.count(AUTOMATED_SHEET) == 1

    def test_the_row_count_is_preserved(self, exported):
        _, report = exported
        wb = load_workbook(report.destination, read_only=True)
        try:
            source_rows = wb[report.source_sheet].max_row
            automated_rows = wb[AUTOMATED_SHEET].max_row
        finally:
            wb.close()
        assert automated_rows == source_rows

    def test_the_original_columns_are_all_still_present(self, exported):
        _, report = exported
        wb = load_workbook(PHASE1_WORKBOOK, read_only=True)
        try:
            ws = wb[report.source_sheet]
            before = [c.value for c in
                      next(ws.iter_rows(min_row=report.header_row,
                                        max_row=report.header_row))]
        finally:
            wb.close()

        wb = load_workbook(report.destination, read_only=True)
        try:
            ws = wb[AUTOMATED_SHEET]
            after = [c.value for c in
                     next(ws.iter_rows(min_row=report.header_row,
                                       max_row=report.header_row))]
        finally:
            wb.close()
        # Interleaved, not truncated: the five are inserted among them.
        assert [c for c in after if c in before] == \
            [c for c in before if c is not None]

    def test_the_columns_go_where_the_working_sheet_puts_them(self, exported):
        """AK..AO, before `QATARENERGY SIGNED / NOT SIGNED` - the placement
        `QatarEnergy-TN WORKING` established, not an append after AM."""
        _, report = exported
        assert report.reused_columns == ()
        assert list(report.columns) == list(AUTOMATION_COLUMNS)
        assert [report.columns[c] for c in AUTOMATION_COLUMNS] == \
            ["AK", "AL", "AM", "AN", "AO"]
        assert report.inserted_before == "QATARENERGY SIGNED / NOT SIGNED"
        assert report.inserted_columns == 5

    def test_the_trailing_columns_moved_right_rather_than_being_overwritten(
            self, exported):
        _, report = exported
        wb = load_workbook(report.destination, read_only=True)
        try:
            ws = wb[AUTOMATED_SHEET]
            row = [c.value for c in
                   next(ws.iter_rows(min_row=report.header_row,
                                     max_row=report.header_row))]
        finally:
            wb.close()
        # AK..AM in the source; AP..AR after five columns are inserted at AK.
        assert row[36:41] == list(AUTOMATION_COLUMNS)
        assert row[41:44] == ["QATARENERGY SIGNED / NOT SIGNED",
                              "AFC DOCUMENT\nTN NO.", "DATE ISSUED"]


class TestTheFiveColumnsInTheFile:
    def test_all_five_captions_are_there(self, columns):
        _, letters, _ = columns
        assert set(letters) == set(AUTOMATION_COLUMNS)

    def test_they_are_on_the_sheets_own_header_row(self, columns, exported):
        header_row, _, _ = columns
        _, report = exported
        assert header_row == report.header_row

    def test_the_file_holds_a_row_for_every_document(self, columns, exported):
        run, _ = exported
        _, _, rows = columns
        assert len(rows) == len(run.rows)
        assert {r["source_row"] for r in rows} == \
            {r.source_row for r in run.rows}

    def test_the_values_match_the_engines_answers(self, columns, exported):
        run, _ = exported
        _, _, rows = columns
        expected = {r.source_row: r for r in run.rows}
        for row in rows:
            want = expected[row["source_row"]]
            assert row[DOC_WITH_REV] == want.doc_with_rev
            assert row[DOC_TYPE] == want.doc_type
            assert row[DOC_IS_REQUIRED_SOW] == want.sow
            assert row[DOC_IDB_COMPLETED_STATUS] == want.idb_status

    def test_every_value_is_upper_case(self, columns):
        _, _, rows = columns
        for row in rows:
            for caption in AUTOMATION_COLUMNS:
                assert row[caption] == row[caption].upper()

    def test_doc_with_rev_is_populated_on_every_row(self, columns):
        _, _, rows = columns
        assert all(r[DOC_WITH_REV] for r in rows)


class TestCheckStatusIsBlankInTheFile:
    def test_the_column_exists(self, columns):
        _, letters, _ = columns
        assert CHECK_STATUS in letters

    def test_no_row_carries_a_value(self, columns):
        _, _, rows = columns
        assert {r[CHECK_STATUS] for r in rows} == {""}

    def test_it_does_not_say_not_received(self, columns):
        """There is no received-document dump. Its absence is not evidence
        that a document was not received."""
        _, _, rows = columns
        assert not any(r[CHECK_STATUS] in {"NOT RECEIVED", "RECEIVED", "#N/A"}
                       for r in rows)

    def test_the_whole_column_is_empty_including_skipped_rows(self, exported):
        """Not just the document rows - every cell under the caption."""
        _, report = exported
        column = column_index_from_string(report.columns[CHECK_STATUS])
        wb = load_workbook(report.destination, read_only=True)
        try:
            ws = wb[AUTOMATED_SHEET]
            values = [row[0].value for row in
                      ws.iter_rows(min_row=report.header_row + 1,
                                   min_col=column, max_col=column)]
        finally:
            wb.close()
        assert set(values) <= {None}

    def test_the_writer_reports_writing_no_cell_in_it(self, exported):
        _, report = exported
        assert report.check_status_cells_written == 0
