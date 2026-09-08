"""Phase 2B: DOC IS REQUIRED SOW.

`rules` holds the `DOCUMENT TYPE` sheet's DOKAR -> SOW table; `resolver`
applies it to one DOC TYPE at a time. Nothing here classifies a document, and
nothing here interprets the `DOC IDB` text inside a SOW value - that is
Phase 2C.
"""

from .resolver import UNRESOLVED, SowResolver
from .rules import SowRule, SowRuleBook, SowRuleRow

__all__ = ["SowResolver", "SowRuleBook", "SowRule", "SowRuleRow", "UNRESOLVED"]
