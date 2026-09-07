"""Deciding a document's DOC TYPE (Phase 2A).

The classifier takes a document's *number* and *title* - nothing else - and
returns a `DocumentClassification`. It never sees a worksheet, a row index or
a column letter; the Excel adapter has already turned the row into named
fields by the time it gets here.

Only those two fields are used because only those two are what the rules
workbook keys on: its two keyword columns are `DOC NUMBER- KEYWORD` and
`DOC DESC- KEYWORDS`. Discipline, area, originator, revision and issue code are
deliberately not consulted - no rule in the workbook refers to them.
"""

from __future__ import annotations

from ...domain.models.classification import DocumentClassification, RuleMatch
from ..identity.normalisation import is_null_token
from .rules import RuleBook, normalise

#: Returned for a document no rule covers. Kept as a constant so callers can
#: test for it without a bare string, but it *is* the empty string: the
#: classifier reports "no rule matched", it does not invent a bucket.
UNCLASSIFIED = ""


class DocumentClassifier:
    """Applies a `RuleBook` to one document at a time."""

    def __init__(self, rules: RuleBook):
        self.rules = rules

    def classify(self, document_number: object = "",
                 document_title: object = "") -> DocumentClassification:
        """Classify one document from its number and title.

        Cells meaning "no value" in this project's convention ('-', 'N/A' and
        friends) are treated as absent rather than matched against, so a
        placeholder dash cannot satisfy a keyword.
        """
        number = "" if is_null_token(document_number) else normalise(document_number)
        title = "" if is_null_token(document_title) else normalise(document_title)

        matches: list[RuleMatch] = []
        for rule in self.rules:
            matches.extend(rule.match(number, title))

        if not matches:
            return DocumentClassification()

        winner = matches[0]      # rules are already in precedence order
        return DocumentClassification(
            doc_type=winner.doc_type,
            rule_source=winner.rule_source,
            matches=tuple(matches),
        )
