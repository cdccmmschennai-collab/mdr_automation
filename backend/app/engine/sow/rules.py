"""The SOW rules that decide DOC IS REQUIRED SOW, and how they are keyed.

Source: `data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`, sheet `DOCUMENT TYPE`.
Each of its 22 rows states three things about one kind of document:

    DOCUMENT TYPE               DOKAR   DOCUMENT SOW
    EQPT DATA SHEET             MDS     YES-MTL/DOC IDB
    P & I DRGS                  MXB     YES-FMTL/MTL/HIERARCHY/DOC IDB

Because the row names the document type *and* its DOKAR code, the lookup
accepts either. Phase 2A emits DOKAR codes for most documents (`MDS`, `MXB`)
but spells a few out (`SCHEMATIC DIAGRAM`), and both forms are the workbook's
own vocabulary - accepting both reads the sheet as written rather than adding
a synonym table.

Two DOC TYPE values are not document types at all but scope-of-work verdicts
that state their own answer:

    OLD REV NOT SOW  -> NO
    NOT SOW          -> NO

Those are evidenced by the reference working sheet, where all 9,934 rows
reading `OLD REV NOT SOW` and all 3,648 reading `NOT SOW` carry `NO` in
column AM, without exception. They are held apart from the workbook table
because they come from a different place: `OLD REV NOT SOW` is Phase 1's
revision verdict arriving through Phase 2A, not a row of the rules sheet. No
old-revision logic is reimplemented here - the verdict is consumed, not
recomputed.

`OTHER` is deliberately *not* in that set. It reads `NO` in 4,237 of 4,411
reference rows but `YES-...` in the other 174, so it states no rule; see
`docs/business-rules/sow-rules.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, NamedTuple, Sequence

from ..identity.normalisation import clean

#: The two `DOCUMENT TYPE` sheet columns a DOC TYPE may be matched on.
DOKAR = "DOKAR"
DOCUMENT_TYPE = "DOCUMENT_TYPE"

#: DOC TYPE values that are scope-of-work verdicts stating their own answer.
#: Mapped to their SOW value, not to a document type.
SELF_STATING_VERDICTS: dict[str, str] = {
    "OLD REV NOT SOW": "NO",
    "NOT SOW": "NO",
}


class SowRuleRow(NamedTuple):
    """One raw `DOCUMENT TYPE` sheet row, as the Excel adapter hands it over."""

    row: int                    # 1-based row in that sheet
    document_type: str          # e.g. 'EQPT DATA SHEET'
    dokar: str                  # e.g. 'MDS'
    sow: str                    # e.g. 'YES-MTL/DOC IDB'


def normalise(value: object) -> str:
    """Comparison form for DOC TYPE labels and SOW values.

    Whitespace collapsed and upper-cased, and nothing else. Punctuation is
    left alone on purpose: the SOW strings distinguish `YES-MTL/DOC IDB` from
    `YES-MTL/BOM/DOC IDB` by their separators, and the reference sheet's own
    spelling variants are a finding to report, not a difference to erase.
    """
    return clean(value).upper()


@dataclass(frozen=True)
class SowRule:
    """One `DOCUMENT TYPE` sheet row, normalised."""

    row: int
    document_type: str
    dokar: str
    sow: str

    @classmethod
    def parse(cls, row: SowRuleRow) -> "SowRule":
        return cls(
            row=row.row,
            document_type=normalise(row.document_type),
            dokar=normalise(row.dokar),
            sow=normalise(row.sow),
        )

    @property
    def is_usable(self) -> bool:
        """A rule with a SOW value and at least one label to key it on."""
        return bool(self.sow) and bool(self.dokar or self.document_type)


class SowRuleBook:
    """The loaded `DOCUMENT TYPE` rules, indexed by both of their labels.

    A DOKAR wins over a document-type name when the same string is used as
    both, so the code column - the one Phase 2A actually emits - is never
    shadowed. In the current workbook no such collision exists; the ordering
    is stated so that adding a row cannot change an existing answer silently.
    """

    def __init__(self, rules: Sequence[SowRule]):
        self.rules: tuple[SowRule, ...] = tuple(
            sorted((r for r in rules if r.is_usable), key=lambda r: r.row))

        self._by_dokar: dict[str, SowRule] = {}
        self._by_name: dict[str, SowRule] = {}
        for rule in self.rules:
            if rule.dokar:
                self._by_dokar.setdefault(rule.dokar, rule)
            if rule.document_type:
                self._by_name.setdefault(rule.document_type, rule)

    @classmethod
    def from_rows(cls, rows: Iterable[SowRuleRow]) -> "SowRuleBook":
        return cls([SowRule.parse(SowRuleRow(*r)) for r in rows])

    def __len__(self) -> int:
        return len(self.rules)

    def __iter__(self):
        return iter(self.rules)

    def lookup(self, label: str) -> tuple[SowRule | None, str]:
        """Find the rule for one DOC TYPE label, and say which column matched."""
        rule = self._by_dokar.get(label)
        if rule is not None:
            return rule, DOKAR
        rule = self._by_name.get(label)
        if rule is not None:
            return rule, DOCUMENT_TYPE
        return None, ""

    @property
    def dokars(self) -> tuple[str, ...]:
        """Every DOKAR code the sheet defines, in workbook order."""
        return tuple(r.dokar for r in self.rules if r.dokar)

    @property
    def sow_values(self) -> tuple[str, ...]:
        """Every distinct SOW value the sheet can produce, in workbook order."""
        seen: list[str] = []
        for r in self.rules:
            if r.sow not in seen:
                seen.append(r.sow)
        return tuple(seen)
