"""DOC TYPE validation against the reference working file.

Column AL of `QatarEnergy-TN WORKING` is the manual result Phase 2A automates,
so it doubles as ground truth. A single agreement percentage would be
misleading, for a reason that is visible in the data itself: **column AL does
not hold DOC TYPE alone**. Of 21,372 rows, 9,934 read `OLD REV NOT SOW`, 3,648
`NOT SOW` and 4,411 `OTHER` - revision and scope-of-work verdicts belonging to
later phases, not document types. Only about 3,356 rows carry a value the
classifier is even being asked to produce.

Mismatches are therefore classified by root cause, and the headline rate is
quoted over the rows Phase 2A is accountable for. Nothing here writes to the
reference workbook, and column AL is never fed to the classifier as an input.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Protocol

from ..classification.classifier import DocumentClassifier
from ..classification.rules import normalise


class Cause(str, Enum):
    """Root cause of an engine-vs-reference DOC TYPE mismatch."""

    #: Column AL holds a scope-of-work / revision verdict rather than a
    #: document type (`OLD REV NOT SOW`, `NOT SOW`, `OTHER`, `NO`). Those
    #: belong to Phase 2B+; Phase 2A has nothing to compare against.
    REFERENCE_NOT_A_DOC_TYPE = "REFERENCE_NOT_A_DOC_TYPE"
    #: Column AL is empty - no ground truth for this row.
    REFERENCE_BLANK = "REFERENCE_BLANK"
    #: The reference names a document type but no keyword rule covers the
    #: document. A gap in the rule set, not a wrong rule.
    NO_RULE_MATCHED = "NO_RULE_MATCHED"
    #: Several rules matched and the reference's answer was among the ones
    #: precedence rejected. A precedence question, not a missing rule.
    COMPETING_RULES = "COMPETING_RULES"
    #: A rule matched cleanly and the reference says something else no matched
    #: rule produced: vocabulary drift between the rules workbook and the
    #: manually maintained column, or a manual classification.
    RULE_DISAGREES_WITH_REFERENCE = "RULE_DISAGREES_WITH_REFERENCE"


#: Column AL values that are verdicts from later phases, not document types.
#: Confirmed absent from every DOC TYPE cell in the rules workbook.
NON_DOC_TYPE_VERDICTS = frozenset({"OLD REV NOT SOW", "NOT SOW", "OTHER", "NO"})

#: Causes that say nothing about whether the classifier is right, because the
#: reference offers no DOC TYPE to compare with.
OUT_OF_SCOPE_CAUSES = {Cause.REFERENCE_NOT_A_DOC_TYPE, Cause.REFERENCE_BLANK}


class _ReferenceRow(Protocol):
    """The shape the comparison needs - see infrastructure.excel."""

    source_row: int
    document_no: str
    document_title: str
    latest_flag: str
    doc_type: str


@dataclass
class DocTypeMismatch:
    source_row: int
    document_no: str
    document_title: str
    reference_doc_type: str
    engine_doc_type: str
    cause: str
    latest_flag: str = ""
    matched_rules: list = field(default_factory=list)
    competing_doc_types: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_row": self.source_row,
            "document_no": self.document_no,
            "document_title": self.document_title,
            "reference_doc_type": self.reference_doc_type,
            "engine_doc_type": self.engine_doc_type,
            "cause": self.cause,
            "latest_flag": self.latest_flag,
            "matched_rules": self.matched_rules,
            "competing_doc_types": self.competing_doc_types,
        }


@dataclass
class DocTypeReport:
    """The Phase 2A reference comparison."""

    rows_evaluated: int = 0
    rows_with_reference_doc_type: int = 0
    exact_matches: int = 0
    mismatches: list[DocTypeMismatch] = field(default_factory=list)
    blank_reference_rows: int = 0
    non_doc_type_reference_rows: int = 0
    blank_engine_rows: int = 0
    unclassified_rows: int = 0
    cause_counts: dict = field(default_factory=dict)
    ambiguous_rows: int = 0
    engine_doc_type_counts: dict = field(default_factory=dict)
    reference_doc_type_counts: dict = field(default_factory=dict)
    #: (reference -> engine) label pairs, most frequent first. Surfaces
    #: vocabulary drift without any equivalence table being assumed.
    label_drift: list = field(default_factory=list)
    #: How `LATEST/ NOT LATEST` and column AL interact - a Phase 2B input.
    latest_flag_interaction: dict = field(default_factory=dict)

    @property
    def comparable_rows(self) -> int:
        """Rows where the reference actually states a document type."""
        return self.rows_with_reference_doc_type

    @property
    def match_rate(self) -> float:
        """Agreement over rows the reference states a document type for."""
        return (self.exact_matches / self.comparable_rows
                if self.comparable_rows else 0.0)

    @property
    def in_scope_mismatches(self) -> list[DocTypeMismatch]:
        out_of_scope = {c.value for c in OUT_OF_SCOPE_CAUSES}
        return [m for m in self.mismatches if m.cause not in out_of_scope]

    def to_dict(self) -> dict:
        return {
            "rows_evaluated": self.rows_evaluated,
            "rows_with_reference_doc_type": self.rows_with_reference_doc_type,
            "exact_matches": self.exact_matches,
            "mismatches": len(self.in_scope_mismatches),
            "match_rate": round(self.match_rate, 6),
            "blank_reference_rows": self.blank_reference_rows,
            "non_doc_type_reference_rows": self.non_doc_type_reference_rows,
            "blank_engine_rows": self.blank_engine_rows,
            "unclassified_rows": self.unclassified_rows,
            "ambiguous_rows": self.ambiguous_rows,
            "mismatch_causes": self.cause_counts,
            "label_drift": self.label_drift,
            "latest_flag_interaction": self.latest_flag_interaction,
            "engine_doc_type_counts": self.engine_doc_type_counts,
            "reference_doc_type_counts": self.reference_doc_type_counts,
            "mismatch_examples": [m.to_dict()
                                  for m in self.in_scope_mismatches],
        }


def compare_doc_types(rows: Iterable[_ReferenceRow],
                      classifier: DocumentClassifier,
                      max_recorded: int = 2000) -> DocTypeReport:
    """Classify every reference row and compare with its column AL value."""
    report = DocTypeReport()
    causes: Counter = Counter()
    engine_counts: Counter = Counter()
    reference_counts: Counter = Counter()
    drift: Counter = Counter()
    interaction: Counter = Counter()

    for row in rows:
        report.rows_evaluated += 1
        reference = normalise(row.doc_type)
        result = classifier.classify(row.document_no, row.document_title)
        engine = result.doc_type

        engine_counts[engine or "(unclassified)"] += 1
        reference_counts[reference or "(blank)"] += 1
        if not reference:
            kind = "(blank)"
        elif reference in NON_DOC_TYPE_VERDICTS:
            kind = reference
        else:
            kind = "(doc type)"
        interaction[(row.latest_flag or "(blank)", kind)] += 1

        if not engine:
            report.blank_engine_rows += 1
            report.unclassified_rows += 1
        if result.is_ambiguous:
            report.ambiguous_rows += 1

        if not reference:
            report.blank_reference_rows += 1
            cause = Cause.REFERENCE_BLANK
        elif reference in NON_DOC_TYPE_VERDICTS:
            report.non_doc_type_reference_rows += 1
            cause = Cause.REFERENCE_NOT_A_DOC_TYPE
        else:
            report.rows_with_reference_doc_type += 1
            if engine == reference:
                report.exact_matches += 1
                continue
            drift[(reference, engine or "(unclassified)")] += 1
            if not engine:
                cause = Cause.NO_RULE_MATCHED
            elif reference in result.competing_doc_types:
                cause = Cause.COMPETING_RULES
            else:
                cause = Cause.RULE_DISAGREES_WITH_REFERENCE

        causes[cause.value] += 1
        # Only rows the reference states a document type for are recorded
        # individually; the out-of-scope rows are counted, not listed, or the
        # cap would fill with rows there is nothing to compare on.
        if cause not in OUT_OF_SCOPE_CAUSES and len(report.mismatches) < max_recorded:
            report.mismatches.append(DocTypeMismatch(
                source_row=row.source_row,
                document_no=row.document_no,
                document_title=row.document_title,
                reference_doc_type=reference,
                engine_doc_type=engine,
                cause=cause.value,
                latest_flag=row.latest_flag,
                matched_rules=[m.describe() for m in result.matches],
                competing_doc_types=list(result.competing_doc_types),
            ))

    report.cause_counts = dict(causes)
    report.engine_doc_type_counts = dict(engine_counts.most_common())
    report.reference_doc_type_counts = dict(reference_counts.most_common())
    report.label_drift = [
        {"reference": ref, "engine": eng, "rows": n}
        for (ref, eng), n in drift.most_common(40)
    ]
    report.latest_flag_interaction = {
        f"{flag} / {kind}": n for (flag, kind), n in interaction.most_common()
    }
    return report
