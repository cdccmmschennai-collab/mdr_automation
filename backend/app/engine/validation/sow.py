"""DOC IS REQUIRED SOW validation against the reference working file.

Column AM of `QatarEnergy-TN WORKING` is the manual result Phase 2B automates,
so it doubles as ground truth. It is a *dirty* target, and the report below
says so rather than tuning the engine until the number looks good:

* 18,706 of its 21,372 rows read `NO`, almost all of them because column AL
  holds `OLD REV NOT SOW` or `NOT SOW` - revision and scope verdicts, not
  document types.
* The `DOCUMENT TYPE` sheet's own rule and column AM genuinely disagree for
  several DOKARs. The clearest is systematic: every rule whose SOW string
  contains `/HIERARCHY` (MBD, MLP, MSD, MSL, MXB) is written into column AM
  *without* it, in 165 of 197 rows, and `HIERARCHY` appears in column AM only
  31 times, always in some other combination.
* Column AM is hand-typed and carries spelling variants (`YEE-MTL/DOC IDB`,
  `YES-FMTL/MLT/DOC IDB`, `YES/DOC IDB`) and non-SOW entries (`CANCELLED`,
  `0`).

Mismatches are therefore classified by root cause. The spelling-variant
canonicalisation below exists **only to sort mismatches into causes** - it
never touches the value Phase 2B computes, and a canonical-only agreement is
counted as a mismatch, not as a match.

Nothing here writes to the reference workbook, and column AM is never fed to
the resolver: `compare_sow` calls `resolver.resolve(row.doc_type)`, which is
the whole of the resolver's input.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Protocol

from ...domain.models.sow import (
    FROM_NOT_SOW_VERDICT, NOT_REQUIRED, UNMAPPED_DOC_TYPE,
)
from ..sow.resolver import SowResolver
from ..sow.rules import normalise


class Cause(str, Enum):
    """Root cause of an engine-vs-reference SOW mismatch."""

    #: Column AM is empty - no ground truth for this row.
    REFERENCE_BLANK = "REFERENCE_BLANK"
    #: Column AM holds something that is not a SOW verdict at all
    #: (`CANCELLED`, `0`). A workbook data-entry state, not a rule.
    REFERENCE_NOT_A_SOW_VALUE = "REFERENCE_NOT_A_SOW_VALUE"
    #: Column AL is empty - there is no DOC TYPE to resolve from.
    DOC_TYPE_ABSENT = "DOC_TYPE_ABSENT"
    #: Column AL names something the `DOCUMENT TYPE` sheet does not cover
    #: (`OTHER`, `GAD`, `TNR`, `MATERIAL SUBMITTAL`, ...). A gap in the rules
    #: workbook, not a wrong rule.
    DOC_TYPE_NOT_IN_SOW_TABLE = "DOC_TYPE_NOT_IN_SOW_TABLE"
    #: The rule's SOW string contains `/HIERARCHY` and the reference is the
    #: same string without it. A systematic divergence between the rules
    #: workbook and the working sheet - see the module docstring.
    RULE_STATES_HIERARCHY = "RULE_STATES_HIERARCHY"
    #: Rule and reference name the same SOW components and differ only in
    #: spelling, spacing or separators.
    REFERENCE_SPELLING_VARIANT = "REFERENCE_SPELLING_VARIANT"
    #: The rule says the document is in scope and the reference says `NO`. A
    #: manual scope decision; nothing in DOC TYPE predicts which rows get it.
    REFERENCE_OVERRIDES_TO_NO = "REFERENCE_OVERRIDES_TO_NO"
    #: Both state a SOW value and they name different components. The rules
    #: workbook and the working sheet disagree on the rule itself.
    RULE_DISAGREES_WITH_REFERENCE = "RULE_DISAGREES_WITH_REFERENCE"


#: Causes that say nothing about whether the resolver is right, because either
#: side of the comparison is missing.
OUT_OF_SCOPE_CAUSES = {
    Cause.REFERENCE_BLANK,
    Cause.REFERENCE_NOT_A_SOW_VALUE,
    Cause.DOC_TYPE_ABSENT,
    Cause.DOC_TYPE_NOT_IN_SOW_TABLE,
}

#: Component spellings column AM uses for a component the rules workbook
#: writes differently. Applied to whole components only, never as substring
#: rewriting, and only inside the diagnostic canonicalisation below.
_COMPONENT_TYPOS = {"MLT": "MTL", "MT": "MTL"}

#: `YES`, however the typist separated it from the rest: `YES-`, `YES/`,
#: `YES `, and the one `YEE-`.
_YES_PREFIX = re.compile(r"^(?:YES|YEE)[-/ ]\s*")

#: SOW components are separated by `/`, and occasionally by `-`.
_SEPARATORS = re.compile(r"[/-]")


def canonical_sow(value: str) -> str:
    """Spelling-insensitive form of a SOW string, for mismatch triage only.

    `YES-MTL/DOC IDB`, `YES/MTL/DOC IDB`, `YES MTL/DOC IDB` and
    `YEE-MTL/DOC IDB` all reduce to the same key; `YES-MTL/DOC IDB` and
    `YES-MTL/BOM/DOC IDB` do not. Components are sorted, so the workbook's
    `YES-FMTL/MTL/DOC IDB` and the sheet's `YES-MTL/FMTL/DOC IDB` agree.

    This is a *diagnostic*. It classifies a mismatch; it never converts one
    into a match, and the resolver never calls it.
    """
    text = normalise(value)
    if not text.startswith(("YES", "YEE")):
        return text
    body = _YES_PREFIX.sub("", text)
    if body == text:                      # a bare 'YES' with no components
        return "YES"
    parts = sorted({
        _COMPONENT_TYPOS.get(p.strip(), p.strip())
        for p in _SEPARATORS.split(body) if p.strip()
    })
    return "YES-" + "/".join(parts)


#: The HIERARCHY component together with the separator that introduces it.
#: Removed with its separator rather than by splitting and rejoining, so the
#: rest of the string keeps the exact punctuation the workbook wrote.
_HIERARCHY_COMPONENT = re.compile(r"[/-]\s*HIERARCHY(?=[/-]|$)|^HIERARCHY[/-]\s*")


def _without_hierarchy(value: str) -> str:
    """The rule's SOW string with its HIERARCHY component removed."""
    return _HIERARCHY_COMPONENT.sub("", normalise(value))


class _ReferenceRow(Protocol):
    """The shape the comparison needs - see infrastructure.excel."""

    source_row: int
    document_no: str
    rev: str
    document_title: str
    doc_type: str
    reference_sow: str


@dataclass
class SowMismatch:
    source_row: int
    document_no: str
    rev: str
    document_title: str
    doc_type: str
    reference_sow: str
    calculated_sow: str
    cause: str
    #: The `DOCUMENT TYPE` sheet row the calculated value came from, or 0.
    rule_row: int = 0
    #: How the resolver reached its answer - see domain.models.sow.
    rule_source: str = ""

    def to_dict(self) -> dict:
        return {
            "source_row": self.source_row,
            "document_no": self.document_no,
            "rev": self.rev,
            "document_title": self.document_title,
            "doc_type": self.doc_type,
            "reference_sow": self.reference_sow,
            "calculated_sow": self.calculated_sow,
            "cause": self.cause,
            "rule_row": self.rule_row,
            "rule_source": self.rule_source,
        }


@dataclass
class SowReport:
    """The Phase 2B reference comparison."""

    rows_evaluated: int = 0
    rows_with_doc_type: int = 0
    rows_with_reference_sow: int = 0
    #: Rows where the resolver produced a value *and* the reference states one.
    #: The denominator of `match_rate`.
    accountable_rows: int = 0
    exact_matches: int = 0
    mismatches: list[SowMismatch] = field(default_factory=list)
    blank_reference_sow: int = 0
    blank_calculated_sow: int = 0
    unknown_doc_type_rows: int = 0
    doc_type_absent_rows: int = 0
    non_sow_reference_rows: int = 0
    cause_counts: dict = field(default_factory=dict)
    calculated_sow_counts: dict = field(default_factory=dict)
    reference_sow_counts: dict = field(default_factory=dict)
    #: (reference -> calculated) value pairs, most frequent first.
    value_drift: list = field(default_factory=list)
    #: DOC TYPE labels the `DOCUMENT TYPE` sheet does not cover, with the
    #: reference SOW values they carry. The Phase 2B rule-gap list.
    unmapped_doc_types: list = field(default_factory=list)
    #: Per-DOKAR agreement, so a systematic divergence is visible per rule.
    per_doc_type: list = field(default_factory=list)

    @property
    def comparable_rows(self) -> int:
        return self.accountable_rows

    @property
    def match_rate(self) -> float:
        """Agreement over rows where both sides state a SOW value."""
        return (self.exact_matches / self.accountable_rows
                if self.accountable_rows else 0.0)

    @property
    def in_scope_mismatches(self) -> list[SowMismatch]:
        out_of_scope = {c.value for c in OUT_OF_SCOPE_CAUSES}
        return [m for m in self.mismatches if m.cause not in out_of_scope]

    def to_dict(self) -> dict:
        return {
            "rows_evaluated": self.rows_evaluated,
            "rows_with_doc_type": self.rows_with_doc_type,
            "rows_with_reference_sow": self.rows_with_reference_sow,
            "accountable_rows": self.accountable_rows,
            "exact_matches": self.exact_matches,
            "mismatches": len(self.in_scope_mismatches),
            "match_rate": round(self.match_rate, 6),
            "blank_reference_sow": self.blank_reference_sow,
            "blank_calculated_sow": self.blank_calculated_sow,
            "unknown_doc_type_rows": self.unknown_doc_type_rows,
            "doc_type_absent_rows": self.doc_type_absent_rows,
            "non_sow_reference_rows": self.non_sow_reference_rows,
            "mismatch_causes": self.cause_counts,
            "value_drift": self.value_drift,
            "unmapped_doc_types": self.unmapped_doc_types,
            "per_doc_type": self.per_doc_type,
            "calculated_sow_counts": self.calculated_sow_counts,
            "reference_sow_counts": self.reference_sow_counts,
            "mismatch_examples": [m.to_dict() for m in self.in_scope_mismatches],
        }


def _classify(reference: str, calculated: str, rule_sow: str) -> Cause:
    """Root cause for one mismatch where both sides state a value."""
    if reference == _without_hierarchy(rule_sow) != rule_sow:
        return Cause.RULE_STATES_HIERARCHY
    if reference == NOT_REQUIRED:
        return Cause.REFERENCE_OVERRIDES_TO_NO
    if canonical_sow(reference) == canonical_sow(calculated):
        return Cause.REFERENCE_SPELLING_VARIANT
    return Cause.RULE_DISAGREES_WITH_REFERENCE


def _is_sow_value(value: str) -> bool:
    """True for a value that states a scope-of-work verdict at all.

    `NO` and anything opening with `YES` (or the one `YEE` typo) qualify;
    `CANCELLED` and `0` do not.
    """
    return value == NOT_REQUIRED or value.startswith(("YES", "YEE"))


def compare_sow(rows: Iterable[_ReferenceRow], resolver: SowResolver,
                max_recorded: int = 2000) -> SowReport:
    """Resolve SOW for every reference row and compare with its column AM."""
    report = SowReport()
    causes: Counter = Counter()
    calculated_counts: Counter = Counter()
    reference_counts: Counter = Counter()
    drift: Counter = Counter()
    unmapped: Counter = Counter()
    per_type: dict[str, Counter] = {}

    for row in rows:
        report.rows_evaluated += 1
        reference = normalise(row.reference_sow)
        doc_type = normalise(row.doc_type)

        # The resolver's entire input is the DOC TYPE. Column AM is read two
        # lines above purely to be compared with the answer.
        requirement = resolver.resolve(row.doc_type)
        calculated = requirement.sow

        calculated_counts[calculated or "(unresolved)"] += 1
        reference_counts[reference or "(blank)"] += 1
        if doc_type:
            report.rows_with_doc_type += 1
        if reference:
            report.rows_with_reference_sow += 1
        if not calculated:
            report.blank_calculated_sow += 1

        # -- rows there is nothing to grade on ----------------------------
        if not reference:
            report.blank_reference_sow += 1
            cause = Cause.REFERENCE_BLANK
        elif not _is_sow_value(reference):
            report.non_sow_reference_rows += 1
            cause = Cause.REFERENCE_NOT_A_SOW_VALUE
        elif not doc_type:
            report.doc_type_absent_rows += 1
            cause = Cause.DOC_TYPE_ABSENT
        elif requirement.source == UNMAPPED_DOC_TYPE:
            report.unknown_doc_type_rows += 1
            unmapped[(doc_type, reference)] += 1
            cause = Cause.DOC_TYPE_NOT_IN_SOW_TABLE
        else:
            # -- rows the resolver is accountable for ---------------------
            report.accountable_rows += 1
            bucket = per_type.setdefault(doc_type, Counter())
            if calculated == reference:
                report.exact_matches += 1
                bucket["match"] += 1
                continue
            bucket["mismatch"] += 1
            drift[(doc_type, reference, calculated)] += 1
            # A self-stating verdict has no `DOCUMENT TYPE` sheet row behind
            # it, so there is no HIERARCHY variant to consider.
            rule_sow = ("" if requirement.source == FROM_NOT_SOW_VERDICT
                        else calculated)
            cause = _classify(reference, calculated, rule_sow)

        causes[cause.value] += 1
        if cause not in OUT_OF_SCOPE_CAUSES and len(report.mismatches) < max_recorded:
            report.mismatches.append(SowMismatch(
                source_row=row.source_row,
                document_no=row.document_no,
                rev=getattr(row, "rev", ""),
                document_title=row.document_title,
                doc_type=doc_type,
                reference_sow=reference,
                calculated_sow=calculated,
                cause=cause.value,
                rule_row=requirement.rule_row,
                rule_source=requirement.source,
            ))

    report.cause_counts = dict(causes)
    report.calculated_sow_counts = dict(calculated_counts.most_common())
    report.reference_sow_counts = dict(reference_counts.most_common())
    report.value_drift = [
        {"doc_type": dt, "reference": ref, "calculated": calc, "rows": n}
        for (dt, ref, calc), n in drift.most_common(60)
    ]
    report.unmapped_doc_types = [
        {"doc_type": dt, "reference_sow": ref, "rows": n}
        for (dt, ref), n in unmapped.most_common(60)
    ]
    report.per_doc_type = sorted(
        ({"doc_type": dt,
          "rows": c["match"] + c["mismatch"],
          "matches": c["match"],
          "mismatches": c["mismatch"]}
         for dt, c in per_type.items()),
        key=lambda d: -d["rows"],
    )
    return report
