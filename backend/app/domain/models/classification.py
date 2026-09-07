"""DOC TYPE classification results (Phase 2A).

A `DocumentClassification` is what the classifier decided about one document:
its DOC TYPE, and every keyword rule that fired on the way to that verdict.

Every match is kept, not only the winner, because the rules workbook genuinely
lets one document match several rules - "CV OF ... PLANNING ENGINEER" matches
both the CV rule and the PLAN rule. Discarding the losers would hide a real
business ambiguity behind a single string.

Pure Python: no Excel, no framework, no row/column coordinates. `rule_row` is
retained only so a human can find the rule again in the rules workbook.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The evidence field a rule matched against.
DOCUMENT_NUMBER = "DOCUMENT_NUMBER"
DOCUMENT_TITLE = "DOCUMENT_TITLE"


@dataclass(frozen=True)
class RuleMatch:
    """One keyword rule firing against one document."""

    doc_type: str
    #: REQUIRED / NOT_REQUIRED - which keyword sheet the rule came from.
    rule_source: str
    #: 1-based row of the rule in its sheet.
    rule_row: int
    #: DOCUMENT_NUMBER or DOCUMENT_TITLE.
    field: str
    #: The alternative that actually matched (an `A or B` rule has two).
    pattern: str
    #: The whole keyword cell the pattern came from.
    keyword: str

    def describe(self) -> str:
        """Short audit string, e.g. `REQUIRED#51 DOCUMENT_TITLE 'P&ID'`."""
        return f"{self.rule_source}#{self.rule_row} {self.field} {self.pattern!r}"

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "rule_source": self.rule_source,
            "rule_row": self.rule_row,
            "field": self.field,
            "pattern": self.pattern,
            "keyword": self.keyword,
        }


@dataclass(frozen=True)
class DocumentClassification:
    """The DOC TYPE verdict for one document.

    `doc_type` is empty when no rule matched: the classifier says "no rule
    covers this document", never a guess.
    """

    doc_type: str = ""
    rule_source: str = ""
    matches: tuple[RuleMatch, ...] = ()

    @property
    def is_classified(self) -> bool:
        return bool(self.doc_type)

    @property
    def winning_match(self) -> RuleMatch | None:
        return self.matches[0] if self.matches else None

    @property
    def competing_doc_types(self) -> tuple[str, ...]:
        """Every distinct DOC TYPE that matched, in precedence order."""
        seen: list[str] = []
        for m in self.matches:
            if m.doc_type not in seen:
                seen.append(m.doc_type)
        return tuple(seen)

    @property
    def is_ambiguous(self) -> bool:
        """True when rules disagreed and precedence had to decide."""
        return len(self.competing_doc_types) > 1

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "rule_source": self.rule_source,
            "competing_doc_types": list(self.competing_doc_types),
            "matches": [m.to_dict() for m in self.matches],
        }
