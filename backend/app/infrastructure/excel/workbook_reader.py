"""Read-only workbook discovery and loading.

Sheets are located by fuzzy name and columns by header text, so a shifted or
renamed column does not silently corrupt the result - it raises instead.

Every workbook here is opened with read_only=True; the engine never writes to
a source file. This is the ONLY module in the backend that imports openpyxl
for reading, so the business layers stay free of Excel implementation details.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from openpyxl import load_workbook

from ...engine.identity.normalisation import clean


def header_key(text: object) -> str:
    """Header comparison key: upper, alphanumeric only.

    Public because the output writer matches the same captions when deciding
    whether a workbook already carries an automation column, and the two must
    agree on what "the same header" means.
    """
    return re.sub(r"[^A-Z0-9]", "", clean(text).upper())


#: Internal shorthand, used throughout this module.
_key = header_key


class SheetNotFoundError(LookupError):
    """Raised when no sheet matches the requested name."""


class ColumnNotFoundError(LookupError):
    """Raised when a required column header is absent."""


@dataclass
class SheetTable:
    """A discovered sheet: its header row, column map and data rows."""

    name: str
    header_row: int
    columns: dict[str, int] = field(default_factory=dict)   # key -> 0-based index
    headers: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)         # data rows only
    first_data_row: int = 0                                 # 1-based Excel row
    #: 1-based Excel row number of each entry in `rows`. Wholly empty rows are
    #: dropped from `rows`, so position alone would drift past a spacer row -
    #: the `DOCUMENT TYPE` sheet has one directly under its header.
    row_numbers: list[int] = field(default_factory=list)

    def index(self, *header_names: str, required: bool = True) -> Optional[int]:
        """Resolve the 0-based column index for the first header that matches.

        Matching is exact on the normalised key, then prefix-based, so
        'REV' does not accidentally capture 'REVIEW CODE'.
        """
        for name in header_names:
            k = _key(name)
            if k in self.columns:
                return self.columns[k]
        for name in header_names:
            k = _key(name)
            for col_key, idx in self.columns.items():
                if col_key.startswith(k) and len(k) >= 4:
                    return idx
        if required:
            raise ColumnNotFoundError(
                f"none of {header_names!r} found in sheet {self.name!r}; "
                f"available headers: {self.headers}"
            )
        return None

    def value(self, row: tuple, idx: Optional[int]) -> str:
        if idx is None or idx >= len(row):
            return ""
        return clean(row[idx])

    def excel_row_number(self, i: int) -> int:
        """1-based Excel row number for data row i."""
        if 0 <= i < len(self.row_numbers):
            return self.row_numbers[i]
        return self.first_data_row + i


def find_sheet(workbook, *candidates: str) -> str:
    """Return the real sheet name matching any candidate (exact then contains)."""
    available = list(workbook.sheetnames)
    by_key = {_key(n): n for n in available}
    for cand in candidates:
        if _key(cand) in by_key:
            return by_key[_key(cand)]
    for cand in candidates:
        ck = _key(cand)
        for name in available:
            if ck and ck in _key(name):
                return name
    raise SheetNotFoundError(
        f"no sheet matching {candidates!r}; available: {available}"
    )


def detect_header_row(ws, expected: Sequence[str], max_scan: int = 15) -> int:
    """Find the header row by scoring the first `max_scan` rows.

    Returns the 1-based row number whose cells cover the most expected headers.
    """
    wanted = {_key(e) for e in expected if e}
    best_row, best_score = 1, -1
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan,
                                         values_only=True), start=1):
        keys = {_key(v) for v in row if v is not None and clean(v)}
        score = sum(1 for w in wanted if any(k == w or k.startswith(w) for k in keys))
        if score > best_score:
            best_row, best_score = i, score
    if best_score <= 0:
        raise ColumnNotFoundError(
            f"could not locate a header row in {ws.title!r} using {list(expected)!r}"
        )
    return best_row


def read_table(path: Path, sheet_candidates: Sequence[str],
               expected_headers: Sequence[str]) -> SheetTable:
    """Load one sheet into a SheetTable. Opens the workbook read-only."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        name = find_sheet(wb, *sheet_candidates)
        ws = wb[name]
        header_row = detect_header_row(ws, expected_headers)

        headers: list[str] = []
        columns: dict[str, int] = {}
        for row in ws.iter_rows(min_row=header_row, max_row=header_row,
                                values_only=True):
            for idx, cell in enumerate(row):
                text = clean(cell)
                headers.append(text)
                k = _key(text)
                if k and k not in columns:      # first occurrence wins
                    columns[k] = idx

        rows: list[tuple] = []
        row_numbers: list[int] = []
        for n, r in enumerate(ws.iter_rows(min_row=header_row + 1,
                                           values_only=True),
                              start=header_row + 1):
            if any(c is not None and clean(c) for c in r):
                rows.append(r)
                row_numbers.append(n)

        return SheetTable(name=name, header_row=header_row, columns=columns,
                          headers=headers, rows=rows,
                          first_data_row=header_row + 1,
                          row_numbers=row_numbers)
    finally:
        wb.close()


def describe_workbook(path: Path) -> dict:
    """Discovery summary: sheets, dimensions and detected headers."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        out = {"path": str(path), "sheets": []}
        for ws in wb.worksheets:
            out["sheets"].append({
                "name": ws.title,
                "state": ws.sheet_state,
                "max_row": ws.max_row,
                "max_column": ws.max_column,
            })
        return out
    finally:
        wb.close()
