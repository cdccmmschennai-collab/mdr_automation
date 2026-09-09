"""Writing the five-column MDR workbook (Phase 2D).

This is the only module in the backend that opens a workbook for *writing*.
Like `workbook_reader` on the read side it is the boundary: sheet names,
column letters, styles and openpyxl live here, and the values it writes arrive
as `AutomationRow` objects that were decided elsewhere. No DOC TYPE keyword,
no SOW rule and no IDB rule appears below.

What it produces
----------------
A copy of the employee's own workbook, saved under a new name, with exactly
one sheet added:

    QatarEnergy-TN            unchanged, exactly as the employee sent it
    QatarEnergy-TN Automated  the same rows, plus the five automation columns
    TN FROM VENDORS           unchanged
    Status Codes              unchanged
    VENDOR LIST               unchanged
    QatarEnergy-TN WORKING    unchanged, *if the employee had already made one*

`QatarEnergy-TN` is always the source of the data, and `QatarEnergy-TN
Automated` is always the only sheet written. An input that already carries a
hand-worked `QatarEnergy-TN WORKING` is treated no differently: that sheet is
never read for its answers, never used as the output, and never touched. Its
DOC IDB COMPLETED STATUS values are somebody's manual work, not an input to
anything here.

Where the five columns go
-------------------------
Where `QatarEnergy-TN WORKING` puts them: immediately before `QATARENERGY
SIGNED / NOT SIGNED`, so the sheet reads AJ, then the five automation columns,
then the three trailing columns the source sheet ends with. That is an
*insertion*, not an append - the trailing columns shift right, and with them
their widths, their merged ranges, and any conditional format or validation
that reaches them.

The anchor is found by header text like every other column in this package, so
a workbook whose trailing columns differ still works; if no anchor caption is
present the columns are appended after the last one in use, which is the only
sensible place left. Columns are matched by caption too, so a workbook that
already carries one of the five has that column updated rather than
duplicated.

The source workbook is opened once, in memory, and saved to the destination.
`export_service` refuses a destination equal to the source; this module
additionally refuses it, because "never write over the employee's input" is
worth stating twice.

What openpyxl cannot carry
--------------------------
`Workbook.copy_worksheet` copies cells, styles, dimensions, merged ranges,
margins and page setup, but not the sheet view, auto-filter, conditional
formats or data validations - those are copied explicitly below.
`Worksheet.insert_cols` moves cells and their styles but updates none of the
sheet-level ranges, so column widths, merged ranges, conditional formats, data
validations, the auto-filter and the frozen pane are all shifted explicitly by
`_insert_columns`. Charts, images and pivot tables are not copied onto the
*new* sheet by openpyxl at all; they survive on the original sheets, which are
untouched. Formula cells keep their formulas and lose their cached values, so
Excel recalculates them when the employee opens the file.
"""

from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
from openpyxl.worksheet.cell_range import CellRange, MultiCellRange

from ...domain.models.automation import (
    AUTOMATION_COLUMNS, CHECK_STATUS, DOC_IDB_COMPLETED_STATUS,
    DOC_IS_REQUIRED_SOW, DOC_TYPE, DOC_WITH_REV, AutomationRow,
)
from ...engine.identity.normalisation import clean
from .mdr_workbook import QE_EXPECTED, QE_SHEET
from .workbook_reader import detect_header_row, find_sheet, header_key

#: The sheet the automation writes into. Named after the sheet it mirrors, so
#: the employee can see at a glance which source sheet it belongs to.
AUTOMATED_SHEET = "QatarEnergy-TN Automated"

#: Sheets that belong to the employee and are never written to, whatever they
#: contain. Listed for the report and for the tests to assert against; the
#: writer touches no sheet but `AUTOMATED_SHEET` regardless.
PRESERVED_SHEETS: tuple[str, ...] = (
    "QatarEnergy-TN", "TN FROM VENDORS", "Status Codes", "VENDOR LIST",
    "QatarEnergy-TN WORKING",
)

#: The caption the five columns are inserted *before*, taken from
#: `QatarEnergy-TN WORKING`: its automation block sits between `(PREPARED /NOT
#: PREPARED BY MEDGULF)` and `QATARENERGY SIGNED / NOT SIGNED`. Several
#: spellings are accepted because the caption is hand-typed.
INSERT_BEFORE: tuple[str, ...] = (
    "QATARENERGY SIGNED / NOT SIGNED",
    "QATARENERGY SIGNED / NOT SIGNE",
    "QATARENERGY SIGNED",
)

#: Width for each newly created automation column, from the working sheet's
#: own column dimensions where it states one. Existing columns keep the width
#: they had.
COLUMN_WIDTHS: dict[str, float] = {
    DOC_WITH_REV: 38.71,                    # AK of QatarEnergy-TN WORKING
    DOC_TYPE: 26.0,
    DOC_IS_REQUIRED_SOW: 22.0,
    DOC_IDB_COMPLETED_STATUS: 26.0,         # AN of QatarEnergy-TN WORKING
    CHECK_STATUS: 18.0,
}

#: The fill `QatarEnergy-TN WORKING` gives the five captions, so the automation
#: block is as visible in the generated sheet as in the hand-made one. Applied
#: over the sheet's own header style - font, border and alignment still come
#: from the neighbouring captions, so only the colour marks the block out.
HEADER_FILL_RGB = "FF00B050"


class OutputWouldOverwriteSource(ValueError):
    """Raised when a destination would write over the source workbook."""


@dataclass
class WorkbookWriteReport:
    """What the writer did, for the CLI to print and the tests to assert."""

    source: Path
    destination: Path
    source_sheet: str
    automated_sheet: str
    header_row: int
    #: Caption -> column letter, for the five automation columns.
    columns: dict[str, str] = field(default_factory=dict)
    #: Captions that already existed in the source sheet and were updated in
    #: place rather than created.
    reused_columns: tuple[str, ...] = ()
    sheet_names: tuple[str, ...] = ()
    data_rows: int = 0
    rows_written: int = 0
    rows_outside_sheet: tuple[int, ...] = ()
    check_status_cells_written: int = 0
    #: The caption the block was inserted before, empty when it was appended
    #: because the sheet has no anchor caption.
    inserted_before: str = ""
    #: How many columns were inserted, and at which 1-based index.
    inserted_columns: int = 0
    inserted_at: int = 0
    #: Sheets the writer left exactly as it found them.
    untouched_sheets: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "source": str(self.source),
            "destination": str(self.destination),
            "source_sheet": self.source_sheet,
            "automated_sheet": self.automated_sheet,
            "header_row": self.header_row,
            "columns": dict(self.columns),
            "reused_columns": list(self.reused_columns),
            "sheet_names": list(self.sheet_names),
            "untouched_sheets": list(self.untouched_sheets),
            "data_rows": self.data_rows,
            "rows_written": self.rows_written,
            "rows_outside_sheet": list(self.rows_outside_sheet),
            "check_status_cells_written": self.check_status_cells_written,
            "inserted_before": self.inserted_before,
            "inserted_columns": self.inserted_columns,
            "inserted_at": self.inserted_at,
        }


# ------------------------------------------------- shifting a sheet sideways

def _shift_range(ref: str, at: int, count: int) -> str:
    """Move or widen one A1 range for `count` columns inserted before `at`.

    Three cases, and the middle one is the one openpyxl gets wrong: a range
    that *starts* left of the insertion and *ends* at or right of it is
    stretched, not moved. `QatarEnergy-TN`'s `AJ1:AK2` title merge is exactly
    that shape, and the hand-made working sheet stretched it too - it reads
    `AJ1:AR2` there.
    """
    cr = CellRange(ref)
    if cr.min_col >= at:
        cr.shift(col_shift=count)
    elif cr.max_col >= at:
        cr.expand(right=count)
    return str(cr)


def _shift_multi(sqref: object, at: int, count: int) -> str:
    """`_shift_range` over a space-separated multi-range (a CF/DV `sqref`)."""
    return " ".join(_shift_range(part, at, count)
                    for part in str(sqref).split() if part)


def _insert_columns(ws, at: int, count: int) -> None:
    """Insert `count` empty columns before column `at`, carrying the sheet with them.

    `Worksheet.insert_cols` moves the cells and their styles and stops there;
    everything a sheet holds *about* a column is left pointing at the old
    index. Each of those is moved here, in the order a reader would check
    them: widths, merges, conditional formats, validations, the filter and the
    frozen pane.
    """
    if count <= 0:
        return

    # Captured before the move: `insert_cols` relocates the MergedCell
    # placeholders, after which `unmerge_cells` can no longer find them.
    merges = [str(r) for r in ws.merged_cells.ranges]

    ws.insert_cols(at, count)

    # Column widths, hidden flags and outline levels.
    moved = {}
    for letter, dim in list(ws.column_dimensions.items()):
        index = column_index_from_string(letter)
        if index < at:
            continue
        del ws.column_dimensions[letter]
        dim.min = dim.max = index + count
        moved[get_column_letter(index + count)] = dim
    for letter, dim in moved.items():
        ws.column_dimensions[letter] = dim

    # Merged ranges: the ones spanning the insertion point are widened. The
    # refs are replaced wholesale rather than un/re-merged, because the cells
    # themselves already travelled with `insert_cols` - only the ranges
    # describing them are stale.
    ws.merged_cells = MultiCellRange(
        [CellRange(_shift_range(ref, at, count)) for ref in merges])

    # Conditional formats: rebuilt, because the collection is keyed by range.
    rules = [(str(cf.sqref), [copy(r) for r in cf.rules])
             for cf in ws.conditional_formatting]
    if rules:
        ws.conditional_formatting = type(ws.conditional_formatting)()
        for sqref, cf_rules in rules:
            for rule in cf_rules:
                ws.conditional_formatting.add(_shift_multi(sqref, at, count),
                                              rule)

    # Data validations.
    for dv in ws.data_validations.dataValidation:
        dv.sqref = _shift_multi(dv.sqref, at, count)

    # The auto-filter, and the frozen pane if it splits right of the insert.
    if ws.auto_filter.ref:
        ws.auto_filter.ref = _shift_range(ws.auto_filter.ref, at, count)
    if ws.freeze_panes:
        letter, row = coordinate_from_string(ws.freeze_panes)
        if column_index_from_string(letter) >= at:
            ws.freeze_panes = (
                f"{get_column_letter(column_index_from_string(letter) + count)}"
                f"{row}")


def _text(value: object) -> str:
    """Cell presentation: whitespace collapsed, upper case.

    Upper case throughout, to match the workbook's own house style - every
    caption and every business value in `QatarEnergy-TN` is upper case. This
    is presentation only; the engines' verdicts are already upper case and
    nothing here changes which verdict was reached.
    """
    return clean(value).upper()


class AutomatedWorkbookWriter:
    """Copies an MDR workbook and adds the five-column automation sheet."""

    def __init__(self, source: Path,
                 sheet_candidates: tuple[str, ...] = QE_SHEET,
                 expected_headers: tuple[str, ...] = tuple(QE_EXPECTED),
                 automated_sheet: str = AUTOMATED_SHEET):
        self.source = Path(source)
        if not self.source.is_file():
            raise FileNotFoundError(self.source)
        self.sheet_candidates = sheet_candidates
        self.expected_headers = expected_headers
        self.automated_sheet = automated_sheet

    # ------------------------------------------------------------------ API

    def write(self, rows: Iterable[AutomationRow],
              destination: Path) -> WorkbookWriteReport:
        """Write the automated copy to `destination` and report what was done."""
        destination = Path(destination)
        if destination.resolve() == self.source.resolve():
            raise OutputWouldOverwriteSource(
                f"refusing to write the automated workbook over its own "
                f"source: {self.source}")

        by_row = {r.source_row: r for r in rows}

        # Not read_only: the sheet has to be copied and added to. Not
        # data_only either, so the 131,558 formulas survive as formulas.
        wb = load_workbook(self.source)
        try:
            source_name = find_sheet(wb, *self.sheet_candidates)
            src = wb[source_name]
            header_row = detect_header_row(src, self.expected_headers)

            dst = self._copy_sheet(wb, src)
            columns, reused, placement = self._resolve_columns(dst, header_row)
            self._write_headers(dst, header_row, columns, reused)
            written, outside = self._write_rows(dst, header_row, columns, by_row)

            destination.parent.mkdir(parents=True, exist_ok=True)
            wb.save(destination)

            return WorkbookWriteReport(
                source=self.source, destination=destination,
                source_sheet=source_name, automated_sheet=dst.title,
                header_row=header_row,
                columns={c: get_column_letter(columns[c])
                         for c in AUTOMATION_COLUMNS},
                reused_columns=reused,
                sheet_names=tuple(wb.sheetnames),
                untouched_sheets=tuple(n for n in wb.sheetnames
                                       if n != dst.title),
                data_rows=max(dst.max_row - header_row, 0),
                rows_written=written, rows_outside_sheet=outside,
                # Structurally zero: `_write_rows` never touches the column.
                check_status_cells_written=0,
                inserted_before=placement[0],
                inserted_at=placement[1],
                inserted_columns=placement[2],
            )
        finally:
            wb.close()

    # ------------------------------------------------------------- internals

    def _copy_sheet(self, wb, src):
        """Duplicate `src` as the automation sheet, carrying what openpyxl skips.

        The copy is always taken from `QatarEnergy-TN`. An input that already
        carries a hand-worked `QatarEnergy-TN WORKING` is not read here and not
        written to: it keeps its position, its data and its manual completion
        values, and the automated sheet is built from the original data beside
        it.
        """
        if self.automated_sheet in wb.sheetnames:
            # A re-run over an already-automated workbook replaces the sheet
            # rather than accumulating 'QatarEnergy-TN Automated1', ...2.
            # Only ever this sheet: no other name is deleted, renamed or moved.
            del wb[self.automated_sheet]

        dst = wb.copy_worksheet(src)
        dst.title = self.automated_sheet
        dst.sheet_state = src.sheet_state

        # copy_worksheet leaves these behind; they are what make the sheet
        # usable rather than merely correct.
        dst.views = deepcopy(src.views)      # freeze panes, zoom, gridlines
        dst.auto_filter.ref = src.auto_filter.ref
        for cf in src.conditional_formatting:
            for rule in cf.rules:
                dst.conditional_formatting.add(str(cf.sqref), copy(rule))
        for dv in src.data_validations.dataValidation:
            dst.add_data_validation(deepcopy(dv))

        # Last in the book, so every sheet the employee sent keeps the
        # position it arrived in and the new one is plainly the addition.
        wb.move_sheet(dst, offset=len(wb.sheetnames) - 1 - wb.index(dst))
        return dst

    def _resolve_columns(self, ws, header_row: int
                         ) -> tuple[dict[str, int], tuple[str, ...],
                                    tuple[str, int, int]]:
        """Map each automation caption to a 1-based column index, inserting room.

        A caption already present in the header row keeps its column - the
        cells are updated, never duplicated into a second column of the same
        name, and no space is inserted for it.

        The rest are inserted as one contiguous block immediately before
        `INSERT_BEFORE`, which is where `QatarEnergy-TN WORKING` puts them. A
        sheet with no anchor caption gets the block appended after its last
        column instead - the columns still exist and still carry their values,
        which matters more than their position on a sheet that is not shaped
        like the working one.

        Returns the column map, the reused captions, and (anchor caption,
        insert index, number of columns inserted) for the report.
        """
        existing = self._header_index(ws, header_row)
        missing = [c for c in AUTOMATION_COLUMNS
                   if header_key(c) not in existing]
        reused = tuple(c for c in AUTOMATION_COLUMNS
                       if header_key(c) in existing)

        anchor, at = self._anchor(existing, ws.max_column + 1)
        if missing:
            _insert_columns(ws, at, len(missing))
            # Reused columns to the right of the insertion moved with it.
            existing = self._header_index(ws, header_row)

        columns: dict[str, int] = {}
        nxt = at
        for caption in AUTOMATION_COLUMNS:
            found = existing.get(header_key(caption))
            if found is not None and caption in reused:
                columns[caption] = found
            else:
                columns[caption] = nxt
                nxt += 1
        return columns, reused, (anchor, at, len(missing))

    @staticmethod
    def _header_index(ws, header_row: int) -> dict[str, int]:
        """Header key -> 1-based column, first occurrence winning."""
        index: dict[str, int] = {}
        for cell in ws[header_row]:
            k = header_key(cell.value)
            if k and k not in index:
                index[k] = cell.column
        return index

    @staticmethod
    def _anchor(existing: dict[str, int], fallback: int) -> tuple[str, int]:
        """Where the block goes: before the anchor caption, else at `fallback`."""
        for caption in INSERT_BEFORE:
            found = existing.get(header_key(caption))
            if found is not None:
                return caption, found
        return "", fallback

    def _write_headers(self, ws, header_row: int, columns: dict[str, int],
                       reused: tuple[str, ...]) -> None:
        """Write the five captions, styled like the sheet's own headers.

        The style is the neighbouring captions' own - font, size, border,
        alignment and number format - with the working sheet's green fill on
        top, which is the one thing it does differently from the columns
        beside it. A caption that already existed keeps the style it had; the
        employee put it there.
        """
        template = self._header_template(ws, header_row, columns)
        for caption in AUTOMATION_COLUMNS:
            col = columns[caption]
            cell = ws.cell(row=header_row, column=col)
            cell.value = caption                       # already upper case
            if caption in reused:
                continue
            if template is not None:
                cell._style = copy(template._style)
            cell.fill = PatternFill("solid", fgColor=HEADER_FILL_RGB)
            ws.column_dimensions[get_column_letter(col)].width = \
                COLUMN_WIDTHS[caption]

    @staticmethod
    def _header_template(ws, header_row: int, columns: dict[str, int]):
        """A header cell of the source sheet to copy the house style from.

        The right-most caption that is not one of ours: it carries the same
        font, fill and border as every other header on the row, so the new
        captions look like the ones beside them rather than like a new theme.
        """
        ours = set(columns.values())
        for cell in reversed(list(ws[header_row])):
            if cell.column not in ours and clean(cell.value):
                return cell
        return None

    @staticmethod
    def _data_template(ws, header_row: int, columns: dict[str, int]):
        """A populated data cell, to copy the body style from."""
        ours = set(columns.values())
        for row in ws.iter_rows(min_row=header_row + 1,
                                max_row=min(header_row + 20, ws.max_row)):
            for cell in row:
                if cell.column not in ours and cell.has_style:
                    return cell
        return None

    def _write_rows(self, ws, header_row: int, columns: dict[str, int],
                    by_row: dict[int, AutomationRow]
                    ) -> tuple[int, tuple[int, ...]]:
        """Write four values per row. CHECK STATUS is never touched.

        Rows are addressed by their own Excel row number, which the reader
        carried through the whole pipeline on `DocumentRecord.source_row`, so
        a row the pipeline skipped - a spacer, a row with no DOCUMENT NO. -
        simply keeps five empty cells rather than shifting its neighbours'
        answers onto it.
        """
        template = self._data_template(ws, header_row, columns)
        # CHECK STATUS is excluded here and nowhere reinstated: it is the
        # written expression of `CHECK_STATUS_NOT_EVALUATED`. It is still
        # *styled* like its neighbours, so the employee sees an empty column
        # of the sheet rather than a hole in the borders - but no value, ever.
        written_columns = [c for c in AUTOMATION_COLUMNS if c != CHECK_STATUS]

        written = 0
        outside: list[int] = []
        for source_row, row in sorted(by_row.items()):
            if source_row <= header_row:
                outside.append(source_row)
                continue
            values = dict(zip(AUTOMATION_COLUMNS, row.values))
            for caption in AUTOMATION_COLUMNS:
                cell = ws.cell(row=source_row, column=columns[caption])
                if caption in written_columns:
                    # A blank DOC IDB COMPLETED STATUS is a decision, not a
                    # missing write: `MANUAL_CHECK_REQUIRED`.
                    cell.value = _text(values[caption]) or None
                if template is not None:
                    cell._style = copy(template._style)
            written += 1
        return written, tuple(outside)


def read_automation_columns(path: Path, sheet: str = AUTOMATED_SHEET,
                            expected_headers: Optional[tuple[str, ...]] = None
                            ) -> tuple[int, dict[str, str], list[dict[str, str]]]:
    """Read the five automation columns back out of a generated workbook.

    Used to validate the artefact that was actually written, rather than the
    objects that were in memory when it was written. Returns the header row,
    the caption -> column-letter map, and one dict per data row.
    """
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        name = find_sheet(wb, sheet)
        ws = wb[name]
        headers = expected_headers or tuple(QE_EXPECTED)
        header_row = detect_header_row(ws, headers)

        index: dict[str, int] = {}
        for row in ws.iter_rows(min_row=header_row, max_row=header_row,
                                values_only=True):
            for i, value in enumerate(row):
                k = header_key(value)
                for caption in AUTOMATION_COLUMNS:
                    if k == header_key(caption) and caption not in index:
                        index[caption] = i

        out: list[dict[str, str]] = []
        for n, row in enumerate(ws.iter_rows(min_row=header_row + 1,
                                             values_only=True),
                                start=header_row + 1):
            record = {caption: (clean(row[i]) if i < len(row) else "")
                      for caption, i in index.items()}
            if any(record.values()):
                record["source_row"] = n
                out.append(record)
        letters = {c: get_column_letter(i + 1) for c, i in index.items()}
        return header_row, letters, out
    finally:
        wb.close()
