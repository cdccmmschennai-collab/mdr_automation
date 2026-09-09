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

The rules workbook states scope in *two* places, and both are read:

* `DOCUMENT TYPE` - the 22-row table of in-scope document types and their
  `DOCUMENT SOW` strings, keyed by DOKAR code or type name;
* `NOT REQUIRED-KEY DOC.WORDS` - the keyword sheet whose name is its rule.
  Every DOC TYPE it defines (`CV`, `METHOD STATEMENT`, `PLAN`, `PLOT PLAN`,
  `LAYOUT`, ...) is a document type the business has already declared out of
  scope; that is what puts it on the *not required* sheet rather than the
  required one. None of its 63 document types appears in the `DOCUMENT TYPE`
  table, and looking for them there is what used to leave 6,500 rows
  `UNMAPPED`.

Phase 2A already records which sheet decided a DOC TYPE
(`DocumentClassification.rule_source`, carried on
`DocumentRecord.doc_type_source`), so `resolve` takes that verdict as a second
argument rather than re-reading the keyword sheets - the classifier stays the
only thing that matches keywords.

Precedence: the `DOCUMENT TYPE` table is consulted first, so a type that sheet
names in scope keeps its `YES-...` string whatever else matched. The
not-required sheet answers only where the table is silent. `RuleBook` already
gives `REQUIRED-KEY DOC.WORDS` precedence when both sheets match a document,
so a required document never arrives here labelled NOT_REQUIRED.

A DOC TYPE that neither states produces an *unresolved* requirement with an
empty SOW value, not a guessed one. `NO` is a business statement that a
document is out of scope; a missing rule is not.
"""

from __future__ import annotations

from ...domain.models.sow import (
    FROM_DOCUMENT_TYPE_TABLE, FROM_NOT_REQUIRED_KEYWORDS, FROM_NOT_SOW_VERDICT,
    NOT_REQUIRED, NO_DOC_TYPE, UNMAPPED_DOC_TYPE, SowRequirement,
)
from ..classification.rules import NOT_REQUIRED as NOT_REQUIRED_SHEET
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

    def resolve(self, doc_type: object = "",
                rule_source: object = "") -> SowRequirement:
        """Resolve DOC IS REQUIRED SOW for one document type.

        `rule_source` is Phase 2A's `DocumentClassification.rule_source`: which
        keyword sheet decided this DOC TYPE. Only `NOT_REQUIRED` changes the
        answer, and only where the `DOCUMENT TYPE` table is silent. It is
        optional so a caller that has a bare label - the reference-workbook
        graders read a hand-typed DOC TYPE column that no classifier produced -
        keeps the table-only behaviour it always had.

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
        if rule is not None:
            return SowRequirement(doc_type=label, sow=rule.sow,
                                  source=FROM_DOCUMENT_TYPE_TABLE,
                                  rule_row=rule.row, matched_on=matched_on)

        if normalise(rule_source) == NOT_REQUIRED_SHEET:
            # The sheet that classified the document is the sheet of document
            # types the business does not require. That is a scope statement,
            # not a rule gap.
            return SowRequirement(doc_type=label, sow=NOT_REQUIRED,
                                  source=FROM_NOT_REQUIRED_KEYWORDS)

        return SowRequirement(doc_type=label, sow=UNRESOLVED,
                              source=UNMAPPED_DOC_TYPE)
