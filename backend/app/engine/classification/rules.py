"""The keyword rules that decide DOC TYPE, and how their patterns match.

Source: `data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`, sheets
`REQUIRED-KEY DOC.WORDS` and `NOT REQUIRED-KEY DOC.WORDS`. Each row is one
rule: a DOCUMENT NO. keyword, a DOCUMENT TITLE keyword, and the DOC TYPE both
imply. `KEYWORD NOT APPLICABLE` means that side of the rule is unused; a rule
with both sides filled fires when *either* matches.

The keyword syntax is small and is implemented literally, not generically:

* **plain literal** - substring containment, e.g. `TEST CERTIFICATE`.
* **`*` wildcard** - `*A*B*` requires A, then B after it, anywhere in the text.
* **` or ` alternation** - `LIGHTING LAYOUT or LIGHTNING LAYOUT` is two
  alternatives; either matching fires the rule.
* **`XXXX` digit runs** - in a DOCUMENT NO. keyword only, `-13-XXXX` means
  `-13-` followed by four digits.

Matching is substring, not word-bounded. That is the authors' own convention,
not a tuning choice: the keywords are written in the singular (`TEST
CERTIFICATE`, `BILL OF MATERIAL`, `LOOP DRAWING`, `CROSS SECTION`,
`PIPING AND INSTRUMENT`, `ISOMETRIC`) while the documents they are meant to
catch are plural or inflected (`TEST CERTIFICATES`, `BILL OF MATERIALS`,
`LOOP DRAWINGS`, `CROSS SECTIONAL`, `PIPING AND INSTRUMENTATION`,
`ISOMETRICS`). Word-bounded matching drops every one of those.

See `docs/business-rules/classification-rules.md` for the evidence behind the
precedence order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, NamedTuple, Sequence

from ...domain.models.classification import (
    DOCUMENT_NUMBER, DOCUMENT_TITLE, RuleMatch,
)
from ..identity.normalisation import clean

#: Rule sources, in precedence order - see `RuleBook`.
REQUIRED = "REQUIRED"
NOT_REQUIRED = "NOT_REQUIRED"
SOURCE_PRECEDENCE = (REQUIRED, NOT_REQUIRED)

#: The rules workbook's own "this side of the rule is unused" marker.
NOT_APPLICABLE = "KEYWORD NOT APPLICABLE"

#: ` or ` between alternatives, whatever the surrounding whitespace.
_ALTERNATION = re.compile(r"\s+OR\s+")

#: A run of two or more X's in a document-number keyword: digit placeholders.
_DIGIT_RUN = re.compile(r"X{2,}")


class RuleRow(NamedTuple):
    """One raw rules-workbook row, as the Excel adapter hands it over."""

    source: str                 # REQUIRED / NOT_REQUIRED
    row: int                    # 1-based row in that sheet
    number_keyword: str
    title_keyword: str
    doc_type: str


def normalise(value: object) -> str:
    """Comparison form for both keywords and document text.

    Whitespace collapsed and upper-cased, and nothing else: `HOOK-UP`,
    `HOOK UP` and `HOOKUP` are three separate rules in the workbook, so
    collapsing punctuation would erase a distinction the business drew.
    """
    return clean(value).upper()


def _compile(pattern: str, *, digit_runs: bool) -> re.Pattern:
    """Translate one keyword alternative into a regex."""
    body = ".*".join(re.escape(seg) for seg in pattern.split("*"))
    if digit_runs:
        body = _DIGIT_RUN.sub(lambda m: "[0-9]{%d}" % len(m.group()), body)
    return re.compile(body)


def parse_keyword(keyword: object, *, digit_runs: bool = False
                  ) -> tuple[tuple[str, re.Pattern], ...]:
    """Split a keyword cell into its (alternative, regex) pairs.

    Returns an empty tuple for a blank cell or `KEYWORD NOT APPLICABLE`, which
    is what makes a one-sided rule one-sided.
    """
    text = normalise(keyword)
    if not text or text == NOT_APPLICABLE:
        return ()
    return tuple(
        (alt, _compile(alt, digit_runs=digit_runs))
        for alt in (a.strip() for a in _ALTERNATION.split(text))
        if alt and alt.strip("*")
    )


@dataclass(frozen=True)
class KeywordRule:
    """One rules-workbook row, with its patterns compiled."""

    source: str
    row: int
    doc_type: str
    number_keyword: str = ""
    title_keyword: str = ""
    number_patterns: tuple[tuple[str, re.Pattern], ...] = field(default=())
    title_patterns: tuple[tuple[str, re.Pattern], ...] = field(default=())

    @classmethod
    def parse(cls, row: RuleRow) -> "KeywordRule":
        return cls(
            source=row.source,
            row=row.row,
            doc_type=normalise(row.doc_type),
            number_keyword=normalise(row.number_keyword),
            title_keyword=normalise(row.title_keyword),
            # Digit runs are a document-number convention only; no title
            # keyword in the workbook contains a run of X's.
            number_patterns=parse_keyword(row.number_keyword, digit_runs=True),
            title_patterns=parse_keyword(row.title_keyword),
        )

    @property
    def is_usable(self) -> bool:
        """A rule with a DOC TYPE and at least one side to match on."""
        return bool(self.doc_type) and bool(
            self.number_patterns or self.title_patterns)

    def match(self, document_number: str, document_title: str) -> list[RuleMatch]:
        """Every way this rule fires against one document.

        Both sides are reported when both hit, so the audit trail shows the
        document number *and* the title agreed. Within one side the first
        alternative to match wins - they are synonyms of the same rule.
        """
        found: list[RuleMatch] = []
        for field_name, text, patterns, keyword in (
            (DOCUMENT_NUMBER, document_number, self.number_patterns,
             self.number_keyword),
            (DOCUMENT_TITLE, document_title, self.title_patterns,
             self.title_keyword),
        ):
            if not text:
                continue
            for pattern, regex in patterns:
                if regex.search(text):
                    found.append(RuleMatch(
                        doc_type=self.doc_type, rule_source=self.source,
                        rule_row=self.row, field=field_name,
                        pattern=pattern, keyword=keyword,
                    ))
                    break
        return found


class RuleBook:
    """The loaded rules, held in the order precedence resolves them.

    Precedence (derived in `docs/business-rules/classification-rules.md`):

    1. `REQUIRED-KEY DOC.WORDS` before `NOT REQUIRED-KEY DOC.WORDS`. Where
       rules from both sheets match the same row, the reference workbook sided
       with the required sheet 84 times and with the not-required sheet 0.
    2. Then workbook row order within a sheet - the order the business authored
       the rules in. The evidence for this one is weaker (22 rows against 4);
       the alternative, letting a document-number rule outrank a title rule,
       is recorded as an unresolved ambiguity rather than adopted.
    """

    def __init__(self, rules: Sequence[KeywordRule]):
        self.rules: tuple[KeywordRule, ...] = tuple(
            sorted((r for r in rules if r.is_usable),
                   key=lambda r: (self._source_order(r.source), r.row)))

    @staticmethod
    def _source_order(source: str) -> int:
        try:
            return SOURCE_PRECEDENCE.index(source)
        except ValueError:          # an unknown sheet sorts last, never first
            return len(SOURCE_PRECEDENCE)

    @classmethod
    def from_rows(cls, rows: Iterable[RuleRow]) -> "RuleBook":
        return cls([KeywordRule.parse(RuleRow(*r)) for r in rows])

    def __len__(self) -> int:
        return len(self.rules)

    def __iter__(self):
        return iter(self.rules)

    def by_source(self, source: str) -> tuple[KeywordRule, ...]:
        return tuple(r for r in self.rules if r.source == source)

    @property
    def doc_types(self) -> tuple[str, ...]:
        """Every DOC TYPE this rule book can produce, in precedence order."""
        seen: list[str] = []
        for r in self.rules:
            if r.doc_type not in seen:
                seen.append(r.doc_type)
        return tuple(seen)
