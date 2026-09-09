"""MDR submission persistence.

Every read here is scoped to a plant or to one submission id. There is no
`get_latest()` and no "current submission" anywhere in this module: MDR #6 must
stay as retrievable as MDR #8 for as long as the business keeps it, and a
convenience accessor for "the newest one" is how a schema quietly becomes a
single-submission schema.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ....domain.enums.lifecycle import INITIAL_STATUS, SubmissionStatus
from ..models import MdrSubmission


class SubmissionRepository:
    """Read and write `mdr_submissions`."""

    def __init__(self, session: Session):
        self.session = session

    # ---------------------------------------------------------------- create

    def next_submission_no(self, plant_id: uuid.UUID) -> int:
        """The next `MDR #n` for this plant.

        `max + 1`, not a sequence: the number is the plant's, and a shared
        sequence would leave every plant with gaps that read as lost
        submissions. Two concurrent uploads can compute the same number; the
        unique index on `(plant_id, submission_no)` then rejects the second,
        which is a visible error rather than two submissions called #7.
        """
        highest = self.session.execute(
            select(func.max(MdrSubmission.submission_no))
            .where(MdrSubmission.plant_id == plant_id)
        ).scalar_one_or_none()
        return (highest or 0) + 1

    def add(self, *, plant_id: uuid.UUID, source_filename: str,
            source_sha256: str, source_byte_size: int,
            submission_no: Optional[int] = None, stored_path: str = "",
            ) -> MdrSubmission:
        """Record an uploaded workbook.

        The status is always `UPLOADED`: a submission cannot be created already
        claiming that work was done to it.
        """
        submission = MdrSubmission(
            plant_id=plant_id,
            submission_no=(submission_no if submission_no is not None
                           else self.next_submission_no(plant_id)),
            status=INITIAL_STATUS.value,
            source_filename=source_filename,
            source_sha256=source_sha256,
            source_byte_size=source_byte_size,
            stored_path=stored_path,
        )
        self.session.add(submission)
        self.session.flush()
        return submission

    # ------------------------------------------------------------------ read

    def get(self, submission_id: uuid.UUID) -> Optional[MdrSubmission]:
        return self.session.get(MdrSubmission, submission_id)

    def by_plant(self, plant_id: uuid.UUID) -> list[MdrSubmission]:
        """Every submission for a plant, oldest first. History, in order."""
        return list(self.session.execute(
            select(MdrSubmission)
            .where(MdrSubmission.plant_id == plant_id)
            .order_by(MdrSubmission.submission_no)
        ).scalars())

    def by_number(self, plant_id: uuid.UUID,
                  submission_no: int) -> Optional[MdrSubmission]:
        """`MDR #6` for a plant - the way the business names a submission."""
        return self.session.execute(
            select(MdrSubmission).where(
                MdrSubmission.plant_id == plant_id,
                MdrSubmission.submission_no == submission_no)
        ).scalar_one_or_none()

    def by_digest(self, source_sha256: str) -> list[MdrSubmission]:
        """Every submission created from these exact bytes."""
        return list(self.session.execute(
            select(MdrSubmission)
            .where(MdrSubmission.source_sha256 == source_sha256)
            .order_by(MdrSubmission.uploaded_at)
        ).scalars())

    # ------------------------------------------------------------- lifecycle

    def mark_extracted(self, submission: MdrSubmission, *,
                       sheet_name: str = "", header_row: Optional[int] = None,
                       row_count: Optional[int] = None) -> MdrSubmission:
        """Move to EXTRACTED and record what was found in the workbook."""
        submission.status = SubmissionStatus.EXTRACTED.value
        submission.source_sheet_name = sheet_name
        submission.source_header_row = header_row
        submission.source_row_count = row_count
        submission.extracted_at = _dt.datetime.now(_dt.timezone.utc)
        self.session.flush()
        return submission

    def mark_automated(self, submission: MdrSubmission) -> MdrSubmission:
        submission.status = SubmissionStatus.AUTOMATED.value
        submission.automated_at = _dt.datetime.now(_dt.timezone.utc)
        self.session.flush()
        return submission

    def mark_failed(self, submission: MdrSubmission,
                    reason: str) -> MdrSubmission:
        """Record that processing stopped, and where.

        `reason` is required and is stored verbatim. A FAILED submission with
        an empty reason is an incident nobody can investigate.
        """
        if not reason.strip():
            raise ValueError("a failed submission must carry a reason")
        submission.status = SubmissionStatus.FAILED.value
        submission.failure_reason = reason
        self.session.flush()
        return submission
