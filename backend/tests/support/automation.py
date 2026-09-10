"""A small MDR workbook, built in code, for the Phase 2D export tests.

The real file is 22,009 rows and takes minutes to copy; almost everything the
exporter has to get right can be shown on nine rows. What matters is that the
fixture has the *shapes* the real workbook has and that the writer must not
lose: a four-row title band above the header, merged cells in it, a formula, a
frozen pane, an auto-filter, styled headers, column widths, a row with no
DOCUMENT NO. that the pipeline skips, and columns to the right of the last one
the engine reads.

`tests/integration/test_phase2d_pipeline.py` runs the same exporter over the
real workbook and holds this fixture honest.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import (
    Alignment, Border, Font, NamedStyle, PatternFill, Protection, Side,
)
from openpyxl.worksheet.datavalidation import DataValidation

from app.domain.models.automation import AutomationRow

#: Row 5, mirroring the real sheet's captions (including its 'ORGINATOR'
#: spelling) so `detect_header_row` and `index` behave as they do in
#: production. Columns A..K.
#:
#: The last three mirror the real sheet's trailing block - AK/AL/AM there -
#: because that is what the exporter has to shift sideways: `QatarEnergy-TN
#: WORKING` puts the five automation columns *before* `QATARENERGY SIGNED /
#: NOT SIGNED`, not after `DATE ISSUED`.
HEADERS: tuple[str, ...] = (
    "TN. NO OUT to (QE)", "DOCUMENT NO.", "REV", "DISCIPLINE",
    "DOCUMENT TITLE", "ISSUED STATUS IN PDMS", "LATEST/ NOT LATEST",
    "REMARKS", "QATARENERGY SIGNED / NOT SIGNED", "AFC DOCUMENT\nTN NO.",
    "DATE ISSUED",
)

#: 1-based index of the caption the automation block is inserted before, and
#: therefore the first automation column in the generated sheet.
ANCHOR_COLUMN = 9                       # 'QATARENERGY SIGNED / NOT SIGNED'

HEADER_ROW = 5
FIRST_DATA_ROW = 6

#: One tuple per data row, in sheet order. Row 9 has no DOCUMENT NO. - the
#: pipeline produces no record for it, and the exporter must leave its five
#: cells empty rather than shuffling its neighbours' answers onto it.
DATA_ROWS: tuple[tuple[str, ...], ...] = (
    ("TN-001", "4391-MEWTP-2-13-0005", "0", "ELE", "DATASHEET FOR LV MOTOR",
     "IFR", "LATEST", "", "SIGNED", "AFC-001", "2026-01-04"),
    ("TN-002", "4391-M3UT-6-51-0007-001", "A", "PRO", "UTILITY P&ID: LAYDOWN",
     "IFR", "LATEST", "", "SIGNED", "AFC-002", "2026-01-05"),
    ("TN-003", "4391-MG-WPR-0041", "1", "PMT", "WEEKLY PROGRESS REPORT",
     "IFI", "LATEST", "", "NOT SIGNED", "AFC-003", "2026-01-06"),
    ("TN-004", "", "", "", "", "", "", "SPACER ROW - NO DOCUMENT", "", "", ""),
    ("TN-005", "VEN-MEWTP-5-43-0011", "-", "MEC", "SPIR INITIAL: LOCAL PANEL",
     "IFR", "NOT LATEST", "", "SIGNED", "AFC-005", "2026-01-08"),
)

#: The rows the exporter is expected to address, by Excel row number.
DOCUMENT_ROWS: tuple[int, ...] = (6, 7, 8, 10)

HEADER_FILL = "FFD9D9D9"
HEADER_FONT = "Arial"

#: The yellow stripe the real sheet draws across row 3, from A to the anchor
#: column and no further - the trailing date columns sit outside it. The
#: exporter has to carry it across the five inserted columns rather than leave
#: a white gap where the block is.
BAND_ROW = 3
BAND_FILL = "FFFFFF00"

#: The named style the real sheet's trailing date captions wear (`Accent1`,
#: beside the `Normal` of every text caption). It exists in the fixture so a
#: header copied from the wrong caption is caught by its named style too.
TRAILING_STYLE = "Accent1"
TRAILING_NUMBER_FORMAT = "[$-409]d\\-mmm\\-yy;@"


def build_source_workbook(path: Path, worked: bool = False) -> Path:
    """Write a small but structurally faithful MDR workbook to `path`.

    `worked=True` adds a hand-made `QatarEnergy-TN WORKING`, which is how an
    MDR arrives from an employee who has already started on it. The automation
    has to behave identically either way: read `QatarEnergy-TN`, add
    `QatarEnergy-TN Automated`, touch nothing else.
    """
    wb = Workbook()

    ws = wb.active
    ws.title = "QatarEnergy-TN"

    # -- the title band above the header ---------------------------------
    ws["A1"] = "GC21107300/4391 ENGINEERING, PROCUREMENT AND CONSTRUCTION"
    ws.merge_cells("A1:E1")
    ws["A3"] = "MJ-184 TRANSMITTAL LOG"
    ws.merge_cells("A3:C3")
    ws["A4"] = "CONTRACT NO.GC21107300"
    ws["K4"] = "=NOW()"                     # a formula, to be preserved
    # A merge that *straddles* the insertion point, as `AJ4:AK4` does on the
    # real sheet. Excel widens such a merge rather than moving it, and so must
    # the exporter.
    ws["H4"] = "SIGN-OFF"
    ws.merge_cells("H4:I4")
    # The band across row 3 stops at the anchor column, as `A3:AK3` does on
    # the real sheet - so the columns right of the insertion are *not* all
    # alike, and copying the wrong neighbour shows.
    thin = Side(style="thin")
    for i in range(1, ANCHOR_COLUMN + 1):
        cell = ws.cell(row=BAND_ROW, column=i)
        cell.fill = PatternFill("solid", fgColor=BAND_FILL)
        cell.font = Font(name=HEADER_FONT, size=13.5, bold=True)
        cell.border = Border(top=thin, bottom=thin)

    # -- the header row ---------------------------------------------------
    # Every caption shares the house style; the ones beside the insertion
    # point differ the way the real sheet's do. `REMARKS`, left of the block,
    # is a text caption in the `Normal` style with the `@` format, unlocked
    # and vertically centred - the style `(PREPARED /NOT PREPARED BY
    # MEDGULF)` has at AJ5 and the working sheet's five captions copy. The
    # trailing block, right of it, carries a date format and a named style,
    # as AK5 and AM5 do. The five new captions must inherit the former.
    wb.add_named_style(NamedStyle(name=TRAILING_STYLE))
    for i, caption in enumerate(HEADERS, start=1):
        cell = ws.cell(row=HEADER_ROW, column=i, value=caption)
        if i >= ANCHOR_COLUMN:
            cell.style = TRAILING_STYLE     # first: it resets what follows
            cell.number_format = TRAILING_NUMBER_FORMAT
        cell.font = Font(name=HEADER_FONT, size=11, bold=True)
        cell.fill = PatternFill("solid", fgColor=HEADER_FILL)
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        if i < ANCHOR_COLUMN:
            cell.number_format = "@"
            cell.protection = Protection(locked=False)

    # -- the data ---------------------------------------------------------
    for r, values in enumerate(DATA_ROWS, start=FIRST_DATA_ROW):
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value or None)
            cell.font = Font(name=HEADER_FONT, size=11)
            cell.alignment = Alignment(horizontal="center")
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.column_dimensions["B"].width = 30.0
    ws.column_dimensions["E"].width = 40.0
    # Widths on the trailing block, which the insertion has to carry right
    # with the columns they belong to.
    ws.column_dimensions["I"].width = 26.0
    ws.column_dimensions["K"].width = 11.5
    ws.freeze_panes = "B6"
    last_row = FIRST_DATA_ROW + len(DATA_ROWS) - 1
    ws.auto_filter.ref = f"A{HEADER_ROW}:K{last_row}"
    # A conditional format and a validation on the trailing block, so the
    # exporter is held to moving those too and not only the cells.
    ws.conditional_formatting.add(
        f"J{FIRST_DATA_ROW}:J{last_row}",
        CellIsRule(operator="equal", formula=['"AFC-001"'],
                   fill=PatternFill("solid", fgColor="FFFFC000")))
    validation = DataValidation(type="list", formula1='"SIGNED,NOT SIGNED"')
    ws.add_data_validation(validation)
    validation.add(f"I{FIRST_DATA_ROW}:I{last_row}")

    # -- the sheets the exporter must leave alone -------------------------
    vendors = wb.create_sheet("TN FROM VENDORS")
    vendors["A1"] = "VENDOR/ SUBCON"
    vendors["B1"] = "TRANSMITTAL NO."
    vendors["A2"] = "ACME"
    vendors["B2"] = "VTN-001"

    codes = wb.create_sheet("Status Codes")
    codes["A1"] = "ISSUE CODE"
    codes["B1"] = "REVIEW CODE FROM QatarEnergy"

    vendor_list = wb.create_sheet("VENDOR LIST")
    vendor_list["A1"] = "VENDOR"
    vendor_list["A2"] = "DANEM"

    if worked:
        _add_working_sheet(wb)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    wb.close()
    return path


#: What a hand-worked `QatarEnergy-TN WORKING` carries that the automation must
#: never copy: somebody's manual completion answers, and a CHECK STATUS the
#: received-document dump has not been built to produce.
WORKING_SHEET = "QatarEnergy-TN WORKING"
WORKING_MANUAL_VALUES: tuple[tuple[str, str, str], ...] = (
    # DOC IS REQUIRED SOW, DOC IDB COMPLETED STATUS, CHECK STATUS
    ("YES-MTL/DOC IDB", "COMPLETED", "NOT RECEIVED"),
    ("YES-FMTL/MTL/HIERARCHY/DOC IDB", "PENDING", "NOT RECEIVED"),
    ("NO", "NO NEED TO CHECK", "NOT RECEIVED"),
    ("", "", ""),
    ("YES-MTL/DOC IDB", "CANCELLED", "#N/A"),
)


def _add_working_sheet(wb) -> None:
    """A sheet the employee already made and worked on, by hand.

    Shaped like the real one - the automation columns at the working
    positions, filled in with a person's own conclusions. The exporter must
    leave every cell of it exactly as found and read none of it.
    """
    ws = wb.create_sheet(WORKING_SHEET)
    captions = list(HEADERS[:ANCHOR_COLUMN - 1]) + [
        "DOC  WITH REV", " DOC TYPE", "DOC IS REQUIRED SOW",
        "DOC IDB COMPLETED STATUS", "CHECK STATUS",
    ] + list(HEADERS[ANCHOR_COLUMN - 1:])
    for i, caption in enumerate(captions, start=1):
        ws.cell(row=HEADER_ROW, column=i, value=caption)

    for r, (values, manual) in enumerate(zip(DATA_ROWS, WORKING_MANUAL_VALUES),
                                         start=FIRST_DATA_ROW):
        head = list(values[:ANCHOR_COLUMN - 1])
        tail = list(values[ANCHOR_COLUMN - 1:])
        row = head + ["WORKED-BY-HAND", "MANUAL TYPE", *manual] + tail
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value or None)


def sample_rows() -> list[AutomationRow]:
    """Five-column answers for the four document rows of the fixture.

    The values are the ones the real engines produce for those document
    numbers (see `tests/integration/test_idb_pipeline.py`), written out here
    so the export tests assert against fixed text and do not depend on the
    rules workbook being present.

    Between them the four cover every shape the IDB column can take: required
    and therefore blank, out of scope, and an honest unknown.
    """
    return [
        # Required. DOC IDB COMPLETED STATUS is blank - a person must check it.
        AutomationRow(source_row=6, doc_with_rev="4391-MEWTP-2-13-0005-0",
                      doc_type="MDS", sow="YES-MTL/DOC IDB",
                      idb_status="", idb_source="NO_COMPLETION_SOURCE"),
        AutomationRow(source_row=7,
                      doc_with_rev="4391-M3UT-6-51-0007-001-A",
                      doc_type="MXB", sow="YES-FMTL/MTL/HIERARCHY/DOC IDB",
                      idb_status="", idb_source="NO_COMPLETION_SOURCE"),
        # Classified from `NOT REQUIRED-KEY DOC.WORDS`, which is itself the
        # statement that the document is out of scope.
        AutomationRow(source_row=8, doc_with_rev="4391-MG-WPR-0041-1",
                      doc_type="WEEKLY PROGRESS REPORT", sow="NO",
                      idb_status="NO NEED TO CHECK",
                      sow_source="NOT_REQUIRED_KEYWORDS",
                      idb_source="SOW_NOT_REQUIRED"),
        # Out of scope, so no check is due.
        AutomationRow(source_row=10, doc_with_rev="VEN-MEWTP-5-43-0011",
                      doc_type="OLD REV NOT SOW", sow="NO",
                      idb_status="NO NEED TO CHECK",
                      idb_source="SOW_NOT_REQUIRED"),
    ]
