"""The reference working-file adapter.

`QatarEnergy-TN WORKING` in `20260516_184-Transmittal Log (8).xlsx` is the
manually maintained sheet the tool automates. Its `DOC TYPE` column is Phase
2A's ground truth - read here, never written, and never fed back into the
classifier as an input.

Only the columns the DOC TYPE and SOW comparisons need are read.
`DOC IDB COMPLETED STATUS` (AN) and `CHECK STATUS` (AO) are later phases and
are deliberately not read at all.

`DOC IS REQUIRED SOW` (AM) is read, and read for one purpose only: it is
Phase 2B's *expected* answer. It reaches `engine.validation.sow` and stops
there. The SOW resolver's signature takes a DOC TYPE and nothing else, so
there is no path by which column AM can influence the value Phase 2B computes.

Opened read-only; never written to.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .workbook_reader import read_table

WORKING_SHEET = ("QatarEnergy-TN WORKING",)

#: Headers used to score which row is the header row.
WORKING_EXPECTED = ["DOCUMENT NO.", "REV", "DOCUMENT TITLE",
                    "LATEST/ NOT LATEST", "DOC WITH REV", "DOC TYPE",
                    "DOC IS REQUIRED SOW"]


@dataclass(frozen=True)
class ReferenceRow:
    """One `QatarEnergy-TN WORKING` row, addressed by meaning."""

    source_row: int
    document_no: str = ""
    rev: str = ""
    document_title: str = ""
    final_issue_code: str = ""
    latest_flag: str = ""
    doc_with_rev: str = ""
    #: Column AL - the manual DOC TYPE Phase 2A is validated against, and the
    #: DOC TYPE the Phase 2B comparison feeds to the SOW resolver.
    doc_type: str = ""
    #: Column AM - the manual DOC IS REQUIRED SOW. Phase 2B's expected answer,
    #: never an input to the resolver.
    reference_sow: str = ""


@dataclass(frozen=True)
class ReferenceDiscovery:
    sheet_name: str
    header_row: int
    row_count: int


class ReferenceWorkbookReader:
    """Read-only access to the reference working sheet."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    def read_working_rows(self) -> tuple[list[ReferenceRow], ReferenceDiscovery]:
        table = read_table(self.path, WORKING_SHEET, WORKING_EXPECTED)

        c_doc = table.index("DOCUMENT NO.")
        c_rev = table.index("REV")
        c_title = table.index("DOCUMENT TITLE")
        c_issue = table.index("FINAL ISSUE CODES", required=False)
        c_latest = table.index("LATEST/ NOT LATEST", required=False)
        c_docrev = table.index("DOC WITH REV", required=False)
        c_type = table.index("DOC TYPE")
        c_sow = table.index("DOC IS REQUIRED SOW", required=False)

        rows = [
            ReferenceRow(
                source_row=table.excel_row_number(i),
                document_no=table.value(row, c_doc),
                rev=table.value(row, c_rev),
                document_title=table.value(row, c_title),
                final_issue_code=table.value(row, c_issue),
                latest_flag=table.value(row, c_latest).upper(),
                doc_with_rev=table.value(row, c_docrev),
                doc_type=table.value(row, c_type),
                reference_sow=table.value(row, c_sow),
            )
            for i, row in enumerate(table.rows)
        ]
        return rows, ReferenceDiscovery(sheet_name=table.name,
                                        header_row=table.header_row,
                                        row_count=len(rows))
