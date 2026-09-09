"""Processing-summary persistence.

The summary is where a result meets the rules that produced it: `rule_set_id`
is not optional, and there is no `add` that omits it. That is the whole point
of the table - a stored result whose rule set is unknown is a result nobody can
explain later.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import MdrProcessingSummary

#: `AutomationRun.summary()` keys that map onto integer columns. The remaining
#: keys are per-value breakdowns and go into `counts` as JSONB.
_COUNTER_COLUMNS = (
    ("rows", "row_count"),
    ("doc_with_rev_populated", "doc_with_rev_populated"),
    ("doc_type_populated", "doc_type_populated"),
    ("sow_populated", "sow_populated"),
    ("sow_unresolved", "sow_unresolved"),
    ("idb_populated", "idb_populated"),
    ("idb_unmapped", "idb_unmapped"),
    ("idb_manual_check_required", "idb_manual_check_required"),
    ("check_status_populated", "check_status_populated"),
)


class ProcessingSummaryRepository:
    """Read and write `mdr_processing_summaries`."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, *, submission_id: uuid.UUID, rule_set_id: uuid.UUID,
            summary: dict, engine_version: str = "",
            discovery: Optional[dict] = None) -> MdrProcessingSummary:
        """Store one run's summary.

        `summary` is `AutomationRun.summary()` verbatim - the same numbers the
        CLI prints. The scalar counts become columns so they can be queried and
        constrained; the per-value maps (`doc_type_counts`, `sow_counts`,
        `idb_counts`) go into `counts` as JSONB, together with the Phase 1
        `discovery` map when one is supplied.
        """
        columns = {column: int(summary.get(key, 0))
                   for key, column in _COUNTER_COLUMNS}
        breakdowns = {k: v for k, v in summary.items()
                      if k not in {key for key, _ in _COUNTER_COLUMNS}}
        if discovery is not None:
            breakdowns["discovery"] = discovery

        record = MdrProcessingSummary(
            submission_id=submission_id, rule_set_id=rule_set_id,
            engine_version=engine_version, counts=breakdowns, **columns)
        self.session.add(record)
        self.session.flush()
        return record

    def get(self, summary_id: uuid.UUID) -> Optional[MdrProcessingSummary]:
        return self.session.get(MdrProcessingSummary, summary_id)

    def for_submission(self, submission_id: uuid.UUID
                       ) -> Optional[MdrProcessingSummary]:
        return self.session.execute(
            select(MdrProcessingSummary).where(
                MdrProcessingSummary.submission_id == submission_id)
        ).scalar_one_or_none()

    def by_rule_set(self, rule_set_id: uuid.UUID) -> list[MdrProcessingSummary]:
        """Every result produced by one rule set.

        The question this table exists to answer, asked from the other side:
        *which submissions would be affected if these rules turn out to be
        wrong?*
        """
        return list(self.session.execute(
            select(MdrProcessingSummary)
            .where(MdrProcessingSummary.rule_set_id == rule_set_id)
            .order_by(MdrProcessingSummary.created_at)
        ).scalars())
