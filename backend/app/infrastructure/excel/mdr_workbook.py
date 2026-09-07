"""The MDR workbook adapter.

This module is the boundary. Everything the backend knows about *where* MDR
data sits in a spreadsheet - sheet names, header captions, the misspelling
'ORGINATOR' - lives here and nowhere else. It hands the engine and the pipeline
plain, named Python records.

Sheets and columns are still resolved by text, never by coordinate: see
`workbook_reader`. The workbook is opened read-only and is never written to.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .workbook_reader import SheetTable, read_table

# --------------------------------------------------------------- sheet naming

QE_SHEET = ("QatarEnergy-TN", "QatarEnergy TN", "QE-TN")
VENDOR_SHEET = ("TN FROM VENDORS", "TN FROM VENDOR")
STATUS_SHEET = ("Status Codes", "StatusCodes")

#: Headers used to score which row is the header row (not all are required).
QE_EXPECTED = ["DOCUMENT NO.", "REV", "DISCIPLINE", "DOCUMENT TITLE",
               "ISSUED STATUS IN PDMS", "LATEST/ NOT LATEST"]
VENDOR_EXPECTED = ["VENDOR/ SUBCON", "TRANSMITTAL NO.", "Vendor Document No.",
                   "PROJECT DOCUMENT/ DRAWING NO.", "REV", "PROJECT DOC NO."]
STATUS_EXPECTED = ["REVIEW CODE FROM QatarEnergy", "ISSUE CODE"]


# ---------------------------------------------------------------- source rows

@dataclass(frozen=True)
class DocumentSourceRow:
    """One QatarEnergy-TN data row, addressed by meaning rather than column."""

    source_row: int
    document_no: str = ""
    rev: str = ""
    issued_status_in_pdms: str = ""
    qe_status: str = ""
    document_title: str = ""
    discipline: str = ""
    originator: str = ""
    issued_date: str = ""
    workbook_latest_flag: str = ""
    remarks: str = ""
    vendor_tn_no: str = ""


@dataclass(frozen=True)
class VendorSourceRow:
    """One TN FROM VENDORS data row."""

    source_row: int
    vendor: str = ""
    transmittal_no: str = ""
    vendor_document_no: str = ""
    project_document_drawing_no: str = ""
    project_doc_no: str = ""
    rev: str = ""
    description: str = ""


@dataclass(frozen=True)
class SheetDiscovery:
    """What was found when a sheet was located."""

    sheet_name: str
    header_row: int
    row_count: int


# -------------------------------------------------------------------- adapter

class MdrWorkbookReader:
    """Read-only access to the three sheets Phase 1 consumes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    # -- Status Codes ------------------------------------------------------

    def read_status_code_rows(self) -> list[tuple]:
        """Raw cell rows of the 'Status Codes' sheet, for `StatusCodeBook`."""
        table = read_table(self.path, STATUS_SHEET, STATUS_EXPECTED)
        # The sheet's first data row sits directly under a title row, so the
        # whole data block is passed through; the loader skips the captions.
        return table.rows

    # -- QatarEnergy-TN ----------------------------------------------------

    def read_document_rows(self) -> tuple[list[DocumentSourceRow], SheetDiscovery]:
        table = read_table(self.path, QE_SHEET, QE_EXPECTED)

        c_doc = table.index("DOCUMENT NO.")
        c_rev = table.index("REV")
        c_issue = table.index("ISSUED STATUS IN PDMS")
        c_status = table.index("QatarEnergy/MG/TEN/TEB STATUS", required=False)
        c_title = table.index("DOCUMENT TITLE", required=False)
        c_disc = table.index("DISCIPLINE", required=False)
        # 'ORGINATOR' is the workbook's own spelling; the correct spelling is
        # accepted as a fallback so a corrected sheet keeps working.
        c_orig = table.index("ORGINATOR", "ORIGINATOR", required=False)
        c_date = table.index("ISSUED DATE to QE", required=False)
        c_latest = table.index("LATEST/ NOT LATEST", required=False)
        c_remarks = table.index("REMARKS", required=False)
        c_vendor_tn = table.index("SUBCON/VENDOR TN NO.", required=False)

        rows = [
            DocumentSourceRow(
                source_row=table.excel_row_number(i),
                document_no=table.value(row, c_doc),
                rev=table.value(row, c_rev),
                issued_status_in_pdms=table.value(row, c_issue),
                qe_status=table.value(row, c_status),
                document_title=table.value(row, c_title),
                discipline=table.value(row, c_disc),
                originator=table.value(row, c_orig),
                issued_date=table.value(row, c_date),
                workbook_latest_flag=table.value(row, c_latest),
                remarks=table.value(row, c_remarks),
                vendor_tn_no=table.value(row, c_vendor_tn),
            )
            for i, row in enumerate(table.rows)
        ]
        return rows, _discovery(table)

    # -- TN FROM VENDORS ---------------------------------------------------

    def read_vendor_rows(self) -> tuple[list[VendorSourceRow], SheetDiscovery]:
        table = read_table(self.path, VENDOR_SHEET, VENDOR_EXPECTED)

        c_vendor = table.index("VENDOR/ SUBCON", required=False)
        c_tn = table.index("TRANSMITTAL NO.", required=False)
        c_vdoc = table.index("Vendor Document No.", required=False)
        c_pdoc = table.index("PROJECT DOCUMENT/ DRAWING NO.", required=False)
        c_rev = table.index("REV", required=False)
        c_desc = table.index("Description", required=False)
        c_pdno = table.index("PROJECT DOC NO.", required=False)

        rows = [
            VendorSourceRow(
                source_row=table.excel_row_number(i),
                vendor=table.value(row, c_vendor),
                transmittal_no=table.value(row, c_tn),
                vendor_document_no=table.value(row, c_vdoc),
                project_document_drawing_no=table.value(row, c_pdoc),
                project_doc_no=table.value(row, c_pdno),
                rev=table.value(row, c_rev),
                description=table.value(row, c_desc),
            )
            for i, row in enumerate(table.rows)
        ]
        return rows, _discovery(table)


def _discovery(table: SheetTable) -> SheetDiscovery:
    return SheetDiscovery(sheet_name=table.name, header_row=table.header_row,
                          row_count=len(table.rows))
