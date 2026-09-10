"""The `/api/v1/mdr` product API.

    POST /api/v1/mdr/upload                 create a submission from a workbook
    POST /api/v1/mdr/{mdr_id}/extract       read and normalise it
    POST /api/v1/mdr/{mdr_id}/automate      resolve the automation columns
    GET  /api/v1/mdr/{mdr_id}/summary       what the run produced
    GET  /api/v1/mdr/{mdr_id}/download      the automated workbook

Five endpoints named after the five things the product does, so the workflow is
legible from the route table alone. They are action endpoints rather than
nested resources because the workflow is genuinely procedural; if extract and
automate ever become long-running background work, the job resource that
follows will be added then, on evidence.

Delivery Phase 3 implements the first four through `services.workflow_service`.
**`download` still returns `501 Not Implemented`**: it is Delivery Phase 4.

A handler here does four things and no more: read the request, call one
service function, translate a `WorkflowError` into an HTTP status, and shape
the result. No SQL, no spreadsheet, no MDR rule - `tests/integration/
test_api_contract.py` inspects this module's imports and source to hold it to
that.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ...core.config import Settings
from ...services import workflow_service as workflow
from ..deps import get_settings
from ..schemas.mdr import (
    AutomateResponse, ErrorResponse, ExtractResponse, RuleSetRef,
    SummaryResponse, UploadResponse,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/mdr", tags=["mdr"])

_DOWNLOAD_PHASE = "Delivery Phase 4"


def _error(code: int, description: str) -> dict:
    return {code: {"model": ErrorResponse, "description": description}}


_NOT_FOUND = _error(404, "No submission with that id.")
_CONFLICT = _error(409, "The submission is not in a status this step starts from.")
_FAILED = _error(422, "The workbook cannot be processed; the submission is FAILED.")


def _http(exc: workflow.WorkflowError) -> HTTPException:
    """The HTTP status for each workflow error. The message is the service's
    own, written for the client; nothing else about the failure is forwarded."""
    if isinstance(exc, workflow.SubmissionNotFound):
        code = 404
    elif isinstance(exc, workflow.PlantNotFound):
        code = 404
    elif isinstance(exc, workflow.UploadTooLarge):
        code = 413
    elif isinstance(exc, workflow.InvalidUpload):
        code = 400
    elif isinstance(exc, workflow.InvalidSubmissionState):
        code = 409
    elif isinstance(exc, workflow.RulesUnavailable):
        code = 422
    elif isinstance(exc, workflow.ProcessingFailed):
        code = 422 if exc.client_error else 500
    else:                                                # pragma: no cover
        code = 500
    return HTTPException(status_code=code, detail=str(exc))


def _rule_set_ref(rule_set) -> RuleSetRef:
    return RuleSetRef(rule_set_id=rule_set.id,
                      version_label=rule_set.version_label,
                      source_filename=rule_set.source_filename,
                      content_sha256=rule_set.content_sha256)


# ------------------------------------------------------------------- upload

@router.post("/upload", response_model=UploadResponse,
             status_code=201,
             responses={
                 **_error(400, "Not an MDR workbook the engine can read."),
                 **_error(404, "No plant with that id."),
                 **_error(413, "Larger than MDR_MAX_UPLOAD_BYTES."),
             },
             summary="Create an MDR submission from an uploaded workbook")
async def upload(plant_id: uuid.UUID = Form(...),
                 mdr_file: UploadFile = File(...),
                 settings: Settings = Depends(get_settings)) -> UploadResponse:
    """Receive an MDR workbook and record it as a new submission at UPLOADED.

    The file is read in full, up to one byte past the configured limit so an
    oversized upload is refused without being held whole in memory first.
    """
    data = await mdr_file.read(settings.max_upload_bytes + 1)
    try:
        submission = workflow.upload_workbook(
            plant_id=plant_id, filename=mdr_file.filename or "", data=data,
            settings=settings)
    except workflow.WorkflowError as exc:
        raise _http(exc) from exc
    return UploadResponse(
        mdr_id=submission.id, submission_no=submission.submission_no,
        plant_id=submission.plant_id, status=submission.status,
        source_filename=submission.source_filename,
        source_sha256=submission.source_sha256,
        source_byte_size=submission.source_byte_size,
        uploaded_at=submission.uploaded_at,
    )


# ------------------------------------------------------------------ extract

@router.post("/{mdr_id}/extract", response_model=ExtractResponse,
             responses={**_NOT_FOUND, **_CONFLICT, **_FAILED},
             summary="Extract and normalise the uploaded MDR workbook")
def extract(mdr_id: uuid.UUID,
            settings: Settings = Depends(get_settings)) -> ExtractResponse:
    """Read the submission's workbook and persist its normalised rows.

    UPLOADED -> EXTRACTED. Synchronous: the response carries the outcome.
    """
    try:
        submission = workflow.extract_submission(mdr_id, settings=settings)
    except workflow.WorkflowError as exc:
        raise _http(exc) from exc
    return ExtractResponse(
        mdr_id=submission.id, status=submission.status,
        source_sheet_name=submission.source_sheet_name or "",
        source_header_row=submission.source_header_row,
        source_row_count=submission.source_row_count,
        extracted_at=submission.extracted_at,
    )


# ----------------------------------------------------------------- automate

@router.post("/{mdr_id}/automate", response_model=AutomateResponse,
             responses={**_NOT_FOUND, **_CONFLICT, **_FAILED},
             summary="Run the MDR automation engine over the submission")
def automate(mdr_id: uuid.UUID,
             settings: Settings = Depends(get_settings)) -> AutomateResponse:
    """Resolve DOC WITH REV, DOC TYPE, SOW and DOC IDB COMPLETED STATUS.

    EXTRACTED -> AUTOMATED. Records the rule set in force against the result -
    that is what makes the submission explainable after the rules change.
    """
    try:
        outcome = workflow.automate_submission(mdr_id, settings=settings)
    except workflow.WorkflowError as exc:
        raise _http(exc) from exc
    return AutomateResponse(
        mdr_id=outcome.submission.id, status=outcome.submission.status,
        row_count=outcome.summary.row_count,
        rule_set=_rule_set_ref(outcome.rule_set),
        automated_at=outcome.submission.automated_at,
    )


# ------------------------------------------------------------------ summary

@router.get("/{mdr_id}/summary", response_model=SummaryResponse,
            responses={**_NOT_FOUND},
            summary="Return the processing summary for one submission")
def summary(mdr_id: uuid.UUID,
            settings: Settings = Depends(get_settings)) -> SummaryResponse:
    """What is persisted about this submission and no other. A read: nothing
    is extracted, automated or modified by asking."""
    try:
        found = workflow.summarise_submission(mdr_id, settings=settings)
    except workflow.WorkflowError as exc:
        raise _http(exc) from exc

    submission, plant, stored = found.submission, found.plant, found.summary
    response = SummaryResponse(
        mdr_id=submission.id, submission_no=submission.submission_no,
        plant_id=submission.plant_id, plant_code=plant.code,
        status=submission.status, failure_reason=submission.failure_reason,
        source_filename=submission.source_filename,
        uploaded_at=submission.uploaded_at,
        extracted_at=submission.extracted_at,
        automated_at=submission.automated_at,
    )
    if stored is None:
        return response
    return response.model_copy(update={
        "rule_set": _rule_set_ref(found.rule_set),
        "engine_version": stored.engine_version,
        "row_count": stored.row_count,
        "doc_with_rev_populated": stored.doc_with_rev_populated,
        "doc_type_populated": stored.doc_type_populated,
        "sow_populated": stored.sow_populated,
        "sow_unresolved": stored.sow_unresolved,
        "idb_populated": stored.idb_populated,
        "idb_unmapped": stored.idb_unmapped,
        "idb_manual_check_required": stored.idb_manual_check_required,
        "check_status_populated": stored.check_status_populated,
        "counts": dict(stored.counts or {}),
    })


# ----------------------------------------------------------------- download

@router.get("/{mdr_id}/download",
            responses=_error(501,
                             "Not implemented until Delivery Phase 4."),
            summary="Download the generated automated Excel workbook")
async def download(mdr_id: uuid.UUID) -> None:
    """Stream the workbook carrying the `QatarEnergy-TN Automated` sheet.

    No `response_model`: the eventual response is an xlsx byte stream, not
    JSON. The writer that produces it already exists
    (`infrastructure.excel.output_workbook`); serving it over HTTP is Phase 4.
    """
    raise HTTPException(
        status_code=501,
        detail=(f"download is not implemented: Delivery Phase 3 implements "
                f"upload, extract, automate and summary only. See "
                f"{_DOWNLOAD_PHASE}."),
    )
