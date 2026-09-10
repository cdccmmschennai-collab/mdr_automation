"""The product workflow: upload -> extract -> automate -> summary (Phase 3).

This is the application layer behind `/api/v1/mdr`. Each function here is one
workflow step, owns one transaction, and composes what already exists:

    API route  ->  workflow_service  ->  repositories        ->  PostgreSQL
                          |-> infrastructure.storage         (the workbook)
                          |-> services.mdr_pipeline.MdrEngine
                          |-> services.automation_service    (the engine)
                          `-> services.rule_set_service      (which rules)

No MDR rule lives here. Extraction is `MdrEngine.run()`, exactly as the CLI
runs it; automation is `run_automation()`, exactly as `--excel` runs it. The
rows that reach the database are the `DocumentRecord`s and `AutomationRow`s
those produce, mapped by the existing repository. What this module adds is the
sequencing, the state checks, the transaction boundaries and the failure
bookkeeping - the things an HTTP workflow needs that a CLI run does not.

**State.** The lifecycle is `domain.enums.lifecycle` unchanged:

    UPLOADED -> EXTRACTED -> AUTOMATED
        \\           \\
         `-----------`--> FAILED

Processing is synchronous, so there is no in-flight state to record: a
request either moves the submission to the next status or to FAILED before it
returns. A step is accepted only from the status directly before it. Calling
it again is refused with `InvalidSubmissionState` (HTTP 409), which is what
keeps `unique(submission_id, source_row)` and the one-summary-per-submission
constraint from ever being tested by a repeat call. FAILED is terminal in this
phase: the workbook is re-uploaded as a new submission, which keeps the failed
one on record.

**Transactions.** Every write of a step happens in one `session_scope`. If
anything in the step raises - the workbook, the engine, or PostgreSQL - the
transaction rolls back, so no rows or summary survive without the status that
says they are there. The FAILED status and its reason are then written in a
second, separate transaction: they must survive precisely when the first one
did not.

**Errors.** Every exception a route needs to translate is a `WorkflowError`
subclass defined here, carrying a message written for the client. Anything
else that escapes is a defect and the route reports it as a 500 without
forwarding its text.
"""

from __future__ import annotations

import hashlib
import io
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from .. import __version__ as BACKEND_VERSION
from ..core.config import Settings, settings as default_settings
from ..domain.enums.lifecycle import SubmissionStatus
from ..infrastructure.excel.mdr_workbook import probe_document_sheet
from ..infrastructure.excel.workbook_reader import (
    ColumnNotFoundError, SheetNotFoundError, WorkbookUnreadableError,
)
from ..infrastructure.persistence.database import session_scope
from ..infrastructure.persistence.models import (
    MdrProcessingSummary, MdrSubmission, Plant, RuleSet,
)
from ..infrastructure.persistence.repositories import (
    DocumentRowRepository, PlantRepository, ProcessingSummaryRepository,
    SubmissionRepository,
)
from ..infrastructure.storage import LocalWorkbookStorage, WorkbookStorage
from .automation_service import run_automation
from .mdr_pipeline import MdrEngine
from .submission_service import register_rule_set

log = logging.getLogger(__name__)

#: Extensions the engine's reader can open. openpyxl reads both.
SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm")

#: A failure reason is stored verbatim, but bounded: a driver error that
#: quotes a 1000-parameter statement is not more useful for being complete.
_MAX_REASON_LENGTH = 1000

#: The exceptions that mean "this workbook cannot be processed" as opposed to
#: "something went wrong processing it". They are the client's problem to fix
#: and are reported as such (HTTP 422); everything else is a 500.
_WORKBOOK_ERRORS = (WorkbookUnreadableError, SheetNotFoundError,
                    ColumnNotFoundError)

#: `EngineResult.discovery` entries that are server filesystem paths. The
#: summary exposes `discovery`, and the submission already records the source
#: filename and the rule set the rules filename, so the paths add nothing a
#: client should see and are not persisted.
_DISCOVERY_PATHS = ("workbook", "rules_workbook")


# ------------------------------------------------------------------ errors

class WorkflowError(Exception):
    """Base for every error a route translates. `str(exc)` is client-safe."""


class SubmissionNotFound(WorkflowError):
    """No submission has this id."""


class PlantNotFound(WorkflowError):
    """The upload named a plant that is not registered."""


class InvalidUpload(WorkflowError):
    """The upload is not an MDR workbook the engine can read."""


class UploadTooLarge(WorkflowError):
    """The upload exceeds `settings.max_upload_bytes`."""


class InvalidSubmissionState(WorkflowError):
    """The submission is not in the status this step starts from."""


class RulesUnavailable(WorkflowError):
    """No rules workbook exists to fingerprint, so no result can be recorded."""


class ProcessingFailed(WorkflowError):
    """A step failed and the submission has been marked FAILED.

    `client_error` says whether the cause was the workbook (True - the client
    can fix it by uploading a different file) or the server (False).
    """

    def __init__(self, message: str, *, client_error: bool):
        super().__init__(message)
        self.client_error = client_error


# ----------------------------------------------------------------- results

@dataclass(frozen=True)
class AutomateOutcome:
    """What `automate_submission` hands back: the submission as it now stands,
    the summary written for it, and the rule set that summary points at."""

    submission: MdrSubmission
    summary: MdrProcessingSummary
    rule_set: RuleSet


@dataclass(frozen=True)
class SubmissionSummary:
    """Everything `GET /summary` reports, read in one transaction.

    `summary` and `rule_set` are None until the submission is AUTOMATED. A
    submission that is UPLOADED, EXTRACTED or FAILED still has a summary page
    - its status, its timestamps and its failure reason are the summary.
    """

    submission: MdrSubmission
    plant: Plant
    summary: Optional[MdrProcessingSummary]
    rule_set: Optional[RuleSet]


# ------------------------------------------------------------------ helpers

def _storage(settings: Settings,
             storage: Optional[WorkbookStorage]) -> WorkbookStorage:
    return storage or LocalWorkbookStorage.from_settings(settings)


def _reason(step: str, exc: BaseException) -> str:
    """The failure reason stored on the submission: which step, what kind of
    error, and its message - bounded, and never a traceback."""
    text = f"{step}: {type(exc).__name__}: {exc}".strip()
    return text[:_MAX_REASON_LENGTH]


def _mark_failed(settings: Settings, mdr_id: uuid.UUID, reason: str) -> None:
    """Record FAILED in its own transaction, after the step's has rolled back.

    If even this fails, the original error is what the caller reports; the
    failure to record it is logged here and not allowed to mask it.
    """
    try:
        with session_scope(settings) as session:
            submission = SubmissionRepository(session).get(mdr_id)
            if submission is not None:
                SubmissionRepository(session).mark_failed(submission, reason)
    except Exception:                                   # pragma: no cover
        log.exception("could not record FAILED for submission %s", mdr_id)


def _client_safe_discovery(discovery: Optional[dict]) -> dict:
    """The engine's discovery map without the server paths - see
    `_DISCOVERY_PATHS`."""
    return {k: v for k, v in (discovery or {}).items()
            if k not in _DISCOVERY_PATHS}


def _require(session, mdr_id: uuid.UUID) -> MdrSubmission:
    submission = SubmissionRepository(session).get(mdr_id)
    if submission is None:
        raise SubmissionNotFound(f"no submission with id {mdr_id}")
    return submission


def _require_status(submission: MdrSubmission, expected: SubmissionStatus,
                    step: str) -> None:
    if submission.status == expected.value:
        return
    if submission.status == SubmissionStatus.FAILED.value:
        hint = ("it is FAILED; upload the workbook again as a new submission")
    elif submission.status == SubmissionStatus.UPLOADED.value:
        hint = "it has not been extracted yet"
    else:
        hint = f"it is already {submission.status}"
    raise InvalidSubmissionState(
        f"cannot {step} submission {submission.id}: {hint} "
        f"(expected {expected.value})")


def _stored_workbook(storage: WorkbookStorage,
                     submission: MdrSubmission) -> Path:
    """The uploaded file, or a FileNotFoundError whose message names the key
    rather than the server's directory layout."""
    if not submission.stored_path or not storage.exists(submission.stored_path):
        raise FileNotFoundError(
            f"stored workbook {submission.stored_path or '(none)'} is missing "
            f"from upload storage")
    return storage.resolve(submission.stored_path)


# ------------------------------------------------------------------- upload

def upload_workbook(*, plant_id: uuid.UUID, filename: str, data: bytes,
                    settings: Settings = default_settings,
                    storage: Optional[WorkbookStorage] = None) -> MdrSubmission:
    """Accept an MDR workbook and create its submission at UPLOADED.

    In order: the bytes are checked (present, within the size limit, a
    supported extension, openable, carrying a QatarEnergy-TN sheet with a
    recognisable header); the plant is looked up; the file is stored under a
    fresh submission id; and the submission row is written pointing at it.
    The file is stored *before* the row so the database never references a
    workbook that is not there; if the row cannot be written the file is
    removed again.

    The digest and byte size are computed from the bytes actually received,
    not from anything the client claims.
    """
    if not data:
        raise InvalidUpload("the uploaded file is empty")
    if len(data) > settings.max_upload_bytes:
        raise UploadTooLarge(
            f"the upload is {len(data)} bytes; the limit is "
            f"{settings.max_upload_bytes} bytes (MDR_MAX_UPLOAD_BYTES)")
    if not filename or not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        raise InvalidUpload(
            f"unsupported file {filename!r}: expected one of "
            f"{', '.join(SUPPORTED_EXTENSIONS)}")
    try:
        probe_document_sheet(io.BytesIO(data))
    except _WORKBOOK_ERRORS as exc:
        raise InvalidUpload(f"not an MDR workbook: {exc}") from exc

    store = _storage(settings, storage)
    submission_id = uuid.uuid4()
    digest = hashlib.sha256(data).hexdigest()

    with session_scope(settings) as session:
        plant = PlantRepository(session).get(plant_id)
        if plant is None:
            raise PlantNotFound(f"no plant with id {plant_id}")

        key = store.put(data, submission_id=submission_id, filename=filename)
        try:
            submission = SubmissionRepository(session).add(
                submission_id=submission_id,
                plant_id=plant.id,
                # The name it arrived under, minus any path a client sent.
                source_filename=PurePosixPath(filename.replace("\\", "/")).name,
                source_sha256=digest,
                source_byte_size=len(data),
                stored_path=key,
            )
        except Exception:
            store.delete(key)
            raise
    log.info("submission %s uploaded for plant %s (%s, %d bytes)",
             submission.id, plant.code, submission.source_filename, len(data))
    return submission


# ------------------------------------------------------------------ extract

def extract_submission(mdr_id: uuid.UUID, *,
                       settings: Settings = default_settings,
                       storage: Optional[WorkbookStorage] = None,
                       ) -> MdrSubmission:
    """Read the stored workbook through the engine and persist its rows.

    `MdrEngine.run()` is the existing Phase 1 + 2A pipeline: it reads the
    QatarEnergy-TN sheet, normalises identity and revision, determines the
    latest revision and, when a rules workbook is present, classifies DOC
    TYPE. What it returns is stored as-is by `DocumentRowRepository.add_rows`,
    with SOW, IDB and DOC WITH REV empty - those are the automate step.

    UPLOADED -> EXTRACTED, or -> FAILED with the reason, and the uploaded file
    is left in place either way.
    """
    store = _storage(settings, storage)
    try:
        with session_scope(settings) as session:
            submission = _require(session, mdr_id)
            _require_status(submission, SubmissionStatus.UPLOADED, "extract")
            workbook = _stored_workbook(store, submission)

            result = MdrEngine(workbook).run()
            discovery = result.discovery or {}

            DocumentRowRepository(session).add_rows(
                submission.id, result.documents, automation_rows=())
            SubmissionRepository(session).mark_extracted(
                submission,
                sheet_name=discovery.get("qe_sheet", "") or "",
                header_row=discovery.get("qe_header_row"),
                row_count=discovery.get("qe_data_rows"),
            )
    except WorkflowError:
        raise
    except Exception as exc:
        log.exception("extraction failed for submission %s", mdr_id)
        _mark_failed(settings, mdr_id, _reason("extract", exc))
        raise ProcessingFailed(
            f"extraction failed and submission {mdr_id} is marked FAILED: "
            f"{_reason('extract', exc)}",
            client_error=isinstance(exc, _WORKBOOK_ERRORS)) from exc

    log.info("submission %s extracted: %s rows from sheet %r", submission.id,
             len(result.documents), submission.source_sheet_name)
    return submission


# ----------------------------------------------------------------- automate

def automate_submission(mdr_id: uuid.UUID, *,
                        settings: Settings = default_settings,
                        storage: Optional[WorkbookStorage] = None,
                        rules_workbook: Optional[Path] = None,
                        ) -> AutomateOutcome:
    """Run the automation engine over the stored workbook and persist the
    four columns, the rule set and the processing summary.

    `run_automation` is the existing Phase 2D entry point - the same call the
    CLI's `--excel` makes - so the values written are `AutomationRow`s the
    engine produced, not a reconstruction. The workbook is re-read from
    storage rather than the rows being rebuilt from the database, because the
    file is the authority and it is there.

    Before anything is written the engine's rows are matched against the
    rows extraction stored, by `source_row`; a mismatch means the two steps
    did not see the same workbook and the run fails rather than writing
    verdicts onto the wrong rows.

    The rule set is registered (or found, by digest) in the same transaction
    as the result that points at it. With no rules workbook to fingerprint
    the step is refused before it starts (`RulesUnavailable`) and the
    submission stays EXTRACTED: that is a deployment gap to fix, not a fact
    about this submission.

    EXTRACTED -> AUTOMATED, or -> FAILED with the reason.
    """
    store = _storage(settings, storage)
    rules = rules_workbook or settings.default_rules_workbook()
    if rules is None or not Path(rules).is_file():
        raise RulesUnavailable(
            f"no rules workbook is available to fingerprint (looked in "
            f"{settings.rules_dir}); nothing can be automated until one is "
            f"installed")

    try:
        with session_scope(settings) as session:
            submission = _require(session, mdr_id)
            _require_status(submission, SubmissionStatus.EXTRACTED, "automate")
            workbook = _stored_workbook(store, submission)

            run = run_automation(workbook, rules)

            rows = DocumentRowRepository(session)
            stored = rows.source_rows_for(submission.id)
            produced = {r.source_row for r in run.rows}
            if stored != produced:
                raise RuntimeError(
                    f"the engine produced {len(produced)} rows but "
                    f"extraction stored {len(stored)}; "
                    f"{len(produced - stored)} new and "
                    f"{len(stored - produced)} missing by source_row")

            updated = rows.update_automation(submission.id, run.rows)
            if updated != len(run.rows):
                raise RuntimeError(
                    f"updated {updated} rows for {len(run.rows)} "
                    f"automation rows")

            rule_set = register_rule_set(session, Path(rules))
            summary = ProcessingSummaryRepository(session).add(
                submission_id=submission.id,
                rule_set_id=rule_set.id,
                summary=run.summary(),
                engine_version=BACKEND_VERSION,
                discovery=_client_safe_discovery(run.result.discovery),
            )
            SubmissionRepository(session).mark_automated(submission)
    except WorkflowError:
        raise
    except Exception as exc:
        log.exception("automation failed for submission %s", mdr_id)
        _mark_failed(settings, mdr_id, _reason("automate", exc))
        raise ProcessingFailed(
            f"automation failed and submission {mdr_id} is marked FAILED: "
            f"{_reason('automate', exc)}",
            client_error=isinstance(exc, _WORKBOOK_ERRORS)) from exc

    log.info("submission %s automated: %d rows under rule set %s",
             submission.id, summary.row_count, rule_set.version_label)
    return AutomateOutcome(submission=submission, summary=summary,
                           rule_set=rule_set)


# ------------------------------------------------------------------ summary

def summarise_submission(mdr_id: uuid.UUID, *,
                         settings: Settings = default_settings,
                         ) -> SubmissionSummary:
    """Read what is persisted about one submission. Runs nothing.

    Every value comes from `mdr_submissions`, `plants`,
    `mdr_processing_summaries` and `rule_sets` as they stand; the per-value
    counts are the JSONB the automate step stored. The workbook is not
    opened and no engine is invoked - a summary that recomputed anything
    could disagree with the result it claims to describe.
    """
    with session_scope(settings) as session:
        submission = _require(session, mdr_id)
        plant = submission.plant
        summary = ProcessingSummaryRepository(session).for_submission(
            submission.id)
        rule_set = summary.rule_set if summary is not None else None
    return SubmissionSummary(submission=submission, plant=plant,
                             summary=summary, rule_set=rule_set)
