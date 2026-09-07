"""What removes a document row from latest-revision candidacy.

Two free-text signals were examined against the reference data. One is applied;
the other is deliberately NOT applied and is retained as context only. Both are
isolated here so the evidence behind each stays next to the rule.
"""

from __future__ import annotations

import re

#: Free-text markers that withdraw a submission from latest candidacy.
#: Evidenced by 4391-MTY-4-15-0004 rev A (status 'WITHDRAWIN'), the single
#: genuine counter-example to the revision ordering in the reference data.
WITHDRAWN_MARKERS = ("WITHDRAW",)

#: Remarks noting that the document was renumbered or reclassified as
#: non-deliverable.
#:
#: This is recorded as CONTEXT ONLY and deliberately does NOT affect latest
#: determination. It was tested as an exclusion rule and rejected: of the 182
#: rows it matches, 128 are NL and 50 are L against a 64% NL base rate, so it
#: carries almost no signal - and in every case examined the renumbered row was
#: itself the one the workbook marked latest. Useful for exception review and
#: for the later identity/DOC TYPE phases; not a revision rule.
RENUMBERED_RE = re.compile(
    r"(DOC(?:UMENT)?\.?\s*(?:REF\.?\s*)?NO\.?[^.]{0,30}?"
    r"(?:UPDATED|CHANGED|REVISED))"
    r"|(?:NUMBER\s+REVISED)"
    r"|(NON[-\s]?DELIVERABLE)",
    re.IGNORECASE,
)


def is_withdrawn(status_text: str, remarks: str) -> bool:
    """True when the status or remarks withdraw this submission.

    Both fields are searched together, upper-cased, exactly as the Phase 1
    engine has always done.
    """
    haystack = f"{status_text} {remarks}".upper()
    return any(marker in haystack for marker in WITHDRAWN_MARKERS)


def has_renumbering_note(remarks: str) -> bool:
    """True when the remarks say the document was renumbered.

    Informational only - see RENUMBERED_RE. Callers must not use this to
    exclude a row from latest determination.
    """
    return bool(RENUMBERED_RE.search(remarks))
