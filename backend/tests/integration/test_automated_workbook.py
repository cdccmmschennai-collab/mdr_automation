"""Phase 2D export: the generated .xlsx, opened and inspected.

Every assertion here is made against a file on disk that has been written,
closed and reopened - not against the objects that were in memory when it was
written. A workbook that is correct only until it is saved is not a
deliverable.

The fixture workbook is built in code (`tests/support/automation.py`) so this
suite runs in under a second and covers the cases the real file does not
happen to contain. `test_phase2d_pipeline.py` runs the same exporter over the
real 22,009-row workbook.
"""

from copy import copy

import pytest
from openpyxl import load_workbook

from app.domain.models.automation import (
    AUTOMATION_COLUMNS, CHECK_STATUS, DOC_IDB_COMPLETED_STATUS,
    DOC_IS_REQUIRED_SOW, DOC_TYPE, DOC_WITH_REV, AutomationRow,
)
from app.infrastructure.excel.output_workbook import (
    AUTOMATED_SHEET, HEADER_FILL_RGB, AutomatedWorkbookWriter,
    OutputWouldOverwriteSource, read_automation_columns,
)
from app.infrastructure.filesystem.artifact_writer import sha256_file
from app.services.export_service import (
    automated_workbook_path, export_automated_workbook,
)
from tests.support.automation import (
    ANCHOR_COLUMN, BAND_ROW, DATA_ROWS, DOCUMENT_ROWS, FIRST_DATA_ROW,
    HEADER_FONT, HEADER_ROW, HEADERS, TRAILING_NUMBER_FORMAT, TRAILING_STYLE,
    WORKING_SHEET, build_source_workbook, sample_rows,
)

SOURCE_SHEETS = ["QatarEnergy-TN", "TN FROM VENDORS", "Status Codes",
                 "VENDOR LIST"]

#: Where the five columns land in the fixture: inserted before `QATARENERGY
#: SIGNED / NOT SIGNED` (column I), as `QatarEnergy-TN WORKING` puts them
#: before the same caption at AK.
AUTOMATION_LETTERS = ["I", "J", "K", "L", "M"]
FIRST_AUTOMATION_COLUMN = ANCHOR_COLUMN                     # 9 -> 'I'
CHECK_STATUS_COLUMN = ANCHOR_COLUMN + 4                     # 13 -> 'M'
#: The three trailing captions, pushed right by the five inserted columns.
TRAILING_LETTERS = ["N", "O", "P"]
#: The caption immediately left of the block - `REMARKS`, as `(PREPARED /NOT
#: PREPARED BY MEDGULF)` is at AJ on the real sheet - whose style the five
#: captions inherit. And the column the block displaced, now to its right.
TEMPLATE_LETTER = "H"
DISPLACED_LETTER = TRAILING_LETTERS[0]


def _style_of(cell) -> dict:
    """Every style component of a cell but the fill, as comparable values.

    The openpyxl style proxies do not compare with one another, so each is
    copied out to the plain style object it wraps. `style` is the named cell
    style (`Normal`, `Accent1`, ...) the cell is based on.
    """
    return {
        "font": copy(cell.font),
        "border": copy(cell.border),
        "alignment": copy(cell.alignment),
        "number_format": cell.number_format,
        "protection": copy(cell.protection),
        "style": cell.style,
    }


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    return build_source_workbook(
        tmp_path_factory.mktemp("phase2d") / "MDR SOURCE.xlsx")


@pytest.fixture(scope="module")
def source_digest(source):
    return sha256_file(source)


@pytest.fixture(scope="module")
def written(source, source_digest, tmp_path_factory):
    """One export, shared by the suite. Returns (report, destination)."""
    outdir = tmp_path_factory.mktemp("phase2d-out")
    report = export_automated_workbook(source, sample_rows(), outdir)
    return report, report.destination


@pytest.fixture(scope="module")
def output(written):
    """The generated workbook, reopened with values only."""
    wb = load_workbook(written[1], data_only=True)
    yield wb
    wb.close()


class TestTheFileExists:
    def test_it_is_written_where_the_export_service_says(self, written, source,
                                                         tmp_path_factory):
        report, destination = written
        assert destination.is_file()
        assert destination.name == "MDR SOURCE_MDR_AUTOMATED.xlsx"
        assert automated_workbook_path(source, destination.parent) == destination

    def test_it_opens(self, output):
        assert output.sheetnames

    def test_re_running_reuses_the_same_path(self, source, written):
        """A deterministic filename, so a re-run replaces its own output
        rather than leaving a second confusing copy beside it."""
        report, destination = written
        again = export_automated_workbook(source, sample_rows(),
                                          destination.parent)
        assert again.destination == destination
        assert len(list(destination.parent.glob("*.xlsx"))) == 1


class TestTheSourceIsUntouched:
    def test_the_sha256_is_unchanged(self, source, source_digest, written):
        assert sha256_file(source) == source_digest

    def test_writing_over_the_source_is_refused_by_the_writer(self, source):
        with pytest.raises(OutputWouldOverwriteSource):
            AutomatedWorkbookWriter(source).write(sample_rows(), source)

    def test_writing_over_the_source_is_refused_by_the_service(self, source):
        with pytest.raises(OutputWouldOverwriteSource):
            export_automated_workbook(source, sample_rows(), source.parent,
                                      destination=source)

    def test_the_source_still_has_no_automation_columns(self, source):
        wb = load_workbook(source)
        try:
            captions = [c.value for c in wb["QatarEnergy-TN"][HEADER_ROW]]
            sheets = wb.sheetnames
        finally:
            wb.close()
        assert [c for c in captions if c] == list(HEADERS)
        assert not set(AUTOMATION_COLUMNS) & set(captions)
        assert sheets == SOURCE_SHEETS


class TestTheWorkbookIsPreserved:
    def test_every_original_sheet_is_still_there_in_order(self, output):
        """The employee's sheets keep the order they arrived in, and the one
        new sheet is added at the end."""
        assert output.sheetnames == SOURCE_SHEETS + [AUTOMATED_SHEET]

    def test_only_the_automated_sheet_was_added(self, written):
        report, _ = written
        assert list(report.untouched_sheets) == SOURCE_SHEETS
        assert report.sheet_names.count(AUTOMATED_SHEET) == 1

    def test_the_original_sheet_is_byte_for_byte_the_same_cells(self, source,
                                                               output):
        src = load_workbook(source, data_only=True)
        try:
            before = [[c.value for c in row] for row in src["QatarEnergy-TN"].rows]
        finally:
            src.close()
        after = [[c.value for c in row] for row in output["QatarEnergy-TN"].rows]
        assert after == before

    def test_the_unrelated_sheets_keep_their_data(self, output):
        assert output["TN FROM VENDORS"]["A2"].value == "ACME"
        assert output["Status Codes"]["A1"].value == "ISSUE CODE"

    def test_the_row_count_is_preserved(self, output):
        expected = FIRST_DATA_ROW + len(DATA_ROWS) - 1
        assert output["QatarEnergy-TN"].max_row == expected
        assert output[AUTOMATED_SHEET].max_row == expected

    def test_the_original_columns_are_all_still_present(self, output):
        """All eleven, in their original order - the five new ones are
        inserted between them, so the captions interleave rather than the
        originals being truncated."""
        row = [c.value for c in output[AUTOMATED_SHEET][HEADER_ROW]]
        assert [c for c in row if c in HEADERS] == list(HEADERS)

    def test_the_trailing_block_moved_right_by_five(self, output):
        ws = output[AUTOMATED_SHEET]
        assert [ws[f"{L}{HEADER_ROW}"].value for L in TRAILING_LETTERS] == \
            list(HEADERS[-3:])

    def test_the_trailing_block_took_its_data_with_it(self, output):
        ws = output[AUTOMATED_SHEET]
        assert [ws[f"{L}{FIRST_DATA_ROW}"].value for L in TRAILING_LETTERS] == \
            list(DATA_ROWS[0][-3:])

    def test_the_trailing_block_took_its_widths_with_it(self, output):
        widths = output[AUTOMATED_SHEET].column_dimensions
        assert widths["N"].width == 26.0            # was I
        assert widths["P"].width == 11.5            # was K

    def test_the_title_band_survives(self, output):
        ws = output[AUTOMATED_SHEET]
        assert ws["A1"].value.startswith("GC21107300/4391")
        assert ws["A3"].value == "MJ-184 TRANSMITTAL LOG"

    def test_the_merged_cells_survive(self, output):
        ranges = {str(r) for r in output[AUTOMATED_SHEET].merged_cells.ranges}
        assert {"A1:E1", "A3:C3"} <= ranges

    def test_a_merge_straddling_the_insertion_is_widened_not_moved(self, output):
        """`H4:I4` spans the insertion point, so Excel - and the exporter -
        stretch it to cover the new columns. The real sheet's `AJ4:AK4`
        becomes `AJ4:AR4` in the hand-made working file for the same reason."""
        ranges = {str(r) for r in output[AUTOMATED_SHEET].merged_cells.ranges}
        assert "H4:N4" in ranges
        assert "H4:I4" not in ranges
        assert output[AUTOMATED_SHEET]["H4"].value == "SIGN-OFF"

    def test_the_freeze_pane_survives(self, output):
        """Left of the insertion, so it does not move."""
        assert output[AUTOMATED_SHEET].freeze_panes == "B6"

    def test_the_auto_filter_is_widened_to_cover_the_new_columns(self, output):
        assert output["QatarEnergy-TN"].auto_filter.ref == "A5:K10"
        assert output[AUTOMATED_SHEET].auto_filter.ref == "A5:P10"

    def test_the_conditional_format_moved_with_its_column(self, written):
        wb = load_workbook(written[1])
        try:
            refs = {str(cf.sqref)
                    for cf in wb[AUTOMATED_SHEET].conditional_formatting}
        finally:
            wb.close()
        assert "O6:O10" in refs             # was J6:J10

    def test_the_data_validation_moved_with_its_column(self, written):
        wb = load_workbook(written[1])
        try:
            refs = {str(dv.sqref) for dv in
                    wb[AUTOMATED_SHEET].data_validations.dataValidation}
        finally:
            wb.close()
        assert "N6:N10" in refs             # was I6:I10

    def test_the_column_widths_survive(self, output):
        widths = output[AUTOMATED_SHEET].column_dimensions
        assert widths["B"].width == 30.0
        assert widths["E"].width == 40.0

    def test_the_formula_survives_as_a_formula(self, written):
        wb = load_workbook(written[1])          # not data_only
        try:
            # K4 in the source; five columns were inserted to its left.
            assert wb[AUTOMATED_SHEET]["P4"].value == "=NOW()"
        finally:
            wb.close()

    def test_the_original_row_order_is_kept(self, output):
        ws = output[AUTOMATED_SHEET]
        numbers = [ws.cell(row=r, column=2).value
                   for r in range(FIRST_DATA_ROW,
                                  FIRST_DATA_ROW + len(DATA_ROWS))]
        assert numbers == [(row[1] or None) for row in DATA_ROWS]


class TestTheFiveColumns:
    def test_all_five_headers_exist(self, written):
        _, letters, _ = read_automation_columns(written[1])
        assert set(letters) == set(AUTOMATION_COLUMNS)

    def test_they_sit_where_the_working_sheet_puts_them(self, written):
        """Inserted before `QATARENERGY SIGNED / NOT SIGNED`, not appended
        after the last column - the placement `QatarEnergy-TN WORKING`
        established at AK..AO."""
        report, _ = written
        assert [report.columns[c] for c in AUTOMATION_COLUMNS] == \
            AUTOMATION_LETTERS
        assert report.reused_columns == ()
        assert report.inserted_before == "QATARENERGY SIGNED / NOT SIGNED"
        assert report.inserted_at == FIRST_AUTOMATION_COLUMN
        assert report.inserted_columns == 5

    def test_they_are_in_the_working_sheets_own_order(self, output):
        ws = output[AUTOMATED_SHEET]
        assert [ws[f"{L}{HEADER_ROW}"].value for L in AUTOMATION_LETTERS] == \
            list(AUTOMATION_COLUMNS)

    def test_exactly_one_column_carries_each_caption(self, output):
        captions = [c.value for c in output[AUTOMATED_SHEET][HEADER_ROW]]
        for caption in AUTOMATION_COLUMNS:
            assert captions.count(caption) == 1

    def test_the_source_sheet_did_not_gain_them(self, output):
        captions = [c.value for c in output["QatarEnergy-TN"][HEADER_ROW]]
        assert not set(AUTOMATION_COLUMNS) & set(captions)

    def test_the_values_land_on_their_own_rows(self, written):
        _, _, rows = read_automation_columns(written[1])
        by_row = {r["source_row"]: r for r in rows}
        assert set(by_row) == set(DOCUMENT_ROWS)
        assert by_row[6][DOC_WITH_REV] == "4391-MEWTP-2-13-0005-0"
        assert by_row[6][DOC_TYPE] == "MDS"
        assert by_row[6][DOC_IS_REQUIRED_SOW] == "YES-MTL/DOC IDB"
        assert by_row[10][DOC_IDB_COMPLETED_STATUS] == "NO NEED TO CHECK"

    def test_a_required_document_leaves_the_idb_status_blank(self, output):
        """Row 6 is in scope. Nobody has checked whether its IDB is complete,
        and the automation has no source that could say - so the cell is empty
        and a person fills it in."""
        ws = output[AUTOMATED_SHEET]
        assert ws.cell(row=6, column=FIRST_AUTOMATION_COLUMN + 2).value == \
            "YES-MTL/DOC IDB"
        assert ws.cell(row=6, column=FIRST_AUTOMATION_COLUMN + 3).value is None

    def test_a_not_required_document_needs_no_check(self, output):
        """Row 8 is a `WEEKLY PROGRESS REPORT`, which the `NOT REQUIRED-KEY
        DOC.WORDS` sheet names. Being on that sheet *is* the scope verdict."""
        ws = output[AUTOMATED_SHEET]
        assert ws.cell(row=8, column=FIRST_AUTOMATION_COLUMN + 2).value == "NO"
        assert ws.cell(row=8, column=FIRST_AUTOMATION_COLUMN + 3).value == \
            "NO NEED TO CHECK"

    def test_a_row_the_pipeline_skipped_keeps_five_empty_cells(self, output):
        """Row 9 has no DOCUMENT NO. Its neighbours' answers must not shift
        onto it."""
        ws = output[AUTOMATED_SHEET]
        assert [ws.cell(row=9, column=c).value
                for c in range(FIRST_AUTOMATION_COLUMN,
                               FIRST_AUTOMATION_COLUMN + 5)] == [None] * 5

    def test_every_written_value_is_upper_case(self, written):
        _, _, rows = read_automation_columns(written[1])
        for row in rows:
            for caption in AUTOMATION_COLUMNS:
                assert row[caption] == row[caption].upper()

    def test_the_writer_reports_what_it_wrote(self, written):
        report, _ = written
        assert report.rows_written == len(DOCUMENT_ROWS)
        assert report.source_sheet == "QatarEnergy-TN"
        assert report.automated_sheet == AUTOMATED_SHEET
        assert report.header_row == HEADER_ROW
        assert report.rows_outside_sheet == ()


class TestCheckStatusIsBlank:
    def test_the_column_exists(self, written):
        _, letters, _ = read_automation_columns(written[1])
        assert letters[CHECK_STATUS] == AUTOMATION_LETTERS[-1]

    def test_every_data_cell_in_it_is_empty(self, output):
        ws = output[AUTOMATED_SHEET]
        column = CHECK_STATUS_COLUMN
        assert ws.cell(row=HEADER_ROW, column=column).value == CHECK_STATUS
        assert [ws.cell(row=r, column=column).value
                for r in range(HEADER_ROW + 1, ws.max_row + 1)] == \
            [None] * len(DATA_ROWS)

    def test_it_does_not_say_not_received(self, written):
        """The received-document dump does not exist; its absence is not
        evidence that a document was not received."""
        _, _, rows = read_automation_columns(written[1])
        assert {r[CHECK_STATUS] for r in rows} == {""}

    def test_the_writer_reports_writing_no_cell_in_it(self, written):
        assert written[0].check_status_cells_written == 0

    def test_a_row_cannot_be_built_carrying_one(self):
        """Belt and braces: the model refuses before the writer is reached."""
        with pytest.raises(ValueError):
            AutomationRow(source_row=6, check_status="NOT RECEIVED")


class TestFormatting:
    def test_the_five_captions_sit_at_ak_to_ao_of_the_real_sheet(self, output):
        """Names and positions, before their looks: the block is `I..M` here
        and `AK..AO` on the real sheet, in the working sheet's own order."""
        ws = output[AUTOMATED_SHEET]
        assert [ws[f"{L}{HEADER_ROW}"].value for L in AUTOMATION_LETTERS] == \
            [DOC_WITH_REV, DOC_TYPE, DOC_IS_REQUIRED_SOW,
             DOC_IDB_COMPLETED_STATUS, CHECK_STATUS]
        assert ws[f"{TEMPLATE_LETTER}{HEADER_ROW}"].value == "REMARKS"
        assert ws[f"{DISPLACED_LETTER}{HEADER_ROW}"].value == \
            "QATARENERGY SIGNED / NOT SIGNED"

    def test_the_new_headers_wear_the_neighbouring_captions_whole_style(
            self, output):
        """Every style component but the fill is the caption beside the
        block's, as one copy - font, colour, bold, border, alignment, number
        format, protection and named style - not a hand-picked subset of it.
        Nothing here names a colour or a font: whatever the source's caption
        wears, the five wear."""
        ws = output[AUTOMATED_SHEET]
        template = ws[f"{TEMPLATE_LETTER}{HEADER_ROW}"]
        expected = _style_of(template)
        assert expected["font"].name == HEADER_FONT       # the fixture's own
        assert expected["font"].bold is True
        assert expected["number_format"] == "@"
        assert expected["protection"].locked is False
        assert expected["style"] == "Normal"
        for letter in AUTOMATION_LETTERS:
            assert _style_of(ws[f"{letter}{HEADER_ROW}"]) == expected, letter

    def test_the_new_headers_did_not_copy_the_trailing_date_caption(
            self, output):
        """The right-most caption is a date column in a named style. On the
        real sheet that is `DATE ISSUED` in `Accent1`; a text caption must not
        inherit it, and a writer that copied the wrong neighbour would."""
        ws = output[AUTOMATED_SHEET]
        trailing = ws[f"{DISPLACED_LETTER}{HEADER_ROW}"]
        assert trailing.number_format == TRAILING_NUMBER_FORMAT
        assert trailing.style == TRAILING_STYLE
        for letter in AUTOMATION_LETTERS:
            cell = ws[f"{letter}{HEADER_ROW}"]
            assert cell.number_format != trailing.number_format
            assert cell.style != trailing.style

    def test_the_new_headers_wear_the_working_sheets_own_fill(self, output):
        """Green, as in `QatarEnergy-TN WORKING`: the one thing the automation
        block does differently from the captions beside it. The fill is the
        neighbouring caption's own with the foreground swapped - same pattern,
        same background - so it is the fill Excel wrote on the working sheet,
        not one built from a colour alone."""
        ws = output[AUTOMATED_SHEET]
        template = ws[f"{TEMPLATE_LETTER}{HEADER_ROW}"].fill
        assert template.fgColor.rgb != HEADER_FILL_RGB    # or this proves nothing
        for letter in AUTOMATION_LETTERS:
            fill = ws[f"{letter}{HEADER_ROW}"].fill
            assert fill.fill_type == template.fill_type == "solid"
            assert fill.fgColor.rgb == HEADER_FILL_RGB
            assert fill.bgColor == template.bgColor

    def test_the_rows_above_the_header_keep_their_colour_across_the_block(
            self, source, output):
        """Row 3 is a yellow band from A to the anchor column, as `A3:AK3` on
        the real sheet. Five columns inserted before the anchor must not open
        a white gap in it: each inserted cell above the header wears the style
        of the cell the insertion displaced - the anchor column's own, now to
        the block's right - so the title rows read as they did."""
        ws = output[AUTOMATED_SHEET]
        src = load_workbook(source)
        try:
            band = copy(src["QatarEnergy-TN"].cell(row=BAND_ROW,
                                                   column=ANCHOR_COLUMN).fill)
        finally:
            src.close()
        assert band.fill_type == "solid"
        # The band travelled with the displaced column ...
        displaced = ws[f"{DISPLACED_LETTER}{BAND_ROW}"]
        assert copy(displaced.fill) == band
        # ... and every inserted cell above the captions matches that
        # column, row for row: the band on row 3, and no invented style on
        # the rows that carry none.
        for row in range(1, HEADER_ROW):
            neighbour = ws[f"{DISPLACED_LETTER}{row}"]
            for letter in AUTOMATION_LETTERS:
                cell = ws[f"{letter}{row}"]
                assert copy(cell.fill) == copy(neighbour.fill), (letter, row)
                assert _style_of(cell) == _style_of(neighbour), (letter, row)
        for letter in AUTOMATION_LETTERS:
            assert copy(ws[f"{letter}{BAND_ROW}"].fill) == band

    def test_the_captions_are_the_only_cells_the_block_colours_green(
            self, output):
        """The green belongs to the caption row alone. Above it the block
        wears the title rows' own colours, and none of those is green."""
        ws = output[AUTOMATED_SHEET]
        for row in range(1, HEADER_ROW):
            for letter in AUTOMATION_LETTERS:
                assert ws[f"{letter}{row}"].fill.fgColor.rgb != HEADER_FILL_RGB

    def test_the_data_cells_wear_the_sheets_own_body_style(self, output):
        ws = output[AUTOMATED_SHEET]
        template = ws.cell(row=FIRST_DATA_ROW, column=2)
        for letter in AUTOMATION_LETTERS:
            cell = ws[f"{letter}{FIRST_DATA_ROW}"]
            assert cell.font.name == template.font.name
            assert cell.font.bold == template.font.bold
            assert cell.border.left.style == template.border.left.style

    def test_the_new_columns_are_wide_enough_to_read(self, output):
        widths = output[AUTOMATED_SHEET].column_dimensions
        assert widths["I"].width >= 30      # DOC WITH REV
        assert widths["L"].width >= 20      # DOC IDB COMPLETED STATUS

    def test_no_original_column_keeps_a_width_it_did_not_have(self, source,
                                                              output):
        """Every original width survives, on whichever column now carries that
        caption - the widths right of the insertion moved with their data."""
        src = load_workbook(source)
        try:
            ws_src = src["QatarEnergy-TN"]
            before = {k: v.width
                      for k, v in ws_src.column_dimensions.items()}
        finally:
            src.close()
        after = output[AUTOMATED_SHEET].column_dimensions
        shifted = {"I": "N", "K": "P"}      # right of the insertion point
        for letter, width in before.items():
            assert after[shifted.get(letter, letter)].width == width


class TestExportingAnAlreadyAutomatedWorkbook:
    """A second pass must replace its own sheet, not accumulate copies."""

    @pytest.fixture(scope="class")
    def rerun(self, written, tmp_path_factory):
        again = tmp_path_factory.mktemp("phase2d-rerun") / "AGAIN.xlsx"
        rows = [AutomationRow(source_row=6, doc_with_rev="CHANGED-0",
                              doc_type="MXB", sow="NO",
                              idb_status="NO NEED TO CHECK",
                              idb_source="SOW_NOT_REQUIRED")]
        report = AutomatedWorkbookWriter(written[1]).write(rows, again)
        return report, again

    def test_the_automated_sheet_is_replaced_not_duplicated(self, rerun):
        report, _ = rerun
        assert report.sheet_names.count(AUTOMATED_SHEET) == 1
        assert not any(n != AUTOMATED_SHEET and n.startswith(AUTOMATED_SHEET)
                       for n in report.sheet_names)

    def test_the_copy_is_taken_from_the_untouched_source_sheet(self, rerun):
        """`QatarEnergy-TN` never gains the columns, so a re-run cannot
        compound its own output."""
        report, _ = rerun
        assert report.source_sheet == "QatarEnergy-TN"
        assert [report.columns[c] for c in AUTOMATION_COLUMNS] == \
            AUTOMATION_LETTERS

    def test_the_values_are_the_new_ones(self, rerun):
        _, _, rows = read_automation_columns(rerun[1])
        assert [r[DOC_WITH_REV] for r in rows] == ["CHANGED-0"]


class TestAWorkbookThatAlreadyCarriesACaption:
    """§6: update the cells, do not create a second column of the same name."""

    @pytest.fixture(scope="class")
    def prepared(self, tmp_path_factory):
        """A source sheet that already has `DOC TYPE` in column L, holding a
        stale value that the export must overwrite."""
        path = build_source_workbook(
            tmp_path_factory.mktemp("phase2d-existing") / "HAS COLUMN.xlsx")
        wb = load_workbook(path)
        try:
            ws = wb["QatarEnergy-TN"]
            ws.cell(row=HEADER_ROW, column=12, value=DOC_TYPE)
            ws.cell(row=FIRST_DATA_ROW, column=12, value="STALE")
            wb.save(path)
        finally:
            wb.close()

        out = tmp_path_factory.mktemp("phase2d-existing-out")
        return AutomatedWorkbookWriter(path).write(sample_rows(),
                                                   out / "OUT.xlsx")

    def test_the_existing_column_is_reused(self, prepared):
        assert prepared.reused_columns == (DOC_TYPE,)
        # Column L, pushed right by the four columns inserted at I.
        assert prepared.columns[DOC_TYPE] == "P"

    def test_only_room_for_the_missing_four_is_inserted(self, prepared):
        assert prepared.inserted_columns == 4
        assert [prepared.columns[c] for c in AUTOMATION_COLUMNS] == \
            ["I", "P", "J", "K", "L"]

    def test_no_duplicate_caption_is_created(self, prepared):
        wb = load_workbook(prepared.destination)
        try:
            captions = [c.value for c in wb[AUTOMATED_SHEET][HEADER_ROW]]
        finally:
            wb.close()
        assert captions.count(DOC_TYPE) == 1

    def test_the_stale_value_is_overwritten(self, prepared):
        _, _, rows = read_automation_columns(prepared.destination)
        by_row = {r["source_row"]: r for r in rows}
        assert by_row[6][DOC_TYPE] == "MDS"


# --------------------------------------------------------------------------
# An MDR arrives either untouched or already worked on by hand. The
# automation's behaviour is the same in both cases: read `QatarEnergy-TN`,
# add `QatarEnergy-TN Automated`, touch nothing else.

UNWORKED_SHEETS = ["QatarEnergy-TN", "TN FROM VENDORS", "Status Codes",
                   "VENDOR LIST"]
WORKED_SHEETS = UNWORKED_SHEETS + [WORKING_SHEET]


def _cells(path, sheet):
    """Every cell value of one sheet, for an exact before/after comparison."""
    wb = load_workbook(path, data_only=True)
    try:
        return [[c.value for c in row] for row in wb[sheet].rows]
    finally:
        wb.close()


class TestAnUnworkedWorkbook:
    """Test A: four sheets in, five out."""

    @pytest.fixture(scope="class")
    def exported(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("unworked")
        source = build_source_workbook(tmp / "UNWORKED.xlsx", worked=False)
        report = AutomatedWorkbookWriter(source).write(
            sample_rows(), tmp / "out" / "OUT.xlsx")
        return source, report

    def test_the_input_had_no_working_sheet(self, exported):
        source, _ = exported
        wb = load_workbook(source, read_only=True)
        try:
            assert wb.sheetnames == UNWORKED_SHEETS
        finally:
            wb.close()

    def test_the_output_is_the_four_sheets_plus_the_automated_one(self,
                                                                  exported):
        _, report = exported
        assert list(report.sheet_names) == UNWORKED_SHEETS + [AUTOMATED_SHEET]

    def test_no_working_sheet_is_invented(self, exported):
        """The automation writes `QatarEnergy-TN Automated` and nothing else.
        It does not create the sheet the employee has not made."""
        _, report = exported
        assert WORKING_SHEET not in report.sheet_names

    def test_every_original_sheet_is_cell_for_cell_unchanged(self, exported):
        source, report = exported
        for sheet in UNWORKED_SHEETS:
            assert _cells(report.destination, sheet) == _cells(source, sheet)

    def test_the_five_columns_are_at_the_working_positions(self, exported):
        _, report = exported
        assert [report.columns[c] for c in AUTOMATION_COLUMNS] == \
            AUTOMATION_LETTERS


class TestAnAlreadyWorkedWorkbook:
    """Test B: five sheets in, six out, and the worked one untouched."""

    @pytest.fixture(scope="class")
    def exported(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("worked")
        source = build_source_workbook(tmp / "WORKED.xlsx", worked=True)
        report = AutomatedWorkbookWriter(source).write(
            sample_rows(), tmp / "out" / "OUT.xlsx")
        return source, report

    def test_the_input_had_a_working_sheet(self, exported):
        source, _ = exported
        wb = load_workbook(source, read_only=True)
        try:
            assert wb.sheetnames == WORKED_SHEETS
        finally:
            wb.close()

    def test_the_output_is_the_five_sheets_plus_the_automated_one(self,
                                                                  exported):
        _, report = exported
        assert list(report.sheet_names) == WORKED_SHEETS + [AUTOMATED_SHEET]

    def test_exactly_one_automated_sheet_is_added(self, exported):
        _, report = exported
        assert report.sheet_names.count(AUTOMATED_SHEET) == 1
        assert not any(n != AUTOMATED_SHEET and n.startswith(AUTOMATED_SHEET)
                       for n in report.sheet_names)

    def test_every_original_sheet_including_the_worked_one_is_unchanged(
            self, exported):
        source, report = exported
        for sheet in WORKED_SHEETS:
            assert _cells(report.destination, sheet) == _cells(source, sheet)

    def test_the_data_comes_from_the_original_sheet_not_the_worked_one(self,
                                                                       exported):
        _, report = exported
        assert report.source_sheet == "QatarEnergy-TN"

    def test_the_manual_completion_values_are_not_copied(self, exported):
        """The whole point: `COMPLETED`, `PENDING` and `CANCELLED` are on the
        worked sheet because a person put them there. They are not evidence
        about this run, and the automation must not repeat them."""
        _, report = exported
        _, _, rows = read_automation_columns(report.destination)
        produced = {r[DOC_IDB_COMPLETED_STATUS] for r in rows}
        assert produced <= {"", "NO NEED TO CHECK"}
        assert not produced & {"COMPLETED", "PENDING", "CANCELLED"}

    def test_the_manual_check_status_is_not_copied_either(self, exported):
        _, report = exported
        _, _, rows = read_automation_columns(report.destination)
        assert {r[CHECK_STATUS] for r in rows} == {""}

    def test_a_required_document_gets_a_blank_not_the_worked_sheets_answer(
            self, exported):
        """Row 6 reads `COMPLETED` on the worked sheet. The automated sheet
        leaves it blank, because nothing the automation reads says so."""
        _, report = exported
        _, _, rows = read_automation_columns(report.destination)
        by_row = {r["source_row"]: r for r in rows}
        assert by_row[6][DOC_IS_REQUIRED_SOW] == "YES-MTL/DOC IDB"
        assert by_row[6][DOC_IDB_COMPLETED_STATUS] == ""

    def test_the_five_columns_are_at_the_working_positions(self, exported):
        _, report = exported
        assert [report.columns[c] for c in AUTOMATION_COLUMNS] == \
            AUTOMATION_LETTERS

    def test_the_worked_sheet_is_never_the_output(self, exported):
        _, report = exported
        assert report.automated_sheet == AUTOMATED_SHEET
        assert WORKING_SHEET in report.untouched_sheets


# --------------------------------------------------------------------------
# The download contract, pinned.
#
# Phase 4 hands this file to an employee over HTTP, and everything downstream
# - the API, the frontend, the employee's own eye - finds the automation by
# the sheet's name and the captions on it. Those are an interface, not an
# implementation detail, so they are asserted as literals here: a refactor
# that renames them has to come and change this test on purpose.

#: The sheet name the product requires. Deliberately *not* `AUTOMATED_SHEET` -
#: the point is to pin the value the constant is allowed to hold, so a rename
#: has to be made here on purpose rather than propagating silently.
CONTRACT_SHEET = "QatarEnergy-TN Automated"

#: The four columns the automation is required to fill. CHECK STATUS is the
#: fifth caption on the sheet and is deliberately not here: it has no engine
#: behind it yet, and `TestCheckStatusIsBlank` asserts it stays empty.
CONTRACT_COLUMNS = (DOC_WITH_REV, DOC_TYPE, DOC_IS_REQUIRED_SOW,
                    DOC_IDB_COMPLETED_STATUS)


class TestTheDownloadContract:
    def test_the_sheet_carries_the_contract_name(self, output):
        assert AUTOMATED_SHEET == CONTRACT_SHEET
        assert CONTRACT_SHEET in output.sheetnames

    def test_the_original_sheets_are_all_still_there_beside_it(self, output):
        """The contract is the employee's workbook *plus* a sheet, never a
        sheet instead of the workbook."""
        assert output.sheetnames == SOURCE_SHEETS + [CONTRACT_SHEET]

    def test_the_four_required_captions_are_on_it(self, written):
        _, letters, _ = read_automation_columns(written[1], CONTRACT_SHEET)
        assert set(CONTRACT_COLUMNS) <= set(letters)

    def test_every_document_row_carries_the_four_values(self, written):
        """Populated, not merely present. A blank DOC IDB COMPLETED STATUS is
        the one permitted empty - it means `MANUAL_CHECK_REQUIRED` - so it is
        checked for presence of the key rather than a value."""
        _, _, rows = read_automation_columns(written[1], CONTRACT_SHEET)
        assert {r["source_row"] for r in rows} == set(DOCUMENT_ROWS)
        for row in rows:
            assert all(caption in row for caption in CONTRACT_COLUMNS)
            assert row[DOC_WITH_REV]
            assert row[DOC_TYPE]
            assert row[DOC_IS_REQUIRED_SOW]

    def test_the_sheet_name_survives_a_re_export(self, source,
                                                 tmp_path_factory):
        """A second pass over an already-automated workbook keeps the one
        contract sheet - it does not add a second, suffixed copy beside it."""
        tmp = tmp_path_factory.mktemp("contract-rerun")
        first = AutomatedWorkbookWriter(source).write(sample_rows(),
                                                      tmp / "ONE.xlsx")
        second = AutomatedWorkbookWriter(first.destination).write(
            sample_rows(), tmp / "TWO.xlsx")
        assert list(second.sheet_names).count(CONTRACT_SHEET) == 1
        assert second.automated_sheet == CONTRACT_SHEET


# --------------------------------------------------------------------------
# Determinism.
#
# The same workbook and the same rows must produce the same answers every
# time. The .xlsx *bytes* are not comparable - openpyxl stamps the save time
# into `docProps/core.xml` - so the comparison is made over everything the
# employee and the API actually read: the sheet names, the column placement
# and every cell on the automated sheet.

def _automated_grid(path):
    """Every cell of the automated sheet, as plain values."""
    wb = load_workbook(path, data_only=True)
    try:
        return [[c.value for c in row] for row in wb[AUTOMATED_SHEET].rows]
    finally:
        wb.close()


class TestRepeatedRunsAreDeterministic:
    @pytest.fixture(scope="class")
    def twice(self, source, tmp_path_factory):
        """Two independent exports of the same source, to separate files."""
        tmp = tmp_path_factory.mktemp("determinism")
        first = AutomatedWorkbookWriter(source).write(sample_rows(),
                                                     tmp / "FIRST.xlsx")
        second = AutomatedWorkbookWriter(source).write(sample_rows(),
                                                      tmp / "SECOND.xlsx")
        return first, second

    def test_the_sheets_are_the_same(self, twice):
        first, second = twice
        assert first.sheet_names == second.sheet_names
        assert first.untouched_sheets == second.untouched_sheets

    def test_the_columns_land_in_the_same_places(self, twice):
        first, second = twice
        assert first.columns == second.columns
        assert first.inserted_at == second.inserted_at
        assert first.inserted_columns == second.inserted_columns
        assert first.inserted_before == second.inserted_before
        assert first.reused_columns == second.reused_columns

    def test_the_same_rows_are_written(self, twice):
        first, second = twice
        assert first.rows_written == second.rows_written
        assert first.header_row == second.header_row
        assert first.rows_outside_sheet == second.rows_outside_sheet

    def test_every_automation_value_is_identical(self, twice):
        first, second = twice
        assert read_automation_columns(first.destination) == \
            read_automation_columns(second.destination)

    def test_every_cell_of_the_automated_sheet_is_identical(self, twice):
        """Not just the five columns - the whole copied sheet, so a
        non-deterministic *copy* is caught too."""
        first, second = twice
        assert _automated_grid(first.destination) == \
            _automated_grid(second.destination)


class TestTheSourceFileIsNotTouchedAtAll:
    """Beyond the digest: the file is not rewritten with identical bytes.

    A writer that opened the source for update and saved it back unchanged
    would keep its SHA-256 and still be a bug - it would take the employee's
    lock, bump the mtime, and prove the input is not being treated as
    read-only. Size and mtime catch that; the digest catches content.
    """

    @pytest.fixture(scope="class")
    def stats(self, source, tmp_path_factory):
        before = source.stat()
        digest = sha256_file(source)
        export_automated_workbook(
            source, sample_rows(), tmp_path_factory.mktemp("untouched"))
        return before, digest, source.stat(), sha256_file(source)

    def test_the_digest_is_unchanged(self, stats):
        _, digest, _, after = stats
        assert after == digest

    def test_the_size_is_unchanged(self, stats):
        before, _, after, _ = stats
        assert after.st_size == before.st_size

    def test_the_modification_time_is_unchanged(self, stats):
        before, _, after, _ = stats
        assert after.st_mtime == before.st_mtime
