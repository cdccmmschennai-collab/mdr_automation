"""The five MDR automation columns for one workbook row (Phase 2D).

`AutomationRow` is what the automation states about one QatarEnergy-TN row:
the four values the engines resolved, and the fifth column the engines
deliberately do not resolve yet.

The captions below are the spellings the business already uses in
`QatarEnergy-TN WORKING`; they are copied verbatim so an employee reading the
generated sheet sees the same words as in their own working file.

**CHECK STATUS is structurally blank.** It is the only one of the five that no
engine feeds. Deciding it needs the received-document dump - search the
received files, match identity, match revision, judge applicability - and no
such dump exists for this project yet (`data/received/` is empty). A blank
cell therefore means *"not evaluated"*, and it must never be read as `NOT
RECEIVED`: absence of a dump is not evidence that a document was not received.
The dataclass refuses to be constructed with a value in it, so no later change
can quietly start filling the column without deleting that rule first.

Pure Python: no Excel, no framework, no row/column coordinates beyond
`source_row`, which is retained so a human can find the row again.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- the five captions, spelled as the working file spells them -------------

DOC_WITH_REV = "DOC WITH REV"
DOC_TYPE = "DOC TYPE"
DOC_IS_REQUIRED_SOW = "DOC IS REQUIRED SOW"
DOC_IDB_COMPLETED_STATUS = "DOC IDB COMPLETED STATUS"
CHECK_STATUS = "CHECK STATUS"

#: The five automation columns, in the order the business reads them.
AUTOMATION_COLUMNS: tuple[str, ...] = (
    DOC_WITH_REV, DOC_TYPE, DOC_IS_REQUIRED_SOW, DOC_IDB_COMPLETED_STATUS,
    CHECK_STATUS,
)

#: What Phase 2D writes into CHECK STATUS: nothing at all. Not `NOT RECEIVED`,
#: not `#N/A`, not a copy of whatever a previous manual workbook held.
CHECK_STATUS_NOT_EVALUATED = ""

#: What Phase 2D writes into DOC IDB COMPLETED STATUS for a document that *is*
#: required: nothing at all, meaning **a person must still check it**.
#:
#: Phase 2C decides the half of the column it can - whether a check is due -
#: and says `TO BE CHECK` for a document in scope that nobody has checked. But
#: the column the employee actually works from records the *outcome* of that
#: check, and no completion source exists to state one. A blank cell is the
#: instruction to go and look; any word written there would be an answer the
#: automation has not earned, `TO BE CHECK` included.
#:
#: Out-of-scope documents are different: `NO NEED TO CHECK` is a conclusion
#: that follows from the SOW verdict alone, so it is written.
MANUAL_CHECK_REQUIRED = ""


class CheckStatusNotEvaluated(ValueError):
    """Raised when something tries to give CHECK STATUS a value in Phase 2D."""


@dataclass(frozen=True)
class AutomationRow:
    """The five automation values for one source row.

    Each of the first four carries whatever its engine decided, verbatim -
    including the empty string Phase 2B uses for "no rule covers this DOC
    TYPE" and the `UNMAPPED` marker Phase 2C uses for "no scope verdict to act
    on". Neither is repaired into a business value here; an unknown that reads
    as a decision is worse than an unknown that reads as blank.
    """

    source_row: int
    doc_with_rev: str = ""          # Phase 1
    doc_type: str = ""              # Phase 2A
    sow: str = ""                   # Phase 2B
    idb_status: str = ""            # Phase 2C
    check_status: str = CHECK_STATUS_NOT_EVALUATED   # Phase 3B - not yet

    # -- provenance, for audit and for the CSV/JSON artefacts --------------
    #: Which keyword rule decided `doc_type`.
    doc_type_rule: str = ""
    #: `SowRequirement.source` - where the SOW verdict came from.
    sow_source: str = ""
    #: `IdbStatus.source` - where the IDB verdict came from.
    idb_source: str = ""

    def __post_init__(self) -> None:
        if self.check_status != CHECK_STATUS_NOT_EVALUATED:
            raise CheckStatusNotEvaluated(
                f"CHECK STATUS is not evaluated until the received-document "
                f"dump exists (Phase 3A/3B); refusing {self.check_status!r} "
                f"for source row {self.source_row}"
            )

    @property
    def values(self) -> tuple[str, ...]:
        """The five cell values, in `AUTOMATION_COLUMNS` order."""
        return (self.doc_with_rev, self.doc_type, self.sow, self.idb_status,
                self.check_status)

    def to_dict(self) -> dict:
        return {
            "source_row": self.source_row,
            "doc_with_rev": self.doc_with_rev,
            "doc_type": self.doc_type,
            "sow": self.sow,
            "idb_status": self.idb_status,
            "check_status": self.check_status,
            "doc_type_rule": self.doc_type_rule,
            "sow_source": self.sow_source,
            "idb_source": self.idb_source,
        }
