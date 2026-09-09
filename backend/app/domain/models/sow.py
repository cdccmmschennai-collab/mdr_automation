"""The DOC IS REQUIRED SOW verdict (Phase 2B).

A `SowRequirement` is what the SOW resolver decided for one document type: the
scope-of-work string the business writes into column AM, and where that string
came from.

The value is carried verbatim, never parsed. `YES-MTL/DOC IDB` is one opaque
business string; the `DOC IDB` inside it is part of the SOW value, *not* a
DOC IDB COMPLETED STATUS - that is Phase 2C and nothing here interprets it.

Pure Python: no Excel, no framework, no row/column coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: The SOW value the business writes when a document is out of scope.
NOT_REQUIRED = "NO"

#: Every in-scope SOW string in the rules workbook starts with this token.
REQUIRED_PREFIX = "YES"

# -- where a verdict came from ---------------------------------------------

#: The `DOCUMENT TYPE` sheet of the rules workbook stated it.
FROM_DOCUMENT_TYPE_TABLE = "DOCUMENT_TYPE_TABLE"
#: Phase 2A classified the document from the `NOT REQUIRED-KEY DOC.WORDS`
#: sheet, which is itself a scope statement: everything that sheet names is
#: out of scope. See `engine.sow.resolver`.
FROM_NOT_REQUIRED_KEYWORDS = "NOT_REQUIRED_KEYWORDS"
#: The DOC TYPE was itself a "not scope of work" verdict (`OLD REV NOT SOW`,
#: `NOT SOW`), which states its own SOW answer.
FROM_NOT_SOW_VERDICT = "NOT_SOW_VERDICT"
#: No DOC TYPE was supplied - there is nothing to resolve.
NO_DOC_TYPE = "NO_DOC_TYPE"
#: A DOC TYPE was supplied and the rules workbook does not cover it.
UNMAPPED_DOC_TYPE = "UNMAPPED_DOC_TYPE"


@dataclass(frozen=True)
class SowRequirement:
    """The DOC IS REQUIRED SOW verdict for one document type.

    `sow` is empty when the rules workbook states no answer. The resolver says
    "no rule covers this document type"; it never invents a business value.
    """

    doc_type: str = ""
    sow: str = ""
    source: str = NO_DOC_TYPE
    #: Row of the `DOCUMENT TYPE` sheet the value came from, for audit. 0 when
    #: the verdict did not come from that sheet.
    rule_row: int = 0
    #: The column of that sheet the DOC TYPE was matched on: DOKAR or
    #: DOCUMENT TYPE. Empty when the verdict came from elsewhere.
    matched_on: str = ""

    @property
    def is_resolved(self) -> bool:
        """True when the workbook states a SOW value for this DOC TYPE."""
        return bool(self.sow)

    @property
    def is_required(self) -> Optional[bool]:
        """True / False in scope, or None when nothing was resolved.

        Deliberately three-valued: an unresolved DOC TYPE is not the same
        business fact as a document the workbook says is out of scope, and
        collapsing the two would let a rule gap read as `NO`.
        """
        if not self.is_resolved:
            return None
        return self.sow.startswith(REQUIRED_PREFIX)

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "sow": self.sow,
            "source": self.source,
            "rule_row": self.rule_row,
            "matched_on": self.matched_on,
            "is_required": self.is_required,
        }
