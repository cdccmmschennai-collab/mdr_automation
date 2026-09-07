"""Validation against ground truth.

The source workbook maintains its own 'LATEST/ NOT LATEST' column (L / NL),
which is the manual result this engine automates, so it doubles as ground truth.

A single agreement percentage would be misleading here, because some of the
workbook's own labels are stale: when a newer revision arrives, the previous
row keeps its 'L' until someone updates it. Disagreements are therefore
classified by root cause, and only genuine conflicts count against the engine.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from ...domain.enums.status_codes import RevisionStatus
from ...domain.models.document import DocumentRecord
from ...domain.models.mdr_result import EngineResult
from ..identity.grouping import group_by_identity

LABELLED = {"L", "NL"}


class Cause(str, Enum):
    """Root cause of an engine-vs-workbook disagreement."""

    #: A higher revision exists but the workbook never processed it, so the
    #: old row still carries 'L'. The engine is correct; the workbook is stale.
    STALE_HIGHER_REVISION_UNPROCESSED = "STALE_HIGHER_REVISION_UNPROCESSED"
    #: Two rows both carry 'L' - the earlier one was never flipped to 'NL'.
    STALE_DUPLICATE_LATEST_FLAG = "STALE_DUPLICATE_LATEST_FLAG"
    #: The workbook marks no row in the group as latest at all. This encodes
    #: "not an active deliverable" (renumbered / superseded / non-deliverable),
    #: a meaning the available columns do not express deterministically.
    #: Out of Phase 1 scope - reported, never guessed.
    WORKBOOK_MARKS_GROUP_INACTIVE = "WORKBOOK_MARKS_GROUP_INACTIVE"
    #: A real conflict the engine cannot explain. These are engine defects.
    GENUINE_CONFLICT = "GENUINE_CONFLICT"


#: Causes that do NOT indicate an engine error.
BENIGN_CAUSES = {
    Cause.STALE_HIGHER_REVISION_UNPROCESSED,
    Cause.STALE_DUPLICATE_LATEST_FLAG,
    Cause.WORKBOOK_MARKS_GROUP_INACTIVE,
}


@dataclass
class Disagreement:
    source_row: int
    document: str
    revision: str
    engine_status: str
    workbook_flag: str
    cause: str
    group: list = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "source_row": self.source_row,
            "document": self.document,
            "revision": self.revision,
            "engine": self.engine_status,
            "workbook": self.workbook_flag,
            "cause": self.cause,
            "group": self.group,
            "reason": self.reason,
        }


@dataclass
class ValidationReport:
    compared: int = 0
    agreements: int = 0
    disagreements: list[Disagreement] = field(default_factory=list)
    cause_counts: dict = field(default_factory=dict)
    unlabelled_rows: int = 0
    exception_rows: int = 0
    engine_status_counts: dict = field(default_factory=dict)

    @property
    def agreement_rate(self) -> float:
        """Raw agreement, counting every disagreement against the engine."""
        return self.agreements / self.compared if self.compared else 0.0

    @property
    def genuine_conflicts(self) -> list[Disagreement]:
        return [d for d in self.disagreements
                if d.cause == Cause.GENUINE_CONFLICT.value]

    @property
    def adjusted_agreement_rate(self) -> float:
        """Agreement over rows the engine is actually accountable for.

        Excludes rows whose workbook label is provably stale (a newer revision
        exists, or two rows both carry 'L') and rows where the workbook marks
        the whole group inactive - a business meaning Phase 1 does not model.
        This is NOT a claim that the engine is right on the excluded rows; see
        `cause_counts` for what was set aside and why.
        """
        if not self.compared:
            return 0.0
        benign = len(self.disagreements) - len(self.genuine_conflicts)
        denom = self.compared - benign
        return (self.agreements / denom) if denom else 0.0

    def to_dict(self) -> dict:
        return {
            "compared_rows": self.compared,
            "agreements": self.agreements,
            "disagreement_count": len(self.disagreements),
            "raw_agreement_rate": round(self.agreement_rate, 6),
            "adjusted_agreement_rate": round(self.adjusted_agreement_rate, 6),
            "genuine_conflicts": len(self.genuine_conflicts),
            "disagreement_causes": self.cause_counts,
            "unlabelled_rows_in_workbook": self.unlabelled_rows,
            "engine_exception_rows": self.exception_rows,
            "engine_status_counts": self.engine_status_counts,
            "disagreements": [d.to_dict() for d in self.disagreements],
        }


def _classify(rec: DocumentRecord, group: list[DocumentRecord],
              engine_latest: bool, flag: str) -> Cause:
    key = (rec.revision_band, rec.revision_rank)
    higher = [x for x in group if (x.revision_band, x.revision_rank) > key]
    higher_unlabelled = [x for x in higher
                         if (x.workbook_latest_flag or "").upper() not in LABELLED]
    labelled_l = [x for x in group if (x.workbook_latest_flag or "").upper() == "L"]

    if not engine_latest and flag == "L":
        if higher and len(higher_unlabelled) == len(higher):
            return Cause.STALE_HIGHER_REVISION_UNPROCESSED
        if len(labelled_l) > 1:
            return Cause.STALE_DUPLICATE_LATEST_FLAG
    if engine_latest and flag == "NL" and not labelled_l:
        return Cause.WORKBOOK_MARKS_GROUP_INACTIVE
    return Cause.GENUINE_CONFLICT


def validate_latest(result: EngineResult,
                    max_recorded: int = 1000) -> ValidationReport:
    """Compare engine latest/old decisions with the workbook's L/NL column."""
    report = ValidationReport()
    report.engine_status_counts = dict(
        Counter(d.revision_status for d in result.documents))

    groups = group_by_identity(result.documents)

    causes: Counter = Counter()
    for rec in result.documents:
        flag = (rec.workbook_latest_flag or "").strip().upper()

        if rec.revision_status in (RevisionStatus.EXCEPTION,
                                   RevisionStatus.AS_BUILT):
            report.exception_rows += 1
            continue
        if flag not in LABELLED:
            report.unlabelled_rows += 1
            continue

        report.compared += 1
        engine_latest = rec.revision_status == RevisionStatus.LATEST
        if engine_latest == (flag == "L"):
            report.agreements += 1
            continue

        cause = _classify(rec, groups[rec.document_identity], engine_latest, flag)
        causes[cause.value] += 1
        if len(report.disagreements) < max_recorded:
            report.disagreements.append(Disagreement(
                source_row=rec.source_row,
                document=rec.qatarenergy_document_no,
                revision=rec.revision,
                engine_status=rec.revision_status,
                workbook_flag=flag,
                cause=cause.value,
                group=sorted([g.revision, g.workbook_latest_flag or "(blank)"]
                             for g in groups[rec.document_identity]),
                reason=rec.reason,
            ))
    report.cause_counts = dict(causes)
    return report
