"""Phase 2C: DOC IDB COMPLETED STATUS.

`rules` states the two rules the working sheet's column AN evidences and reads
a SOW string for its scope verdict; `resolver` applies them to one document's
Phase 2B requirement. Nothing here classifies a document, re-derives its scope
or re-decides its revision - each of those is an earlier phase's verdict,
consumed as given.
"""

from .resolver import IdbResolver
from .rules import normalise, outcome_of, scope_of

__all__ = ["IdbResolver", "normalise", "outcome_of", "scope_of"]
