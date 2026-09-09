"""The lifecycle of one MDR submission.

An uploaded workbook moves through the product workflow one step at a time,
and the status records how far it has actually got:

    UPLOADED  -> EXTRACTED -> AUTOMATED
        \\            \\
         `--------------`--> FAILED

`UPLOADED` is the only status a submission can be created with: a row cannot
appear already claiming that work was done to it. `FAILED` is reachable from
any step and records that the submission stopped there; it is not an end state
the workflow can move on from in Delivery Phase 2.

This is a domain enum, deliberately: the values are business facts about a
submission, not a database detail. `infrastructure.persistence` stores them as
text under a CHECK constraint rather than a PostgreSQL ENUM type - see
`persistence/models.py` for why.

Delivery Phase 2 persists these values; it does not implement the transitions,
because the upload, extract and automate workflows are later phases.
"""

from __future__ import annotations

from enum import StrEnum


class SubmissionStatus(StrEnum):
    """How far one MDR submission has progressed."""

    #: The workbook has been received and recorded. Nothing has read it yet.
    UPLOADED = "UPLOADED"
    #: The workbook has been read and its rows normalised into the database.
    EXTRACTED = "EXTRACTED"
    #: The four automation columns have been resolved and persisted.
    AUTOMATED = "AUTOMATED"
    #: Processing stopped. `mdr_submissions.failure_reason` says where.
    FAILED = "FAILED"


#: The status every submission starts in.
INITIAL_STATUS = SubmissionStatus.UPLOADED

#: Every legal value, for the database CHECK constraint and for validation.
SUBMISSION_STATUSES: tuple[str, ...] = tuple(s.value for s in SubmissionStatus)
