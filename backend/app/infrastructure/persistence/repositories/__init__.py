"""Repositories: the only code that queries the MDR tables.

One repository per aggregate. Each takes a `Session` it does not own - the
caller opened the transaction and the caller commits it, so a service can write
a submission, its rows and its summary in one atomic unit rather than three.

No repository commits, and none catches a database exception. Both are
deliberate: a repository that commits makes atomic multi-table work impossible,
and one that swallows an `IntegrityError` turns a rejected foreign key into a
silent no-op.
"""

from .document_rows import DocumentRowRepository
from .plants import PlantRepository
from .rule_sets import RuleSetRepository
from .submissions import SubmissionRepository
from .summaries import ProcessingSummaryRepository

__all__ = [
    "DocumentRowRepository",
    "PlantRepository",
    "ProcessingSummaryRepository",
    "RuleSetRepository",
    "SubmissionRepository",
]
