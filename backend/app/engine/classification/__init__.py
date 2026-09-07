"""DOC TYPE classification (Phase 2A).

`rules`      - the keyword rules and their matching semantics.
`classifier` - applies them to one document.

Nothing here knows about Excel, HTTP or the frontend. SOW, IDB and CHECK
STATUS are later phases and are not implemented.
"""

from .classifier import UNCLASSIFIED, DocumentClassifier
from .rules import NOT_REQUIRED, REQUIRED, KeywordRule, RuleBook, RuleRow

__all__ = [
    "DocumentClassifier", "UNCLASSIFIED",
    "RuleBook", "KeywordRule", "RuleRow", "REQUIRED", "NOT_REQUIRED",
]
