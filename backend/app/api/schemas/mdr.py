"""The `/api/v1/mdr` contract.

Every field below is a real domain concept that Delivery Phase 2 already
persists - a column on `mdr_submissions`, `mdr_processing_summaries`,
`rule_sets` or `plants`. Nothing is invented to make a response look fuller: a
field that no table can supply would be a promise the next phase has to either
implement or break.

Delivery Phase 2 fixed these shapes and answered every endpoint with 501.
Delivery Phase 3 implements upload, extract, automate and summary against
them; download remains Phase 4. The Phase 3 additions to `SummaryResponse`
(`plant_code`, `extracted_at`, `failure_reason`) are backward-compatible: new
fields, all optional or defaulted.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ...domain.enums.lifecycle import SubmissionStatus


class UploadResponse(BaseModel):
    """What `POST /api/v1/mdr/upload` returns.

    `mdr_id` is the identifier every later call in the workflow uses.
    `submission_no` is the same submission as the business names it - `MDR #6`
    for that plant - and is returned alongside because an operator reading a
    screen recognises the number, not the UUID.
    """

    mdr_id: uuid.UUID = Field(description="Identifier for this submission.")
    submission_no: int = Field(description="The plant's nth submission, from 1.")
    plant_id: uuid.UUID
    status: SubmissionStatus = Field(
        description="Always UPLOADED for a newly created submission.")
    source_filename: str
    source_sha256: str = Field(description="SHA-256 of the uploaded bytes.")
    source_byte_size: int
    uploaded_at: _dt.datetime


class ExtractResponse(BaseModel):
    """What `POST /api/v1/mdr/{mdr_id}/extract` returns.

    The three `sheet`/`header_row`/`row_count` values are what the workbook
    turned out to contain - `MdrEngine.run().discovery`, persisted onto the
    submission. They are the operator's evidence that the right sheet was read.
    """

    mdr_id: uuid.UUID
    status: SubmissionStatus = Field(description="EXTRACTED on success.")
    source_sheet_name: str
    source_header_row: Optional[int] = None
    source_row_count: Optional[int] = None
    extracted_at: Optional[_dt.datetime] = None


class RuleSetRef(BaseModel):
    """The rule set that produced a result.

    Present on every automation response for one reason: a result whose rules
    are unknown cannot be explained after the rules change. See
    `services.rule_set_service`.
    """

    rule_set_id: uuid.UUID
    version_label: str
    source_filename: str
    content_sha256: str


class AutomateResponse(BaseModel):
    """What `POST /api/v1/mdr/{mdr_id}/automate` returns."""

    mdr_id: uuid.UUID
    status: SubmissionStatus = Field(description="AUTOMATED on success.")
    row_count: int
    rule_set: RuleSetRef
    automated_at: Optional[_dt.datetime] = None


class SummaryResponse(BaseModel):
    """What `GET /api/v1/mdr/{mdr_id}/summary` returns.

    Available for a submission in any status. Before AUTOMATED the counters
    are zero, `rule_set` is null and `counts` is empty - the summary of a
    submission that has not been automated is its status and timestamps; for a
    FAILED one, `failure_reason` says where it stopped.

    The counters are `mdr_processing_summaries` columns, which are in turn
    `AutomationRun.summary()` - the numbers the CLI already prints.

    `check_status_populated` is always 0 and is returned anyway. CHECK STATUS
    is structurally blank until the received-document dump exists, and a
    consumer that can see the zero cannot mistake blank cells for a failed run.
    """

    mdr_id: uuid.UUID
    submission_no: int
    plant_id: uuid.UUID
    plant_code: str = Field(default="", description="The plant's business key.")
    status: SubmissionStatus
    failure_reason: str = Field(
        default="", description="Why processing stopped. Empty unless FAILED.")
    source_filename: str
    uploaded_at: _dt.datetime
    extracted_at: Optional[_dt.datetime] = None
    automated_at: Optional[_dt.datetime] = None

    rule_set: Optional[RuleSetRef] = None
    engine_version: str = ""

    row_count: int = 0
    doc_with_rev_populated: int = 0
    doc_type_populated: int = 0
    sow_populated: int = 0
    sow_unresolved: int = 0
    idb_populated: int = 0
    idb_unmapped: int = 0
    idb_manual_check_required: int = Field(
        default=0,
        description="Required documents left blank for a human to check.")
    check_status_populated: int = Field(
        default=0, description="Always 0: CHECK STATUS is not evaluated yet.")

    counts: dict = Field(
        default_factory=dict,
        description="Per-value breakdowns: doc_type_counts, sow_counts, "
                    "idb_counts, and the extraction discovery map.")


class ErrorResponse(BaseModel):
    """FastAPI's error shape, declared so it appears in the contract."""

    detail: str
