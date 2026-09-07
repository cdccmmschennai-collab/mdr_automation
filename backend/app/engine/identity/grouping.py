"""Document grouping.

Rows belong to the same document when their canonical identity keys are equal.
Grouping is separated from ranking so that both the latest-revision engine and
the validation layer group rows the same way, by construction.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from ...domain.models.document import DocumentRecord


def group_by_identity(
    records: Iterable[DocumentRecord],
) -> dict[str, list[DocumentRecord]]:
    """Group document rows by their canonical document identity."""
    groups: dict[str, list[DocumentRecord]] = defaultdict(list)
    for record in records:
        groups[record.document_identity].append(record)
    return groups
