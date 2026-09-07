"""Status Code domain vocabulary.

The QatarEnergy review codes (CODE-1..CODE-11) and the issue/PDMS codes
(IFC, IFA, AFC, ASB, ...) as domain value objects, plus the enumerations that
describe where a row sits in the revision lifecycle and how a vendor row
resolved against QatarEnergy.

`ReviewCode` / `IssueCode` instances are *loaded from the workbook's own Status
Codes sheet* by `engine.revision.status_codes.StatusCodeBook` - they are never
hard-coded here, so a revised sheet changes behaviour without a code change.
This module owns only their semantics.

Depends on nothing outside the standard library: no FastAPI, no openpyxl, no
engine imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

#: Issue codes whose revision sequence is alphabetic, per the Status Codes sheet.
_ALPHA_SEQUENCE_RE = re.compile(r"\bA\s*,\s*B\s*,\s*C", re.IGNORECASE)
#: Issue codes whose revision sequence is numeric.
_NUMERIC_SEQUENCE_RE = re.compile(r"\b0\b|\b1\s*,\s*2\s*,\s*3", re.IGNORECASE)


class RevisionStatus(str):
    """Lifecycle position the engine assigns to a document row.

    Kept as a `str` subclass carrying class attributes rather than an `Enum`,
    because the values are compared against - and serialised as - plain strings
    throughout Phase 1. Changing this to an Enum would change the emitted JSON.
    """

    LATEST = "LATEST"
    OLD = "OLD"
    #: An as-built (Z) issue. A known, well-understood category that sits
    #: outside the A,B,C.. sequence - not an error needing review.
    AS_BUILT = "AS_BUILT"
    EXCEPTION = "EXCEPTION"


class MatchStatus(str, Enum):
    """Outcome of resolving a vendor row against the QatarEnergy documents."""

    EXACT = "EXACT"
    NORMALIZED_EXACT = "NORMALIZED_EXACT"
    ALTERNATIVE_IDENTIFIER = "ALTERNATIVE_IDENTIFIER"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_MATCHED = "NOT_MATCHED"
    NO_IDENTIFIER = "NO_IDENTIFIER"


@dataclass(frozen=True)
class ReviewCode:
    """A QatarEnergy review code, e.g. CODE-2."""

    code: str
    description: str

    @property
    def number(self) -> Optional[int]:
        m = re.search(r"(\d+)", self.code)
        return int(m.group(1)) if m else None

    @property
    def requires_resubmission(self) -> bool:
        """CODE-1/2/3 all call for a resubmission; 6/7/10/11 do not."""
        return self.number in (1, 2, 3)

    @property
    def work_may_proceed(self) -> bool:
        return self.number in (1, 2, 10)

    @property
    def is_cancellation(self) -> bool:
        return self.number == 11


@dataclass(frozen=True)
class IssueCode:
    """An issue/PDMS status code, e.g. IFA, RE-AFC, ASB."""

    code: str
    description: str
    revision_sequence: str

    @property
    def base_code(self) -> str:
        """'RE-IFA' -> 'IFA'. Re-issues share the base code's semantics."""
        return re.sub(r"^RE-+", "", self.code)

    @property
    def is_reissue(self) -> bool:
        return self.code.startswith("RE-")

    @property
    def is_as_built(self) -> bool:
        return self.base_code == "ASB"

    @property
    def expected_revision_band(self) -> Optional[str]:
        """'ALPHABETIC' / 'NUMERIC' / None, derived from the sheet text."""
        seq = self.revision_sequence or ""
        if _ALPHA_SEQUENCE_RE.search(seq):
            return "ALPHABETIC"
        if _NUMERIC_SEQUENCE_RE.search(seq):
            return "NUMERIC"
        return None
