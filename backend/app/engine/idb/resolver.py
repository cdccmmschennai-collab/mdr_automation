"""Deciding a document's DOC IDB COMPLETED STATUS (Phase 2C).

The resolver takes the document's Phase 2B `SowRequirement` and, when one
exists, the outcome a completion source recorded for it. It returns an
`IdbStatus`. It never sees a worksheet, a row index, a column letter, a
document number or a title, and it never looks at column AN of the reference
workbook: column AN is the answer this stage is graded against, never an input
to it.

It also does not re-derive scope. The requirement it receives is Phase 2B's
verdict, already decided from the `DOCUMENT TYPE` sheet; re-reading the rules
here would give the pipeline two disagreeing answers about scope. The chain
stays flat:

    document -> 2A -> doc_type -> 2B -> sow -> 2C -> idb

Revision reaches IDB through that chain and by no other route. Phase 1 decides
latest/old, Phase 2A turns an old revision into the DOC TYPE `OLD REV NOT
SOW`, Phase 2B turns that into `NO`, and rule 1 below turns *that* into `NO
NEED TO CHECK` - which is why all 9,934 old-revision rows carry it. There is
no separate old-revision branch here, and none is needed: an old revision that
is still in scope keeps its in-scope status (107 of the 127 such rows read
`COMPLETED`), so a direct latest/old test would be wrong as well as redundant.

A document whose SOW Phase 2B could not resolve produces `UNMAPPED`, not a
guessed status. `NO NEED TO CHECK` is a business statement that a document
needs no IDB check; a missing upstream rule is not.
"""

from __future__ import annotations

from ...domain.models.idb import (
    FROM_COMPLETION_SOURCE, FROM_SOW_NOT_REQUIRED, NO_COMPLETION_SOURCE,
    NO_NEED_TO_CHECK, SOW_NOT_A_VERDICT, TO_BE_CHECK, UNKNOWN_OUTCOME,
    UNMAPPED, UNRESOLVED_SOW, IdbStatus,
)
from ...domain.models.sow import SowRequirement
from .rules import normalise, outcome_of, scope_of


class IdbResolver:
    """Applies the two Phase 2C rules to one document's SOW verdict."""

    def resolve(self, requirement: SowRequirement | None = None,
                recorded_outcome: object = "") -> IdbStatus:
        """Resolve DOC IDB COMPLETED STATUS for one document.

        `requirement` is Phase 2B's `SowRequirement` for the document.

        `recorded_outcome` is what a completion source says about the IDB check
        itself - the IDB folder and the FMTL, which no workbook in this project
        reads. Phase 2C implements no such source, so every run today passes
        nothing and every in-scope document comes back `TO BE CHECK`. The
        parameter exists because the outcome is genuinely an input: it is
        recorded by the person who performed the check and cannot be derived
        from the transmittal log (see `rules` for the evidence). It is only
        consulted for a document that is in scope; an out-of-scope document
        needs no check, so there is no outcome for one to have.
        """
        if requirement is None:
            return IdbStatus()

        sow = normalise(requirement.sow)
        doc_type = normalise(requirement.doc_type)
        required = scope_of(sow)

        if required is None:
            # Either Phase 2B stated nothing, or it stated something that is
            # not a scope verdict. Both are reported, never defaulted.
            source = SOW_NOT_A_VERDICT if sow else UNRESOLVED_SOW
            return IdbStatus(status=UNMAPPED, source=source, sow=sow,
                             doc_type=doc_type)

        if not required:
            # Rule 1. Out of scope, so no IDB check is due. This holds
            # whatever else the row says - cancelled submissions included.
            return IdbStatus(status=NO_NEED_TO_CHECK,
                             source=FROM_SOW_NOT_REQUIRED,
                             sow=sow, doc_type=doc_type)

        # Rule 2. In scope, so a check is due and its outcome is recorded
        # outside this pipeline.
        stated = normalise(recorded_outcome)
        if not stated:
            return IdbStatus(status=TO_BE_CHECK, source=NO_COMPLETION_SOURCE,
                             sow=sow, doc_type=doc_type)

        outcome = outcome_of(stated)
        if not outcome:
            return IdbStatus(status=UNMAPPED, source=UNKNOWN_OUTCOME, sow=sow,
                             doc_type=doc_type, recorded_outcome=stated)

        return IdbStatus(status=outcome, source=FROM_COMPLETION_SOURCE,
                         sow=sow, doc_type=doc_type, recorded_outcome=stated)
