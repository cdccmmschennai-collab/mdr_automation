"""Persisting an MDR submission and its results (Delivery Phase 2).

This is the service layer for persistence, and it is the only place that
composes repositories into one unit of work. It sits where the layering says it
should:

    API route  ->  submission_service  ->  repositories  ->  PostgreSQL
                            \\-> MDR engine / automation_service

**What this module does not do.** It does not upload anything, read an
uploaded file off a request, run the engine on the API's behalf, or generate a
download. Those are the upload/extract/automate/download workflows, and they
belong to later delivery phases. What is here is the persistence half: given an
`AutomationRun` that the existing engine already produced, store it in a way
that is still explainable a year later.

Each function takes an open `Session` and does not commit. The caller owns the
transaction - so recording a submission's rows and its summary either both
happen or neither does, rather than leaving a submission marked AUTOMATED with
no rows under it.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .. import __version__ as BACKEND_VERSION
from ..infrastructure.persistence.models import (
    MdrProcessingSummary, MdrSubmission, Plant, RuleSet,
)
from ..infrastructure.persistence.repositories import (
    DocumentRowRepository, PlantRepository, ProcessingSummaryRepository,
    RuleSetRepository, SubmissionRepository,
)
from .automation_service import AutomationRun
from .rule_set_service import file_digest, fingerprint_rules_workbook


def register_plant(session: Session, code: str, name: str) -> Plant:
    """Ensure a plant exists, and return it."""
    return PlantRepository(session).get_or_create(code, name)


def register_rule_set(session: Session,
                      rules_workbook: Optional[Path] = None,
                      version_label: Optional[str] = None) -> RuleSet:
    """Fingerprint the rules workbook and record it, or return the known row.

    Called before storing a result, so that the result has something to point
    at. Registering rules that are already known is a no-op returning the
    existing row - see `RuleSetRepository.register`.
    """
    fingerprint = fingerprint_rules_workbook(rules_workbook)
    return RuleSetRepository(session).register(fingerprint, version_label)


def record_upload(session: Session, *, plant: Plant, workbook: Path,
                  stored_path: str = "") -> MdrSubmission:
    """Record that a workbook arrived, and return the submission.

    The digest and byte size are taken from the file itself rather than from
    anything a caller claims about it: they are what make it possible, later,
    to say whether two submissions were the same file.

    This records an upload; it does not perform one. Receiving bytes over HTTP
    and deciding where they are stored is the upload workflow, a later phase -
    `stored_path` is whatever that phase will supply and is empty until then.
    """
    workbook = Path(workbook)
    return SubmissionRepository(session).add(
        plant_id=plant.id,
        source_filename=workbook.name,
        source_sha256=file_digest(workbook),
        source_byte_size=workbook.stat().st_size,
        stored_path=stored_path,
    )


def record_automation_run(session: Session, *, submission: MdrSubmission,
                          run: AutomationRun, rule_set: RuleSet,
                          ) -> MdrProcessingSummary:
    """Store one completed run: its rows, its summary, and its rule set.

    The submission is moved to EXTRACTED and then AUTOMATED, so the two
    timestamps reflect what actually happened rather than both being stamped at
    the end. `run.result.discovery` supplies what the workbook turned out to
    contain.

    Nothing is committed. If the caller's transaction fails after this returns,
    no half-stored submission survives.
    """
    discovery = run.result.discovery or {}
    SubmissionRepository(session).mark_extracted(
        submission,
        sheet_name=discovery.get("qe_sheet", "") or "",
        header_row=discovery.get("qe_header_row"),
        row_count=discovery.get("qe_data_rows"),
    )

    DocumentRowRepository(session).add_rows(
        submission.id, run.result.documents, run.rows)

    summary = ProcessingSummaryRepository(session).add(
        submission_id=submission.id,
        rule_set_id=rule_set.id,
        summary=run.summary(),
        engine_version=BACKEND_VERSION,
        discovery=discovery,
    )
    SubmissionRepository(session).mark_automated(submission)
    return summary


def submission_history(session: Session,
                       plant_id: uuid.UUID) -> list[MdrSubmission]:
    """Every submission a plant has ever made, oldest first.

    Exposed because it is the question the schema was shaped to answer: MDR #6,
    #7 and #8 side by side, each still carrying the rule set that produced it.
    """
    return SubmissionRepository(session).by_plant(plant_id)
