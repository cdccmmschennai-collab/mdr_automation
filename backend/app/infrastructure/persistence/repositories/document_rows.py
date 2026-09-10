"""Processed-row persistence.

This is the one repository that takes domain objects rather than keyword
arguments: it is handed the `DocumentRecord`s and `AutomationRow`s the existing
engine already produces, and maps them onto columns. No new domain model was
invented for the database - the engine's output *is* the thing being stored,
and a parallel set of "persistence models" would be two definitions of the same
row drifting apart.
"""

from __future__ import annotations

import uuid
from typing import Iterable, Optional, Sequence

from sqlalchemy import bindparam, func, select
from sqlalchemy.orm import Session

from ....domain.models.automation import AutomationRow
from ....domain.models.document import DocumentRecord
from ..models import MdrDocumentRow

#: How many rows to send per `INSERT`. The real workbook is ~22k rows; one
#: statement per row would be ~22k round trips, and one statement for all of
#: them would build a parameter list PostgreSQL rejects.
INSERT_CHUNK = 1000


class DocumentRowRepository:
    """Read and write `mdr_document_rows`."""

    def __init__(self, session: Session):
        self.session = session

    # ---------------------------------------------------------------- writes

    def add_rows(self, submission_id: uuid.UUID,
                 documents: Iterable[DocumentRecord],
                 automation_rows: Iterable[AutomationRow]) -> int:
        """Persist one submission's processed rows. Returns the row count.

        The two inputs are joined on `source_row`, not on position: the
        automation rows are built from the documents in order today, but a
        positional join would silently mis-attribute every automation value the
        day that stops being true. A document with no automation row is stored
        with its four automation columns empty rather than skipped - it is
        still a row that was processed.
        """
        by_source_row = {r.source_row: r for r in automation_rows}
        payload = [self._row_values(submission_id, doc,
                                    by_source_row.get(doc.source_row))
                   for doc in documents]
        for start in range(0, len(payload), INSERT_CHUNK):
            self.session.execute(MdrDocumentRow.__table__.insert(),
                                 payload[start:start + INSERT_CHUNK])
        self.session.flush()
        return len(payload)

    @staticmethod
    def _row_values(submission_id: uuid.UUID, doc: DocumentRecord,
                    row: Optional[AutomationRow]) -> dict:
        """One row as a plain dict, for the bulk insert.

        `check_status` is not taken from `row` even though `AutomationRow` has
        the attribute: it is always the empty string until Phase 3B, the
        dataclass refuses any other value, and the table has a CHECK constraint
        saying the same. Writing it literally keeps that fact in one more place
        that has to be changed deliberately.
        """
        return {
            "submission_id": submission_id,
            "source_row": doc.source_row,
            "document_identity": doc.document_identity,
            "qatarenergy_document_no": doc.qatarenergy_document_no,
            "revision": doc.revision,
            "revision_raw": doc.revision_raw,
            "revision_status": doc.revision_status,
            "is_latest_revision": doc.is_latest_revision,
            "document_title": doc.document_title,
            "discipline": doc.discipline,
            "doc_with_rev": row.doc_with_rev if row else "",
            "doc_type": row.doc_type if row else doc.doc_type,
            "sow": row.sow if row else "",
            "idb_completed_status": row.idb_status if row else "",
            "check_status": "",
            "doc_type_rule": row.doc_type_rule if row else doc.doc_type_rule,
            "sow_source": row.sow_source if row else "",
            "idb_source": row.idb_source if row else "",
        }

    def update_automation(self, submission_id: uuid.UUID,
                          automation_rows: Iterable[AutomationRow]) -> int:
        """Write the automation verdicts onto rows that already exist.

        The Delivery Phase 3 workflow extracts first and automates later, so
        the rows are inserted by `add_rows` with their four automation columns
        empty and filled in here. Each row is addressed by
        `(submission_id, source_row)` - the unique key - never by position.
        Returns the number of rows updated; the caller compares it with what
        it expected, because an automation row with no stored counterpart is
        a defect and not something to skip quietly.

        `check_status` is deliberately not in the SET list. It stays at the
        empty string the insert wrote, and the CHECK constraint would refuse
        anything else.
        """
        payload = [{
            "b_submission_id": submission_id,
            "b_source_row": row.source_row,
            "b_doc_with_rev": row.doc_with_rev,
            "b_doc_type": row.doc_type,
            "b_sow": row.sow,
            "b_idb_completed_status": row.idb_status,
            "b_doc_type_rule": row.doc_type_rule,
            "b_sow_source": row.sow_source,
            "b_idb_source": row.idb_source,
        } for row in automation_rows]
        if not payload:
            return 0

        table = MdrDocumentRow.__table__
        statement = (
            table.update()
            .where(table.c.submission_id == bindparam("b_submission_id"),
                   table.c.source_row == bindparam("b_source_row"))
            .values(doc_with_rev=bindparam("b_doc_with_rev"),
                    doc_type=bindparam("b_doc_type"),
                    sow=bindparam("b_sow"),
                    idb_completed_status=bindparam("b_idb_completed_status"),
                    doc_type_rule=bindparam("b_doc_type_rule"),
                    sow_source=bindparam("b_sow_source"),
                    idb_source=bindparam("b_idb_source"))
        )
        updated = 0
        for start in range(0, len(payload), INSERT_CHUNK):
            result = self.session.execute(statement,
                                          payload[start:start + INSERT_CHUNK])
            updated += result.rowcount
        self.session.flush()
        return updated

    # ----------------------------------------------------------------- reads

    def source_rows_for(self, submission_id: uuid.UUID) -> set[int]:
        """Every `source_row` stored for one submission.

        What the automate workflow checks its engine output against before
        writing: the rows the engine produced from the workbook must be the
        rows extraction stored from it, or the two runs did not see the same
        file.
        """
        return set(self.session.execute(
            select(MdrDocumentRow.source_row)
            .where(MdrDocumentRow.submission_id == submission_id)
        ).scalars())

    def count_for(self, submission_id: uuid.UUID) -> int:
        return self.session.execute(
            select(func.count()).select_from(MdrDocumentRow)
            .where(MdrDocumentRow.submission_id == submission_id)
        ).scalar_one()

    def for_submission(self, submission_id: uuid.UUID, *,
                       limit: Optional[int] = None,
                       offset: int = 0) -> Sequence[MdrDocumentRow]:
        """One submission's rows in source order.

        Paged, because the real workbook is ~22k rows and an endpoint that
        returns all of them is a decision to make deliberately, in the phase
        that adds the endpoint.
        """
        stmt = (select(MdrDocumentRow)
                .where(MdrDocumentRow.submission_id == submission_id)
                .order_by(MdrDocumentRow.source_row)
                .offset(offset))
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars())

    def by_source_row(self, submission_id: uuid.UUID,
                      source_row: int) -> Optional[MdrDocumentRow]:
        return self.session.execute(
            select(MdrDocumentRow).where(
                MdrDocumentRow.submission_id == submission_id,
                MdrDocumentRow.source_row == source_row)
        ).scalar_one_or_none()

    def doc_type_counts(self, submission_id: uuid.UUID) -> dict[str, int]:
        """`DOC TYPE` -> row count, for one submission."""
        rows = self.session.execute(
            select(MdrDocumentRow.doc_type, func.count())
            .where(MdrDocumentRow.submission_id == submission_id)
            .group_by(MdrDocumentRow.doc_type)
        ).all()
        return {doc_type: count for doc_type, count in rows}
