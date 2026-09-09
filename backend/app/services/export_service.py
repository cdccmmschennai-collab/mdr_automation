"""Exporting a run's results to the artefacts a caller can use.

Decides *what* is published and under which filename; the mechanics of writing
live in `infrastructure.filesystem.artifact_writer` for the JSON and CSV
artefacts, and in `infrastructure.excel.output_workbook` for the Excel one.

Phases 1, 2A, 2B and 2C emit JSON and CSV. Phase 2D adds the employee-facing
workbook: a copy of the input file carrying the five automation columns. That
copy is written to the configured output directory under a new name, and this
module refuses any destination that resolves to the source - the employee's
own workbook is an input and stays one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from ..domain.models.automation import AutomationRow
from ..domain.models.mdr_result import EngineResult
from ..engine.validation.doc_type import DocTypeReport
from ..engine.validation.idb import IdbReport
from ..engine.validation.latest import ValidationReport
from ..engine.validation.sow import SowReport
from ..infrastructure.excel.output_workbook import (
    AutomatedWorkbookWriter, OutputWouldOverwriteSource, WorkbookWriteReport,
)
from ..infrastructure.filesystem.artifact_writer import (
    public_fields, write_csv, write_json,
)

RESULT_JSON = "mdr_phase1_result.json"
DOCUMENTS_CSV = "documents.csv"
VENDOR_ROWS_CSV = "vendor_rows.csv"
EXCEPTIONS_CSV = "exceptions.csv"
VALIDATION_JSON = "validation_report.json"
DOC_TYPE_JSON = "doc_type_report.json"
SOW_JSON = "sow_report.json"
IDB_JSON = "idb_report.json"
AUTOMATION_JSON = "automation_rows.json"

#: Appended to the input workbook's own stem, so the employee can see at a
#: glance which file the output came from. Deterministic: the same input in
#: the same output directory always produces the same path, which is what
#: keeps a re-run from littering the directory with copies.
AUTOMATED_WORKBOOK_SUFFIX = "_MDR_AUTOMATED.xlsx"


def result_payload(result: EngineResult) -> dict:
    """The full machine-readable Phase 1 result."""
    return {
        "summary": result.summary(),
        "discovery": result.discovery,
        "documents": [public_fields(d) for d in result.documents],
        "vendor_rows": [public_fields(v) for v in result.vendor_rows],
    }


def export_result(result: EngineResult, outdir: Path) -> list[Path]:
    """Write the JSON result and the three CSV views. Returns the paths."""
    outdir = Path(outdir)
    written = [
        outdir / RESULT_JSON,
        outdir / DOCUMENTS_CSV,
        outdir / VENDOR_ROWS_CSV,
        outdir / EXCEPTIONS_CSV,
    ]
    write_json(result_payload(result), written[0])
    write_csv(result.documents, written[1])
    write_csv(result.vendor_rows, written[2])
    write_csv(result.exceptions, written[3])
    return written


def export_validation_report(report: ValidationReport, outdir: Path) -> Path:
    """Write the ground-truth comparison report."""
    path = Path(outdir) / VALIDATION_JSON
    write_json(report.to_dict(), path)
    return path


def export_doc_type_report(report: DocTypeReport, outdir: Path) -> Path:
    """Write the Phase 2A DOC TYPE comparison report."""
    path = Path(outdir) / DOC_TYPE_JSON
    write_json(report.to_dict(), path)
    return path


def export_sow_report(report: SowReport, outdir: Path) -> Path:
    """Write the Phase 2B DOC IS REQUIRED SOW comparison report."""
    path = Path(outdir) / SOW_JSON
    write_json(report.to_dict(), path)
    return path


def export_idb_report(report: IdbReport, outdir: Path) -> Path:
    """Write the Phase 2C DOC IDB COMPLETED STATUS comparison report."""
    path = Path(outdir) / IDB_JSON
    write_json(report.to_dict(), path)
    return path


# ------------------------------------------------------- Phase 2D: the Excel

def automated_workbook_path(source: Path, outdir: Path) -> Path:
    """Where the automated copy of `source` goes."""
    return Path(outdir) / (Path(source).stem + AUTOMATED_WORKBOOK_SUFFIX)


def export_automated_workbook(source: Path, rows: Iterable[AutomationRow],
                              outdir: Path,
                              destination: Optional[Path] = None
                              ) -> WorkbookWriteReport:
    """Write the five-column workbook: a copy of `source`, plus the columns.

    `source` is opened, copied in memory and saved elsewhere; it is never
    written to, and a `destination` that resolves to it raises
    `OutputWouldOverwriteSource` rather than being silently redirected. That
    is the difference between a bug and a lost input file.
    """
    destination = destination or automated_workbook_path(source, outdir)
    if Path(destination).resolve() == Path(source).resolve():
        raise OutputWouldOverwriteSource(
            f"the automated workbook would overwrite its source: {source}")
    return AutomatedWorkbookWriter(source).write(rows, destination)


def export_automation_rows(rows: Iterable[AutomationRow], outdir: Path) -> Path:
    """Write the five automation values, with their provenance, as JSON.

    The machine-readable companion to the workbook: it records which rule
    decided each DOC TYPE and where each SOW and IDB verdict came from, which
    the spreadsheet has no room for.
    """
    path = Path(outdir) / AUTOMATION_JSON
    write_json({"rows": [r.to_dict() for r in rows]}, path)
    return path
