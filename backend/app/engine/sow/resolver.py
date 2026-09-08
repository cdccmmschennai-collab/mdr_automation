"""Deciding a document's DOC IS REQUIRED SOW (Phase 2B).

The resolver takes a document's *DOC TYPE* - nothing else - and returns a
`SowRequirement`. It never sees a document number, a title, a worksheet, a row
index or a column letter, and it never looks at column AM of the reference
workbook: column AM is the answer this stage is graded against, never an input
to it.

It also does not classify. The DOC TYPE it receives is Phase 2A's verdict,
already decided by the keyword rules; re-running keyword matching here would
give the pipeline two disagreeing classifiers. The chain is deliberately flat:

    document -> Phase 2A -> doc_type -> Phase 2B -> sow

A DOC TYPE the rules workbook does not cover produces an *unresolved*
requirement with an empty SOW value, not a guessed one. `NO` is a business
statement that a document is out of scope; a missing rule is not.
"""

from __future__ import annotations

from ...domain.models.sow import (
    FROM_DOCUMENT_TYPE_TABLE, FROM_NOT_SOW_VERDICT, NO_DOC_TYPE,
    UNMAPPED_DOC_TYPE, SowRequirement,
)
from ..identity.normalisation import is_null_token
from .rules import SELF_STATING_VERDICTS, SowRuleBook, normalise

#: Returned for a DOC TYPE no rule covers. Kept as a constant so callers can
#: test for it without a bare string, but it *is* the empty string: the
#: resolver reports "no rule states a SOW value", it does not invent one.
UNRESOLVED = ""


class SowResolver:
    """Applies a `SowRuleBook` to one DOC TYPE at a time."""

    def __init__(self, rules: SowRuleBook):
        self.rules = rules

    def resolve(self, doc_type: object = "") -> SowRequirement:
        """Resolve DOC IS REQUIRED SOW for one document type.

        Cells meaning "no value" in this project's convention ('-', 'N/A' and
        friends) are treated as absent rather than looked up, so a placeholder
        dash cannot match a rule.
        """
        label = "" if is_null_token(doc_type) else normalise(doc_type)
        if not label:
            return SowRequirement(source=NO_DOC_TYPE)

        verdict = SELF_STATING_VERDICTS.get(label)
        if verdict is not None:
            return SowRequirement(doc_type=label, sow=verdict,
                                  source=FROM_NOT_SOW_VERDICT)

        rule, matched_on = self.rules.lookup(label)
        if rule is None:
            return SowRequirement(doc_type=label, sow=UNRESOLVED,
                                  source=UNMAPPED_DOC_TYPE)

        return SowRequirement(doc_type=label, sow=rule.sow,
                              source=FROM_DOCUMENT_TYPE_TABLE,
                              rule_row=rule.row, matched_on=matched_on)
