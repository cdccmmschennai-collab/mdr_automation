"""The product workflow: upload -> extract -> automate -> summary -> download.

This is the application layer behind `/api/v1/mdr`. Each function here is one
workflow step, owns one transaction, and composes what already exists:

    API route  ->  workflow_service  ->  repositories        ->  PostgreSQL
                          |-> infrastructure.storage         (the workbook)
                          |-> services.mdr_pipeline.MdrEngine
                          |-> services.automation_service    (the engine)
                          |-> services.rule_set_service      (which rules)
                          `-> services.export_service        (the .xlsx)

No MDR rule lives here. Extraction is `MdrEngine.run()`, exactly as the CLI
runs it; automation is `run_automation()`, exactly as `--excel` runs it; the
downloaded workbook is `export_automated_workbook()`, exactly as `--excel`
writes it. The rows that reach the database are the `DocumentRecord`s and
`AutomationRow`s those produce, mapped by the existing repository. What this
module adds is the sequencing, the state checks, the transaction boundaries
and the failure bookkeeping - the things an HTTP workflow needs that a CLI run
does not.

Delivery Phase 3 implemented the first four steps; Delivery Phase 4 adds
`download_submission`, which runs no engine at all: it rebuilds the
`AutomationRow`s from the persisted rows and hands them to the Phase 1 writer.

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
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from .. import __version__ as BACKEND_VERSION
from ..core.config import Settings, settings as default_settings
from ..domain.enums.lifecycle import SubmissionStatus
from ..domain.models.automation import AutomationRow, CheckStatusNotEvaluated
from ..infrastructure.excel.mdr_workbook import probe_document_sheet
from ..infrastructure.excel.output_workbook import WorkbookWriteReport
from ..infrastructure.excel.workbook_reader import (
    ColumnNotFoundError, SheetNotFoundError, WorkbookUnreadableError,
)
from ..infrastructure.filesystem.artifact_writer import sha256_file
from ..infrastructure.persistence.database import session_scope
from ..infrastructure.persistence.models import (
    MdrDocumentRow, MdrProcessingSummary, MdrSubmission, Plant, RuleSet,
)
from ..infrastructure.persistence.repositories import (
    DocumentRowRepository, PlantRepository, ProcessingSummaryRepository,
    SubmissionRepository,
)
from ..infrastructure.storage import (
    LocalWorkbookStorage, WorkbookStorage, safe_filename,
)
from .automation_service import run_automation
from .export_service import AUTOMATED_WORKBOOK_SUFFIX, export_automated_workbook
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

#: The media type of the workbook `download_submission` produces. The writer
#: always saves `.xlsx` (see `AUTOMATED_WORKBOOK_SUFFIX`), whatever the upload
#: was called.
XLSX_MEDIA_TYPE = ("application/vnd.openxmlformats-officedocument"
                   ".spreadsheetml.sheet")

#: Prefix of the temporary directory each download is generated into. Under
#: the system temporary directory, never under `uploads_dir` or any data
#: directory: the generated file is a response body, not a stored artefact.
_DOWNLOAD_TMP_PREFIX = "mdr-download-"

#: `MdrProcessingSummary` counters that `download_submission` recomputes from
#: the persisted rows and requires to agree. Each is `AutomationRun.summary()`
#: counting one non-empty column; the row-side attribute is named beside it.
_POPULATED_COUNTERS: tuple[tuple[str, str], ...] = (
    ("doc_with_rev_populated", "doc_with_rev"),
    ("doc_type_populated", "doc_type"),
    ("sow_populated", "sow"),
    ("idb_populated", "idb_status"),
)


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


class DownloadFailed(WorkflowError):
    """The automated workbook could not be generated from what is stored.

    Raised when the stored workbook is missing or is not the file that was
    uploaded, when the persisted rows do not agree with the persisted summary
    or with the workbook, or when the writer fails. It is a server-side
    condition (HTTP 500), and unlike `ProcessingFailed` it changes nothing:
    download is a read, and a failure to serve a result is not a fact about
    the result, so the submission stays AUTOMATED and keeps its history.
    """


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


@dataclass(frozen=True)
class DownloadArtifact:
    """What `download_submission` hands back: a generated workbook that exists
    only to be served once.

    `path` is inside `workdir`, a temporary directory created for this call
    alone. The route streams `path` and then calls `cleanup()`; nothing else
    references the file, no database column points at it, and a second
    download generates it again from the same persisted rows.
    """

    submission: MdrSubmission
    #: The generated workbook.
    path: Path
    #: The temporary directory `path` lives in; `cleanup()` removes it whole.
    workdir: Path
    #: The name the client should save the file under. Derived from the
    #: uploaded filename through `safe_filename`, so it carries nothing an
    #: HTTP header cannot - and never a server path.
    filename: str
    media_type: str
    #: What the writer did, for logging and for tests to assert against.
    report: WorkbookWriteReport

    def cleanup(self) -> None:
        """Remove the generated workbook and its directory. Idempotent: a
        second call, or a call after a partial failure, finds nothing to do."""
        shutil.rmtree(self.workdir, ignore_errors=True)


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
    elif (submission.status == SubmissionStatus.EXTRACTED.value
          and expected == SubmissionStatus.AUTOMATED):
        hint = "it has not been automated yet"
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


# ----------------------------------------------------------------- download

def download_filename(source_filename: str) -> str:
    """The name the generated workbook is offered under.

    The uploaded name's stem plus the export service's own suffix - the same
    name the CLI's `--excel` gives the file, so an employee sees the same
    thing whichever way it was produced. Passed through `safe_filename` first:
    the result holds letters, digits, spaces and a few punctuation marks, so
    it cannot carry a path, a quote or a control character into a
    `Content-Disposition` header.
    """
    stem = Path(safe_filename(source_filename)).stem
    return stem + AUTOMATED_WORKBOOK_SUFFIX


def _automation_row(stored: MdrDocumentRow) -> AutomationRow:
    """One persisted row as the `AutomationRow` the writer takes.

    `check_status` is passed through deliberately: the column is constrained
    to the empty string and `AutomationRow` refuses anything else, so a row
    that somehow carried a value raises here rather than being written.
    """
    return AutomationRow(
        source_row=stored.source_row,
        doc_with_rev=stored.doc_with_rev,
        doc_type=stored.doc_type,
        sow=stored.sow,
        idb_status=stored.idb_completed_status,
        check_status=stored.check_status,
        doc_type_rule=stored.doc_type_rule,
        sow_source=stored.sow_source,
        idb_source=stored.idb_source,
    )


def _persisted_automation_rows(session, submission: MdrSubmission
                               ) -> list[AutomationRow]:
    """The automation result exactly as PostgreSQL holds it, or a
    `DownloadFailed` naming what is wrong with it.

    Every check is against what the automate step itself persisted - the
    summary's row count and populated counters, and the header row extraction
    recorded. Nothing is recomputed from the workbook and no engine runs: the
    question is whether the stored result is whole, not whether it is right.
    A result that fails a check is not repaired, filtered or padded; the
    download refuses, because a workbook that quietly omitted rows would look
    finished.
    """
    summary = ProcessingSummaryRepository(session).for_submission(submission.id)
    if summary is None:
        raise DownloadFailed(
            f"submission {submission.id} is AUTOMATED but has no processing "
            f"summary")
    header_row = submission.source_header_row
    if header_row is None:
        raise DownloadFailed(
            f"submission {submission.id} is AUTOMATED but records no header "
            f"row for its document sheet")

    stored = DocumentRowRepository(session).for_submission(submission.id)
    if not stored:
        raise DownloadFailed(
            f"submission {submission.id} is AUTOMATED but has no document rows")

    source_rows = [r.source_row for r in stored]
    if len(set(source_rows)) != len(source_rows):
        raise DownloadFailed(
            f"submission {submission.id} holds duplicate source rows")
    if len(stored) != summary.row_count:
        raise DownloadFailed(
            f"submission {submission.id} holds {len(stored)} document rows "
            f"but its processing summary records {summary.row_count}")
    outside = [r for r in source_rows if r <= header_row]
    if outside:
        raise DownloadFailed(
            f"submission {submission.id} holds {len(outside)} document rows "
            f"at or above header row {header_row} of its document sheet")

    try:
        rows = [_automation_row(r) for r in stored]
    except CheckStatusNotEvaluated as exc:
        raise DownloadFailed(
            f"submission {submission.id} holds a CHECK STATUS value, which "
            f"nothing evaluates yet") from exc

    disagreeing = [
        counter for counter, attribute in _POPULATED_COUNTERS
        if sum(1 for r in rows if getattr(r, attribute))
        != getattr(summary, counter)
    ]
    if disagreeing:
        raise DownloadFailed(
            f"the document rows of submission {submission.id} disagree with "
            f"its processing summary on {', '.join(disagreeing)}")
    return rows


def _check_written(submission: MdrSubmission, rows: list[AutomationRow],
                   report: WorkbookWriteReport) -> None:
    """The writer must have found the sheet extraction found, at the header
    row extraction found, and written every row. A difference means the
    stored workbook is not the one the rows were extracted from."""
    if report.source_sheet != (submission.source_sheet_name or ""):
        raise DownloadFailed(
            f"the stored workbook of submission {submission.id} carries its "
            f"documents on sheet {report.source_sheet!r} but extraction read "
            f"{submission.source_sheet_name!r}")
    if report.header_row != submission.source_header_row:
        raise DownloadFailed(
            f"the stored workbook of submission {submission.id} has its "
            f"header at row {report.header_row} but extraction recorded row "
            f"{submission.source_header_row}")
    if report.rows_outside_sheet or report.rows_written != len(rows):
        raise DownloadFailed(
            f"wrote {report.rows_written} of {len(rows)} automation rows for "
            f"submission {submission.id}; {len(report.rows_outside_sheet)} "
            f"fell outside the document sheet")


def download_submission(mdr_id: uuid.UUID, *,
                        settings: Settings = default_settings,
                        storage: Optional[WorkbookStorage] = None,
                        ) -> DownloadArtifact:
    """Generate the automated workbook for an AUTOMATED submission.

    Runs nothing. The rows are read from `mdr_document_rows` as the automate
    step left them, rebuilt as `AutomationRow`s, and handed to
    `export_automated_workbook` - the Phase 1 writer the CLI's `--excel`
    uses - together with the stored upload. The result is therefore the
    employee's own workbook, every sheet in its original order, plus the
    `QatarEnergy-TN Automated` sheet populated from the database and mapped
    by `source_row`. The writer's guarantees (formulas, formatting, merges,
    conditional formats, validations, filter, frozen pane; CHECK STATUS
    blank; the source never written) are inherited, not re-implemented.

    The database is touched inside one read-only `session_scope` and released
    before the workbook is opened: generating the real ~22k-row file takes
    long enough that holding a transaction across it would be a cost with no
    benefit. Nothing is written to any table - a download changes no status,
    no timestamp and no row.

    The stored upload is verified against `source_sha256` before it is read,
    so a file that has been replaced, truncated or corrupted since upload is
    refused as such rather than surfacing as a writer error. The generated
    file is written to a fresh temporary directory, never beside the upload
    and never under a data directory; the caller owns it through
    `DownloadArtifact.cleanup()`. On any failure the directory is removed
    here and nothing is left behind.

    Only AUTOMATED is accepted. UPLOADED, EXTRACTED and FAILED are refused
    with `InvalidSubmissionState`; there is nothing to download from them.
    """
    store = _storage(settings, storage)
    with session_scope(settings) as session:
        submission = _require(session, mdr_id)
        _require_status(submission, SubmissionStatus.AUTOMATED, "download")
        rows = _persisted_automation_rows(session, submission)

    try:
        source = _stored_workbook(store, submission)
    except FileNotFoundError as exc:
        # The message names the storage key, not the server's directory.
        raise DownloadFailed(
            f"cannot download submission {mdr_id}: {exc}") from exc
    if sha256_file(source) != submission.source_sha256:
        raise DownloadFailed(
            f"cannot download submission {mdr_id}: the stored workbook does "
            f"not match the digest recorded at upload")

    filename = download_filename(submission.source_filename)
    workdir = Path(tempfile.mkdtemp(prefix=_DOWNLOAD_TMP_PREFIX))
    try:
        report = export_automated_workbook(
            source, rows, workdir, destination=workdir / filename)
        _check_written(submission, rows, report)
    except WorkflowError:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        log.exception("could not generate the download for submission %s",
                      mdr_id)
        # The type name says what kind of failure it was; the message may
        # quote a server path, so it stays in the log.
        raise DownloadFailed(
            f"cannot download submission {mdr_id}: the automated workbook "
            f"could not be generated ({type(exc).__name__})") from exc

    log.info("submission %s download generated: %d rows on sheet %r as %s",
             submission.id, report.rows_written, report.automated_sheet,
             filename)
    return DownloadArtifact(submission=submission, path=report.destination,
                            workdir=workdir, filename=filename,
                            media_type=XLSX_MEDIA_TYPE, report=report)
