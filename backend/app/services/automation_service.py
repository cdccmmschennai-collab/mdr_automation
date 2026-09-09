"""Phase 2D orchestration: the five MDR automation columns for one workbook.

This is the application layer, and like every other service here it holds no
rule of its own. It runs the four engines in the order the business states
them and collects their verdicts into one `AutomationRow` per source row:

    Phase 1   identity + revision   -> DOC WITH REV
    Phase 2A  keyword classifier    -> DOC TYPE
    Phase 2B  SOW resolver          -> DOC IS REQUIRED SOW
    Phase 2C  IDB resolver          -> DOC IDB COMPLETED STATUS
    Phase 3B  (not implemented)     -> CHECK STATUS

Phases 1 and 2A already run inside `MdrEngine`, so their answers are read off
the `DocumentRecord`. Phases 2B and 2C are pure resolvers and are applied
here, each fed only the previous phase's verdict - the SOW resolver sees a DOC
TYPE and the keyword sheet that decided it, the IDB resolver sees a
`SowRequirement` and nothing else - so the chain stays flat and no stage can
reach around another for an input it is not entitled to.

The SOW resolver is given `doc_type_source` as well as `doc_type` because the
rules workbook states scope on two sheets, not one: `DOCUMENT TYPE` lists what
is required, and `NOT REQUIRED-KEY DOC.WORDS` lists what is not. Both are
Phase 2A output being carried forward, not a second classification - see
`engine.sow.resolver`.

**DOC IDB COMPLETED STATUS is left blank for every required document.** Phase
2C answers `TO BE CHECK` there, which is a correct statement that a check is
due; but the column records the *outcome* of the check, and no completion
source exists to state one. The blank is the instruction to go and look. See
`MANUAL_CHECK_REQUIRED` in `domain.models.automation`.

Nothing in this module opens a workbook for writing, knows a column letter, or
imports openpyxl. Turning these rows into a spreadsheet is
`infrastructure.excel.output_workbook`, and choosing where that spreadsheet
goes is `export_service`.

**No completion source, and no historical column, is consulted.** The IDB
resolver is called without a `recorded_outcome`, because Phase 2C implements
no completion source; the historical `DOC IDB COMPLETED STATUS` values in
`20260516_184-Transmittal Log (8).xlsx` are manual results and are not an
input to anything here. CHECK STATUS is left at its structural blank - see
`domain.models.automation`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from ..domain.models.automation import MANUAL_CHECK_REQUIRED, AutomationRow
from ..domain.models.document import DocumentRecord
from ..domain.models.idb import NO_COMPLETION_SOURCE, UNMAPPED
from ..domain.models.mdr_result import EngineResult
from ..engine.identity.normalisation import doc_with_rev
from ..engine.idb.resolver import IdbResolver
from ..engine.sow.resolver import SowResolver
from .idb_service import build_resolvers
from .mdr_pipeline import MdrEngine


def build_automation_rows(documents: Iterable[DocumentRecord],
                          sow_resolver: Optional[SowResolver],
                          idb_resolver: IdbResolver) -> list[AutomationRow]:
    """Resolve the five automation values for each document row.

    `sow_resolver` may be None - that is what `sow_service.build_resolver`
    returns when no rules workbook is available. Every SOW value is then
    empty and every IDB status `UNMAPPED`, which is the honest result of a run
    with no rules rather than a crash or a fabricated `NO`.
    """
    rows: list[AutomationRow] = []
    for doc in documents:
        requirement = (sow_resolver.resolve(doc.doc_type, doc.doc_type_source)
                       if sow_resolver is not None else None)
        # No `recorded_outcome`: Phase 2C implements no completion source, and
        # the historical column is never read as one.
        status = idb_resolver.resolve(requirement)

        rows.append(AutomationRow(
            source_row=doc.source_row,
            doc_with_rev=doc_with_rev(doc.qatarenergy_document_no,
                                      doc.revision_raw),
            doc_type=doc.doc_type,
            sow=requirement.sow if requirement is not None else "",
            idb_status=idb_cell(status),
            doc_type_rule=doc.doc_type_rule,
            sow_source=requirement.source if requirement is not None else "",
            idb_source=status.source,
        ))
    return rows


def idb_cell(status) -> str:
    """The DOC IDB COMPLETED STATUS value for one Phase 2C verdict.

    Phase 2C's three answers reach the column as two written values and one
    blank:

    * `NO NEED TO CHECK` - out of scope, so no check is due. A conclusion the
      SOW verdict fully supports, and it is written.
    * `UNMAPPED` - no scope verdict, so it is unknown whether a check is due.
      Written, because a rule gap that reads as blank is indistinguishable
      from a document waiting to be checked.
    * a check *is* due and no completion source has said how it went - blank,
      because the outcome is what the column records and nobody has recorded
      it. `status.status` is `TO BE CHECK` here; that is Phase 2C stating the
      requirement, not the outcome, and it is not an answer to write down.

    The provenance survives either way: `AutomationRow.idb_source` still says
    `NO_COMPLETION_SOURCE`, so a blank is never mistaken for an unresolved row.
    """
    if status.source == NO_COMPLETION_SOURCE:
        return MANUAL_CHECK_REQUIRED
    return status.status


@dataclass
class AutomationRun:
    """One Phase 2D run: the Phase 1 result, and the five-column rows."""

    result: EngineResult
    rows: list[AutomationRow] = field(default_factory=list)

    def summary(self) -> dict:
        """Counts an operator needs to see that the five columns are sane."""
        return {
            "rows": len(self.rows),
            "doc_with_rev_populated": sum(1 for r in self.rows if r.doc_with_rev),
            "doc_type_populated": sum(1 for r in self.rows if r.doc_type),
            "sow_populated": sum(1 for r in self.rows if r.sow),
            "sow_unresolved": sum(1 for r in self.rows if not r.sow),
            "idb_populated": sum(1 for r in self.rows if r.idb_status),
            "idb_unmapped": sum(1 for r in self.rows
                                if r.idb_status == UNMAPPED),
            # Blank by design: required documents awaiting a manual check.
            # Counted separately so the blanks are visible as a decision
            # rather than looking like rows the pipeline missed.
            "idb_manual_check_required": sum(
                1 for r in self.rows
                if not r.idb_status and r.idb_source == NO_COMPLETION_SOURCE),
            "check_status_populated": sum(1 for r in self.rows
                                          if r.check_status),
            "doc_type_counts": dict(Counter(r.doc_type for r in self.rows)),
            "sow_counts": dict(Counter(r.sow for r in self.rows)),
            "idb_counts": dict(Counter(r.idb_status for r in self.rows)),
        }


def run_automation(workbook: Path,
                   rules_workbook: Optional[Path] = None) -> AutomationRun:
    """Run Phases 1, 2A, 2B and 2C over `workbook` and return the five columns.

    The workbook is opened read-only by every reader involved and is never
    written to; producing the output file is a separate, explicit step.
    """
    engine = MdrEngine(workbook, rules_workbook)
    result = engine.run()
    sow_resolver, idb_resolver = build_resolvers(engine.rules_workbook)
    return AutomationRun(
        result=result,
        rows=build_automation_rows(result.documents, sow_resolver,
                                   idb_resolver),
    )
