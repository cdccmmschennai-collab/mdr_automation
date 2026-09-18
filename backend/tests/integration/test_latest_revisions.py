"""`Latest Revisions`: one complete row per document, on the automated sheet.

Additive to Phase 2D: `QatarEnergy-TN Automated` is unchanged (see
`TestTheAutomatedSheetIsUnchanged` and `test_automated_workbook.py`, which
still passes untouched); a new sheet is appended after it, filtered to the
row `engine.revision.ranking.determine_latest` marked `is_latest_revision`
for each document group. No revision comparison is reimplemented here - the
tests exist to prove that fact, by running the real pipeline over a small
multi-revision fixture and checking what came out the other end.
"""

from __future__ import annotations

from copy import copy

import pytest
from openpyxl import load_workbook

from app.domain.models.automation import (
    AUTOMATION_COLUMNS, DOC_IS_REQUIRED_SOW, DOC_TYPE, DOC_WITH_REV,
)
from app.infrastructure.excel.output_workbook import (
    AUTOMATED_SHEET, LATEST_REVISIONS_SHEET, read_automation_columns,
)
from app.services.automation_service import build_automation_rows
from app.services.export_service import export_automated_workbook
from app.services.mdr_pipeline import MdrEngine
from tests.support.latest_revisions import (
    MIXED_DOCUMENT_ROWS, build_revision_workbook,
)

SOURCE_SHEETS = ["QatarEnergy-TN", "TN FROM VENDORS", "Status Codes",
                 "VENDOR LIST"]


def _run(path, document_rows):
    """Phase 1 -> Phase 2D over `document_rows`, exactly as `--excel` does,
    with the `is_latest_revision` the engine already computed handed to the
    writer - no rules workbook, so DOC TYPE/SOW are blank for every row."""
    build_revision_workbook(path, document_rows)
    result = MdrEngine(path, rules_workbook=None).run()
    rows = build_automation_rows(result.documents, sow_resolver=None,
                                 idb_resolver=_NoOpIdbResolver())
    latest = {d.source_row for d in result.documents if d.is_latest_revision}
    return result, rows, latest


class _NoOpIdbResolver:
    """A minimal stand-in: no rules workbook means no SOW requirement ever
    reaches Phase 2C, so its answer does not matter to these tests."""

    def resolve(self, requirement=None, recorded_outcome=""):
        from app.domain.models.idb import UNMAPPED, IdbStatus
        return IdbStatus(status=UNMAPPED, source="UNMAPPED_NO_RULES")


@pytest.fixture(scope="module")
def mixed(tmp_path_factory):
    """The full chain over `MIXED_DOCUMENT_ROWS`, exported once."""
    tmp = tmp_path_factory.mktemp("latest-revisions")
    source = tmp / "MIXED.xlsx"
    result, rows, latest = _run(source, MIXED_DOCUMENT_ROWS)
    outdir = tmp_path_factory.mktemp("latest-revisions-out")
    report = export_automated_workbook(source, rows, outdir,
                                       latest_source_rows=latest)
    return source, result, rows, latest, report


@pytest.fixture(scope="module")
def mixed_output(mixed):
    _, _, _, _, report = mixed
    wb = load_workbook(report.destination, data_only=True)
    yield wb
    wb.close()


def _by_doc_with_rev(rows_dicts):
    return {r[DOC_WITH_REV]: r for r in rows_dicts}


class TestNumericRevisionProgression:
    """TEST 1: 0, 1, 2 -> only 2 is latest."""

    def test_doc_num_001_keeps_only_revision_2(self, mixed):
        _, _, _, _, report = mixed
        _, _, rows = read_automation_columns(report.destination,
                                             LATEST_REVISIONS_SHEET)
        by_doc = _by_doc_with_rev(rows)
        assert "DOC-NUM-001-2" in by_doc
        assert "DOC-NUM-001-0" not in by_doc
        assert "DOC-NUM-001-1" not in by_doc


class TestAlphabeticRevisionProgression:
    """TEST 2: A, B, C -> only the highest letter is latest."""

    def test_doc_alp_002_keeps_only_revision_b(self, mixed):
        _, _, _, _, report = mixed
        _, _, rows = read_automation_columns(report.destination,
                                             LATEST_REVISIONS_SHEET)
        by_doc = _by_doc_with_rev(rows)
        assert "DOC-ALP-002-B" in by_doc
        assert "DOC-ALP-002-A" not in by_doc


class TestMixedDocumentSet:
    """TEST 3: several documents at once, each contributing its own winner."""

    def test_contains_exactly_the_three_eligible_latest_rows(self, mixed):
        _, _, _, _, report = mixed
        _, _, rows = read_automation_columns(report.destination,
                                             LATEST_REVISIONS_SHEET)
        assert {r[DOC_WITH_REV] for r in rows} == {
            "DOC-NUM-001-2", "DOC-ALP-002-B", "DOC-SGL-003-5",
        }

    def test_the_as_built_only_document_has_no_winner(self, mixed):
        """`Z` is an as-built marker, never eligible to be latest (see
        `engine.revision.parsing`). A document whose only row is `Z` has no
        eligible row in its group, so `determine_latest` marks it an
        exception rather than inventing a winner - and `Latest Revisions`,
        which only ever asks "is this the row `is_latest_revision` marked?",
        correctly contains none of its rows either."""
        _, result, _, latest, _ = mixed
        asb = [d for d in result.documents
              if d.qatarenergy_document_no == "DOC-ASB-004"]
        assert len(asb) == 1
        assert asb[0].is_latest_revision is False
        assert asb[0].source_row not in latest


class TestBlankAutomationFieldsStillAppear:
    """TEST 4: the only selection criterion is latest-ness, not whether the
    automation columns resolved to anything."""

    def test_the_latest_row_is_present_even_with_blank_doc_type_and_sow(
            self, mixed):
        _, _, _, _, report = mixed
        _, _, rows = read_automation_columns(report.destination,
                                             LATEST_REVISIONS_SHEET)
        by_doc = _by_doc_with_rev(rows)
        row = by_doc["DOC-NUM-001-2"]
        # No rules workbook was given, so DOC TYPE and SOW are blank for
        # every row in this fixture - exactly the case that must not filter
        # a latest row out.
        assert row[DOC_TYPE] == ""
        assert row[DOC_IS_REQUIRED_SOW] == ""


class TestTheAutomatedSheetIsUnchanged:
    """TEST 5: adding `Latest Revisions` must not touch the existing sheet."""

    def test_the_row_count_matches_the_source(self, mixed_output):
        assert mixed_output[AUTOMATED_SHEET].max_row == \
            len(MIXED_DOCUMENT_ROWS) + 1          # + header row

    def test_every_document_row_is_still_there_unfiltered(self, mixed):
        _, _, _, _, report = mixed
        _, _, rows = read_automation_columns(report.destination,
                                             AUTOMATED_SHEET)
        assert {r[DOC_WITH_REV] for r in rows} == {
            "DOC-NUM-001-0", "DOC-NUM-001-1", "DOC-NUM-001-2",
            "DOC-ALP-002-A", "DOC-ALP-002-B", "DOC-SGL-003-5",
            "DOC-ASB-004-Z",
        }

    def test_the_four_automation_headers_are_unchanged(self, mixed_output):
        row = [c.value for c in mixed_output[AUTOMATED_SHEET][1]]
        for caption in AUTOMATION_COLUMNS:
            assert caption in row


class TestSourceWorkbookPreservation:
    """TEST 6: every original sheet survives, cell for cell."""

    def test_every_source_sheet_is_present(self, mixed_output):
        assert set(SOURCE_SHEETS) <= set(mixed_output.sheetnames)

    def test_the_source_sheet_gained_no_automation_columns(self, mixed_output):
        captions = [c.value for c in mixed_output["QatarEnergy-TN"][1]]
        assert not set(AUTOMATION_COLUMNS) & set(captions)


class TestTheFinalWorkbook:
    """TEST 7: `Latest Revisions` exists, is last, one row per document."""

    def test_latest_revisions_exists(self, mixed_output):
        assert LATEST_REVISIONS_SHEET in mixed_output.sheetnames

    def test_latest_revisions_is_the_final_sheet(self, mixed_output):
        assert mixed_output.sheetnames[-1] == LATEST_REVISIONS_SHEET

    def test_automated_sheet_is_second_to_last(self, mixed_output):
        assert mixed_output.sheetnames[-2] == AUTOMATED_SHEET

    def test_exactly_one_row_per_document_that_has_a_winner(self, mixed):
        """3 winners: DOC-NUM-001, DOC-ALP-002, DOC-SGL-003.
        DOC-ASB-004 has none - see `test_the_as_built_only_document_has_no_winner`."""
        _, _, _, latest, report = mixed
        _, _, rows = read_automation_columns(report.destination,
                                             LATEST_REVISIONS_SHEET)
        assert len(rows) == 3
        assert len(latest) == 3

    def test_each_row_carries_the_complete_automation_columns_not_just_identity(
            self, mixed):
        _, _, _, _, report = mixed
        _, letters, rows = read_automation_columns(report.destination,
                                                    LATEST_REVISIONS_SHEET)
        assert set(letters) == set(AUTOMATION_COLUMNS)
        for row in rows:
            assert all(caption in row for caption in AUTOMATION_COLUMNS)

    def test_the_row_wears_the_automated_sheets_own_header_style(self,
                                                                  mixed_output):
        """Not a new visual design: the green automation-header fill on
        `Latest Revisions` is the same fill `QatarEnergy-TN Automated` wears,
        cell for cell."""
        automated = mixed_output[AUTOMATED_SHEET]
        latest = mixed_output[LATEST_REVISIONS_SHEET]
        for col in range(1, automated.max_column + 1):
            a = automated.cell(row=1, column=col)
            l = latest.cell(row=1, column=col)
            assert a.value == l.value
            assert copy(a.fill) == copy(l.fill)
            assert a.font.bold == l.font.bold


class TestWriterDefaultWhenNoLatestInfoIsGiven:
    """Backward-compatible default for callers that do not (yet) know which
    rows are latest - every existing test in `test_automated_workbook.py`
    calls the writer this way."""

    def test_every_written_row_is_treated_as_latest(self, tmp_path):
        source = tmp_path / "SRC.xlsx"
        result, rows, _ = _run(source, MIXED_DOCUMENT_ROWS)
        report = export_automated_workbook(source, rows, tmp_path / "out")
        _, _, latest_rows = read_automation_columns(report.destination,
                                                     LATEST_REVISIONS_SHEET)
        _, _, automated_rows = read_automation_columns(report.destination,
                                                        AUTOMATED_SHEET)
        assert len(latest_rows) == len(automated_rows)
