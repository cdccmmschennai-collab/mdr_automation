"""The DOC IDB COMPLETED STATUS verdict (Phase 2C).

An `IdbStatus` is what the IDB resolver decided for one document: the status
string the business writes into column AN of the working sheet, and where that
string came from.

The column conflates two independent facts, and this model keeps them apart:

* **whether an IDB check is needed at all** - decided by the document's
  DOC IS REQUIRED SOW verdict, which Phase 2B already resolves;
* **the outcome of that check** - recorded by whoever performed it against the
  IDB folder and the FMTL, neither of which is in any workbook this project
  reads.

Phase 2C decides the first completely. For the second it carries whatever a
completion source states, and states `TO BE CHECK` when no completion source
has spoken - never a guess at `COMPLETED`.

Pure Python: no Excel, no framework, no row/column coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# -- the vocabulary --------------------------------------------------------
# Every value below is observed in column AN of `QatarEnergy-TN WORKING`. The
# counts are from `docs/business-rules/idb-rules.md`; nothing here is invented.

#: The document's SOW verdict says it is out of scope, so no IDB check is due.
NO_NEED_TO_CHECK = "NO NEED TO CHECK"
#: An IDB check is due and no completion source has recorded its outcome.
TO_BE_CHECK = "TO BE CHECK"
#: The check was performed and the IDB is complete.
COMPLETED = "COMPLETED"
#: Complete, but a newer revision has arrived since - the checker's own note.
COMPLETED_REV_UPDATED = "COMPLETED (REV UPDATED)"
#: The check was performed and the IDB is not complete yet.
PENDING = "PENDING"
#: The submission was cancelled, so the check will not be completed.
CANCELLED = "CANCELLED"
#: The document's tag is absent from the FMTL, so it cannot be checked.
TAG_NOT_IN_FMTL = "TAG NOT IN FMTL"
#: The document is a typical/reference drawing, not a tagged deliverable.
REFERENCE = "REFERENCE"
#: The document is a general specification, not tied to a tag.
GENERAL_SPECIFICATION = "GENERAL SPECIFICATION"

#: No rule and no completion source states a status. Explicitly *not* a
#: business value: it is the engine saying it does not know, and it must never
#: be read as `NO NEED TO CHECK`.
UNMAPPED = "UNMAPPED"

#: The statuses a completed check can produce. A completion source may state
#: any of these; the resolver carries them through and rejects anything else.
CHECK_OUTCOMES: frozenset[str] = frozenset({
    COMPLETED, COMPLETED_REV_UPDATED, PENDING, CANCELLED, TAG_NOT_IN_FMTL,
    REFERENCE, GENERAL_SPECIFICATION, TO_BE_CHECK,
})

#: Every status the engine can emit, including the unknown marker.
IDB_STATUSES: frozenset[str] = CHECK_OUTCOMES | {NO_NEED_TO_CHECK, UNMAPPED}

# -- where a verdict came from ---------------------------------------------

#: Phase 2B resolved the document out of scope (`NO`), so no check is due.
FROM_SOW_NOT_REQUIRED = "SOW_NOT_REQUIRED"
#: Phase 2B resolved the document in scope and a completion source stated the
#: outcome of the check.
FROM_COMPLETION_SOURCE = "COMPLETION_SOURCE"
#: Phase 2B resolved the document in scope and no completion source has
#: spoken. The status is the requirement, not an outcome.
NO_COMPLETION_SOURCE = "NO_COMPLETION_SOURCE"
#: Phase 2B stated no SOW verdict for this document, so whether a check is due
#: is unknown. An upstream rule gap, reported rather than defaulted.
UNRESOLVED_SOW = "UNRESOLVED_SOW"
#: A SOW value arrived that is neither `NO` nor a `YES...` requirement, so it
#: states no scope verdict to act on.
SOW_NOT_A_VERDICT = "SOW_NOT_A_VERDICT"
#: A completion source stated an outcome outside the vocabulary above.
UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"


@dataclass(frozen=True)
class IdbStatus:
    """The DOC IDB COMPLETED STATUS verdict for one document.

    `status` is `UNMAPPED` when neither the rules nor a completion source
    establishes a value. It is never blank and never silently `NO NEED TO
    CHECK`: a rule gap and an out-of-scope document are different business
    facts.
    """

    status: str = UNMAPPED
    source: str = UNRESOLVED_SOW
    #: The DOC IS REQUIRED SOW string this verdict was derived from, carried
    #: verbatim for audit. Empty when Phase 2B resolved nothing.
    sow: str = ""
    #: The DOC TYPE that produced that SOW value, carried for audit.
    doc_type: str = ""
    #: What a completion source stated, before it was accepted or rejected.
    #: Empty when no completion source spoke - which is every run today.
    recorded_outcome: str = ""

    @property
    def is_resolved(self) -> bool:
        """True when the engine states an actual IDB status."""
        return self.status != UNMAPPED

    @property
    def check_required(self) -> Optional[bool]:
        """Whether an IDB check is due: True / False, or None when unknown.

        This is the half of column AN that Phase 2C decides on its own. It is
        three-valued for the same reason `SowRequirement.is_required` is: an
        unresolved document is not a document that needs no check.
        """
        if not self.is_resolved:
            return None
        return self.status != NO_NEED_TO_CHECK

    @property
    def outcome_known(self) -> bool:
        """True when a completion source stated the outcome of the check."""
        return self.source == FROM_COMPLETION_SOURCE

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "source": self.source,
            "sow": self.sow,
            "doc_type": self.doc_type,
            "recorded_outcome": self.recorded_outcome,
            "check_required": self.check_required,
            "outcome_known": self.outcome_known,
        }
