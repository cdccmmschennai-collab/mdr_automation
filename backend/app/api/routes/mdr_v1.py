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

**Every handler here returns `501 Not Implemented`.** Delivery Phase 2 builds
the persistence and the contract; the behaviour is Delivery Phase 3 (upload,
extract, automate, summary) and Phase 4 (download). The stubs exist so the
paths, the methods and the response shapes are fixed and testable now - not so
the API can appear to work. None of them touches the database, runs the engine
or returns a fabricated result: an endpoint that answered with plausible
numbers it did not compute would be worse than one that answers 501.

`response_model` is declared on each so `/docs` shows the real contract. When a
handler starts returning data, the shape it must return is already written
down.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from ..schemas.mdr import (
    AutomateResponse, ErrorResponse, ExtractResponse, SummaryResponse,
    UploadResponse,
)

router = APIRouter(prefix="/mdr", tags=["mdr"])

#: The phase that will implement each endpoint, named in its 501 body so a
#: caller who hits one is told what is missing rather than only that it is.
_UPLOAD_PHASE = "Delivery Phase 3"
_DOWNLOAD_PHASE = "Delivery Phase 4"

#: Declared on every route so the contract documents the 501 rather than
#: leaving a caller to discover it.
_RESPONSES = {
    status.HTTP_501_NOT_IMPLEMENTED: {
        "model": ErrorResponse,
        "description": "Not implemented in Delivery Phase 2.",
    },
}


def _not_implemented(what: str, phase: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(f"{what} is not implemented: Delivery Phase 2 establishes "
                f"persistence and this API contract only. See {phase}."),
    )


@router.post("/upload", response_model=UploadResponse,
             status_code=status.HTTP_201_CREATED, responses=_RESPONSES,
             summary="Create an MDR submission from an uploaded workbook")
async def upload(plant_id: uuid.UUID = Form(...),
                 mdr_file: UploadFile = File(...)) -> UploadResponse:
    """Receive an MDR workbook and record it as a new submission.

    The parameters are declared so the multipart contract is real in `/docs`,
    but the file is never read: storing bytes, validating that they are an
    xlsx, and choosing where they live are the upload workflow.
    """
    raise _not_implemented("upload", _UPLOAD_PHASE)


@router.post("/{mdr_id}/extract", response_model=ExtractResponse,
             responses=_RESPONSES,
             summary="Extract and normalise the uploaded MDR workbook")
async def extract(mdr_id: uuid.UUID) -> ExtractResponse:
    """Read the submission's workbook and persist its normalised rows."""
    raise _not_implemented("extract", _UPLOAD_PHASE)


@router.post("/{mdr_id}/automate", response_model=AutomateResponse,
             responses=_RESPONSES,
             summary="Run the MDR automation engine over the submission")
async def automate(mdr_id: uuid.UUID) -> AutomateResponse:
    """Resolve DOC WITH REV, DOC TYPE, SOW and DOC IDB COMPLETED STATUS.

    Will record the rule set in force against the result - that is what makes
    the submission explainable after the rules change.
    """
    raise _not_implemented("automate", _UPLOAD_PHASE)


@router.get("/{mdr_id}/summary", response_model=SummaryResponse,
            responses=_RESPONSES,
            summary="Return the processing summary for one submission")
async def summary(mdr_id: uuid.UUID) -> SummaryResponse:
    """What the run produced, for this submission and no other."""
    raise _not_implemented("summary", _UPLOAD_PHASE)


@router.get("/{mdr_id}/download", responses=_RESPONSES,
            summary="Download the generated automated Excel workbook")
async def download(mdr_id: uuid.UUID) -> None:
    """Stream the workbook carrying the `QatarEnergy-TN Automated` sheet.

    No `response_model`: the eventual response is an xlsx byte stream, not
    JSON. The writer that produces it already exists
    (`infrastructure.excel.output_workbook`); serving it over HTTP is Phase 4.
    """
    raise _not_implemented("download", _DOWNLOAD_PHASE)
