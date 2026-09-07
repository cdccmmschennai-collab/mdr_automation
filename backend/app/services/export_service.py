"""Exporting a Phase 1 result to machine-readable artefacts.

Decides *what* is published and under which filename; the mechanics of writing
live in `infrastructure.filesystem.artifact_writer`.

Phases 1 and 2A emit JSON and CSV only. Excel MDR output is Phase 5 and is not
implemented here: nothing in this module writes an .xlsx file.
"""

from __future__ import annotations

from pathlib import Path

from ..domain.models.mdr_result import EngineResult
from ..engine.validation.doc_type import DocTypeReport
from ..engine.validation.latest import ValidationReport
from ..infrastructure.filesystem.artifact_writer import (
    public_fields, write_csv, write_json,
)

RESULT_JSON = "mdr_phase1_result.json"
DOCUMENTS_CSV = "documents.csv"
VENDOR_ROWS_CSV = "vendor_rows.csv"
EXCEPTIONS_CSV = "exceptions.csv"
VALIDATION_JSON = "validation_report.json"
DOC_TYPE_JSON = "doc_type_report.json"


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
