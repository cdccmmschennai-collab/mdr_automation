"""DOC IDB COMPLETED STATUS validation against the reference working file.

Column AN of `QatarEnergy-TN WORKING` is the manual result Phase 2C automates,
so it doubles as ground truth. It is a *partial* target, and the report below
says so rather than tuning the engine until the number looks good:

* 18,706 of its 21,372 rows read `NO NEED TO CHECK`, and every one of them is
  a row whose DOC IS REQUIRED SOW reads `NO`. That half of the column is a
  rule, and the engine reproduces it.
* The other half - `COMPLETED`, `PENDING`, `TO BE CHECK` and the rarer values
  - records the outcome of a check performed against the IDB folder and the
  FMTL. Neither is in any workbook this project reads, and no column in the
  transmittal log predicts which value a row gets. The engine therefore
  answers `TO BE CHECK` and the mismatch is reported as a missing input, not
  as an engine defect.
* Column AN is hand-typed and carries spelling variants (`COMPLETE`, `REF`)
  and non-status entries (`0`, blank).

Mismatches are classified by root cause, and the report separates two very
different questions:

* `match_rate` - does the engine reproduce column AN exactly?
* `requirement_rate` - does the engine agree about *whether a check is due*?
  That is the half of the column Phase 2C actually decides, and it is the
  number to read when asking whether the Phase 2C rules are right.

The spelling canonicalisation below exists **only to sort mismatches into
causes** - it never touches the value Phase 2C computes, and a canonical-only
agreement is counted as a mismatch, not as a match.

Nothing here writes to the reference workbook, and column AN is never fed to
either resolver: `compare_idb` calls `sow_resolver.resolve(row.doc_type)` and
`idb_resolver.resolve(requirement)`, which is the whole of their input.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Protocol

from ...domain.models.idb import (
    CANCELLED, COMPLETED, COMPLETED_REV_UPDATED, GENERAL_SPECIFICATION,
    NO_NEED_TO_CHECK, PENDING, REFERENCE, TAG_NOT_IN_FMTL, TO_BE_CHECK,
    UNMAPPED,
)
from ...domain.models.sow import NOT_REQUIRED
from ..idb.resolver import IdbResolver
from ..idb.rules import normalise, outcome_of
from ..sow.resolver import SowResolver


class Cause(str, Enum):
    """Root cause of an engine-vs-reference IDB mismatch."""

    #: Column AN is empty - no ground truth for this row.
    REFERENCE_BLANK = "REFERENCE_BLANK"
    #: Column AN holds something that is not an IDB status at all (`0`). A
    #: workbook data-entry state, not a rule.
    REFERENCE_NOT_AN_IDB_VALUE = "REFERENCE_NOT_AN_IDB_VALUE"
    #: Phase 2B stated no SOW verdict for the row's DOC TYPE, so Phase 2C
    #: cannot say whether a check is due. A Phase 2B rule gap reaching
    #: Phase 2C, reported here and fixed there or not at all.
    UPSTREAM_SOW_UNRESOLVED = "UPSTREAM_SOW_UNRESOLVED"
    #: The document is in scope, the reference records the outcome of a check
    #: that was performed, and no completion source told the engine about it.
    #: A missing input, not a wrong rule - see the module docstring.
    COMPLETION_EVIDENCE_NOT_AVAILABLE = "COMPLETION_EVIDENCE_NOT_AVAILABLE"
    #: The reference value is a human judgement or needs data outside this
    #: project entirely (`GENERAL SPECIFICATION`, `REFERENCE`, `TAG NOT IN
    #: FMTL`). No completion source this project could build would generate
    #: it from the transmittal log.
    REFERENCE_VALUE_NOT_GENERATABLE = "REFERENCE_VALUE_NOT_GENERATABLE"
    #: The reference names a vocabulary value and differs only in spelling
    #: (`COMPLETE`, `REF`).
    REFERENCE_SPELLING_VARIANT = "REFERENCE_SPELLING_VARIANT"
    #: The `DOCUMENT TYPE` sheet puts the row's DOC TYPE in scope, the working
    #: sheet's own column AM overrides it to `NO`, and column AN follows
    #: column AM. Phase 2B already records this contradiction as
    #: `REFERENCE_OVERRIDES_TO_NO`; it reaches Phase 2C unchanged. Fixing it
    #: means deciding the SOW rule, not the IDB rule.
    UPSTREAM_SOW_OVERRIDDEN = "UPSTREAM_SOW_OVERRIDDEN"
    #: Engine and reference disagree about whether an IDB check is due, and no
    #: cause above explains it. This is the only cause that questions the
    #: Phase 2C rules themselves.
    RULE_DISAGREES_WITH_REFERENCE = "RULE_DISAGREES_WITH_REFERENCE"


#: Causes that say nothing about whether the resolver is right, because either
#: side of the comparison is missing.
OUT_OF_SCOPE_CAUSES = {
    Cause.REFERENCE_BLANK,
    Cause.REFERENCE_NOT_AN_IDB_VALUE,
    Cause.UPSTREAM_SOW_UNRESOLVED,
}

#: Reference spellings of a vocabulary value. Observed in column AN; applied
#: to whole values only, and only inside the diagnostic canonicalisation
#: below. The resolver never calls this.
_REFERENCE_VARIANTS = {
    "COMPLETE": COMPLETED,
    "REF": REFERENCE,
}

#: Reference values no rule and no completion source built from the
#: transmittal log could produce: two are human judgements about the document
#: itself, the third needs the FMTL.
NOT_GENERATABLE = frozenset({
    GENERAL_SPECIFICATION, REFERENCE, TAG_NOT_IN_FMTL,
})

#: Reference values that record the outcome of a check somebody performed.
RECORDED_OUTCOMES = frozenset({
    COMPLETED, COMPLETED_REV_UPDATED, PENDING, CANCELLED,
})


def canonical_status(value: str) -> str:
    """Spelling-insensitive form of an IDB status, for mismatch triage only.

    `COMPLETE` and `COMPLETED` reduce to the same key; `COMPLETED` and
    `COMPLETED (REV UPDATED)` do not. This is a *diagnostic*: it classifies a
    mismatch, it never converts one into a match, and the resolver never calls
    it.
    """
    text = normalise(value)
    return _REFERENCE_VARIANTS.get(text, text)


def is_idb_status(value: str) -> bool:
    """True for a value that states an IDB status at all.

    The vocabulary plus the two observed spelling variants. `0` and blank do
    not qualify.
    """
    text = normalise(value)
    return bool(text) and (text == NO_NEED_TO_CHECK
                           or bool(outcome_of(canonical_status(text))))


def reference_requires_check(value: str) -> bool:
    """Whether a reference status says an IDB check is due for the row.

    Everything except `NO NEED TO CHECK` does: `COMPLETED` says one was done,
    `PENDING` and `TO BE CHECK` that one is outstanding. This is the axis
    Phase 2C decides, so it is the axis `requirement_rate` is measured on.
    """
    return normalise(value) != NO_NEED_TO_CHECK


class _ReferenceRow(Protocol):
    """The shape the comparison needs - see infrastructure.excel.

    `reference_sow` is read for triage only: it distinguishes a Phase 2C rule
    error from Phase 2B's already-documented column AM override. Like
    `reference_idb`, it never reaches a resolver.
    """

    source_row: int
    document_no: str
    rev: str
    document_title: str
    doc_type: str
    reference_sow: str
    reference_idb: str


@dataclass
class IdbMismatch:
    source_row: int
    document_no: str
    rev: str
    document_title: str
    doc_type: str
    calculated_sow: str
    reference_sow: str
    reference_idb: str
    calculated_idb: str
    cause: str
    #: How the resolver reached its answer - see domain.models.idb.
    rule_source: str = ""

    def to_dict(self) -> dict:
        return {
            "source_row": self.source_row,
            "document_no": self.document_no,
            "rev": self.rev,
            "document_title": self.document_title,
            "doc_type": self.doc_type,
            "calculated_sow": self.calculated_sow,
            "reference_sow": self.reference_sow,
            "reference_idb": self.reference_idb,
            "calculated_idb": self.calculated_idb,
            "cause": self.cause,
            "rule_source": self.rule_source,
        }


@dataclass
class IdbReport:
    """The Phase 2C reference comparison."""

    rows_evaluated: int = 0
    rows_with_doc_type: int = 0
    rows_with_reference_idb: int = 0
    #: Rows where the resolver produced a status *and* the reference states
    #: one. The denominator of `match_rate`.
    accountable_rows: int = 0
    exact_matches: int = 0
    #: Every accountable row where the two values differ. Counted in full,
    #: unlike `recorded_mismatches`, which is capped for report size.
    in_scope_mismatch_count: int = 0
    #: Example mismatches, capped per cause so the rarest cause is still
    #: illustrated. A sample, never a total - `in_scope_mismatch_count` is.
    recorded_mismatches: list[IdbMismatch] = field(default_factory=list)
    #: Of the accountable rows, those where engine and reference agree about
    #: whether a check is due. The denominator is `accountable_rows`.
    requirement_matches: int = 0
    blank_reference_idb: int = 0
    #: Rows where the engine emitted nothing at all. Structurally zero: the
    #: resolver always states a status or `UNMAPPED`.
    blank_calculated_idb: int = 0
    unmapped_calculated_idb: int = 0
    non_idb_reference_rows: int = 0
    upstream_unresolved_rows: int = 0
    cause_counts: dict = field(default_factory=dict)
    calculated_idb_counts: dict = field(default_factory=dict)
    reference_idb_counts: dict = field(default_factory=dict)
    #: (reference -> calculated) value pairs, most frequent first.
    value_drift: list = field(default_factory=list)
    #: DOC TYPE labels whose SOW Phase 2B does not resolve, with the reference
    #: IDB values they carry. The Phase 2C view of the Phase 2B rule gap.
    upstream_unresolved_doc_types: list = field(default_factory=list)
    #: Per-DOC TYPE agreement, so a systematic divergence is visible per rule.
    per_doc_type: list = field(default_factory=list)

    @property
    def match_rate(self) -> float:
        """Exact agreement over rows where both sides state a status."""
        return (self.exact_matches / self.accountable_rows
                if self.accountable_rows else 0.0)

    @property
    def requirement_rate(self) -> float:
        """Agreement about whether a check is due - the Phase 2C rule axis."""
        return (self.requirement_matches / self.accountable_rows
                if self.accountable_rows else 0.0)

    def to_dict(self) -> dict:
        return {
            "rows_evaluated": self.rows_evaluated,
            "rows_with_doc_type": self.rows_with_doc_type,
            "rows_with_reference_idb": self.rows_with_reference_idb,
            "accountable_rows": self.accountable_rows,
            "exact_matches": self.exact_matches,
            "mismatches": self.in_scope_mismatch_count,
            "recorded_mismatches": len(self.recorded_mismatches),
            "match_rate": round(self.match_rate, 6),
            "requirement_matches": self.requirement_matches,
            "requirement_rate": round(self.requirement_rate, 6),
            "blank_reference_idb": self.blank_reference_idb,
            "blank_calculated_idb": self.blank_calculated_idb,
            "unmapped_calculated_idb": self.unmapped_calculated_idb,
            "non_idb_reference_rows": self.non_idb_reference_rows,
            "upstream_unresolved_rows": self.upstream_unresolved_rows,
            "mismatch_causes": self.cause_counts,
            "value_drift": self.value_drift,
            "upstream_unresolved_doc_types": self.upstream_unresolved_doc_types,
            "per_doc_type": self.per_doc_type,
            "calculated_idb_counts": self.calculated_idb_counts,
            "reference_idb_counts": self.reference_idb_counts,
            "mismatch_examples": [m.to_dict() for m in self.recorded_mismatches],
        }


def _classify(reference: str, calculated: str, reference_sow: str) -> Cause:
    """Root cause for one mismatch where both sides state a status."""
    if canonical_status(reference) != reference:
        return Cause.REFERENCE_SPELLING_VARIANT
    if reference in NOT_GENERATABLE:
        return Cause.REFERENCE_VALUE_NOT_GENERATABLE
    if calculated == TO_BE_CHECK and reference in RECORDED_OUTCOMES:
        return Cause.COMPLETION_EVIDENCE_NOT_AVAILABLE
    if (calculated == TO_BE_CHECK and reference == NO_NEED_TO_CHECK
            and normalise(reference_sow) == NOT_REQUIRED):
        return Cause.UPSTREAM_SOW_OVERRIDDEN
    return Cause.RULE_DISAGREES_WITH_REFERENCE


def compare_idb(rows: Iterable[_ReferenceRow], sow_resolver: SowResolver,
                idb_resolver: IdbResolver,
                max_per_cause: int = 250) -> IdbReport:
    """Resolve IDB for every reference row and compare with its column AN.

    The chain run here is the real one: the reference's DOC TYPE goes to the
    SOW resolver, whose `SowRequirement` goes to the IDB resolver. No
    completion source is supplied, because none exists - so every in-scope row
    comes back `TO BE CHECK`, and the report says how many rows that leaves
    depending on an input Phase 2C does not have.

    Examples are capped *per cause* rather than overall. A flat cap would fill
    up on the largest group and leave the smallest - the two rows that
    actually question the rules - with no example to look at.
    """
    report = IdbReport()
    causes: Counter = Counter()
    recorded: Counter = Counter()
    calculated_counts: Counter = Counter()
    reference_counts: Counter = Counter()
    drift: Counter = Counter()
    unresolved: Counter = Counter()
    per_type: dict[str, Counter] = {}

    for row in rows:
        report.rows_evaluated += 1
        reference = normalise(row.reference_idb)
        doc_type = normalise(row.doc_type)

        # The engine's entire input is the DOC TYPE, by way of Phase 2B.
        # Column AN is read two lines above purely to be compared with the
        # answer, and reaches neither resolver.
        requirement = sow_resolver.resolve(row.doc_type)
        status = idb_resolver.resolve(requirement)
        calculated = status.status

        calculated_counts[calculated] += 1
        reference_counts[reference or "(blank)"] += 1
        if doc_type:
            report.rows_with_doc_type += 1
        if reference:
            report.rows_with_reference_idb += 1
        if not calculated:
            report.blank_calculated_idb += 1
        if calculated == UNMAPPED:
            report.unmapped_calculated_idb += 1

        # -- rows there is nothing to grade on ----------------------------
        if not reference:
            report.blank_reference_idb += 1
            cause = Cause.REFERENCE_BLANK
        elif not is_idb_status(reference):
            report.non_idb_reference_rows += 1
            cause = Cause.REFERENCE_NOT_AN_IDB_VALUE
        elif calculated == UNMAPPED:
            report.upstream_unresolved_rows += 1
            unresolved[(doc_type, reference)] += 1
            cause = Cause.UPSTREAM_SOW_UNRESOLVED
        else:
            # -- rows the resolver is accountable for ---------------------
            report.accountable_rows += 1
            bucket = per_type.setdefault(doc_type, Counter())
            if status.check_required == reference_requires_check(reference):
                report.requirement_matches += 1
                bucket["requirement_match"] += 1
            if calculated == reference:
                report.exact_matches += 1
                bucket["match"] += 1
                continue
            bucket["mismatch"] += 1
            drift[(doc_type, reference, calculated)] += 1
            cause = _classify(reference, calculated,
                              getattr(row, "reference_sow", ""))

        causes[cause.value] += 1
        if cause in OUT_OF_SCOPE_CAUSES:
            continue
        report.in_scope_mismatch_count += 1
        recorded[cause.value] += 1
        if recorded[cause.value] <= max_per_cause:
            report.recorded_mismatches.append(IdbMismatch(
                source_row=row.source_row,
                document_no=row.document_no,
                rev=getattr(row, "rev", ""),
                document_title=row.document_title,
                doc_type=doc_type,
                calculated_sow=status.sow,
                reference_sow=normalise(getattr(row, "reference_sow", "")),
                reference_idb=reference,
                calculated_idb=calculated,
                cause=cause.value,
                rule_source=status.source,
            ))

    report.cause_counts = dict(causes)
    report.calculated_idb_counts = dict(calculated_counts.most_common())
    report.reference_idb_counts = dict(reference_counts.most_common())
    report.value_drift = [
        {"doc_type": dt, "reference": ref, "calculated": calc, "rows": n}
        for (dt, ref, calc), n in drift.most_common(60)
    ]
    report.upstream_unresolved_doc_types = [
        {"doc_type": dt, "reference_idb": ref, "rows": n}
        for (dt, ref), n in unresolved.most_common(60)
    ]
    report.per_doc_type = sorted(
        ({"doc_type": dt,
          "rows": c["match"] + c["mismatch"],
          "matches": c["match"],
          "mismatches": c["mismatch"],
          "requirement_matches": c["requirement_match"]}
         for dt, c in per_type.items()),
        key=lambda d: -d["rows"],
    )
    return report
