"""The MDR result aggregate.

`EngineResult` is what one Phase 1 run produces: the resolved document rows,
the resolved vendor rows, the Status Code book that was in force, and a record
of what was discovered in the workbook.

The `StatusCodeBook` annotation is a TYPE_CHECKING-only import so that the
domain carries no runtime dependency on the engine layer.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from ..enums.status_codes import RevisionStatus
from .document import DocumentRecord, VendorRecord

if TYPE_CHECKING:  # pragma: no cover
    from ...engine.revision.status_codes import StatusCodeBook


@dataclass
class EngineResult:
    documents: list[DocumentRecord] = field(default_factory=list)
    vendor_rows: list[VendorRecord] = field(default_factory=list)
    status_codes: Optional["StatusCodeBook"] = None
    discovery: dict = field(default_factory=dict)

    @property
    def exceptions(self) -> list[DocumentRecord]:
        return [d for d in self.documents if d.is_exception]

    def summary(self) -> dict:
        groups = {d.document_identity for d in self.documents if d.document_identity}
        match_counts: dict[str, int] = defaultdict(int)
        for v in self.vendor_rows:
            match_counts[v.match_status] += 1
        return {
            "document_rows": len(self.documents),
            "distinct_documents": len(groups),
            "latest_rows": sum(1 for d in self.documents
                               if d.revision_status == RevisionStatus.LATEST),
            "old_rows": sum(1 for d in self.documents
                            if d.revision_status == RevisionStatus.OLD),
            "as_built_rows": sum(1 for d in self.documents
                                 if d.revision_status == RevisionStatus.AS_BUILT),
            "exception_rows": len(self.exceptions),
            # Phase 2A. Zero when the run had no rules workbook to load.
            "doc_type_classified_rows": sum(1 for d in self.documents
                                            if d.doc_type),
            "vendor_rows": len(self.vendor_rows),
            "vendor_match_counts": dict(match_counts),
            "review_codes_loaded": len(self.status_codes.review_codes)
            if self.status_codes else 0,
            "issue_codes_loaded": len(self.status_codes.issue_codes)
            if self.status_codes else 0,
        }
