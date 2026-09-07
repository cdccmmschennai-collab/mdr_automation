"""Revision parsing, banding and sequencing.

Rules established from the source workbooks (see docs/PHASE1_FINDINGS.md):

1. Alphabetic revisions rank LATER than numeric revisions.
   Verified against the workbook's own LATEST/NOT LATEST column:
   7653/7654 (99.99%) agreement, versus 68% for the inverse ordering.

2. Revision 'Z' is NOT the 26th letter of a sequence. The Status Codes sheet
   defines the AS-BUILT (ASB) sequence as "AFC-GRASS FIELD / Z-BROWN FIELD",
   and all 68 'Z' rows in the workbook carry issue code ASB, are never marked
   LATEST, and always have a sibling revision that is. 'Z' is therefore an
   as-built marker band that is excluded from latest-revision candidacy.

3. The revision comes from the REV field only. A digit or letter appearing
   inside a document number is never treated as a revision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from .identity import clean, is_null_token


class RevisionBand(IntEnum):
    """Ordering bands. Higher band == later in the document lifecycle.

    UNPARSEABLE sorts lowest and is never eligible to be the latest revision;
    such rows are surfaced as exceptions instead of being guessed at.
    """

    UNPARSEABLE = -1
    NUMERIC = 0
    ALPHABETIC = 1
    AS_BUILT = 2


#: Revision tokens that denote an as-built/brown-field issue rather than a
#: position in the normal A,B,C.. sequence.
AS_BUILT_TOKENS = {"Z"}

_NUMERIC_RE = re.compile(r"^\d{1,3}$")
_ALPHA_RE = re.compile(r"^[A-Y]$")


@dataclass(frozen=True)
class Revision:
    """A parsed revision with an explicit, explainable sort position."""

    raw: str
    band: RevisionBand
    ordinal: int
    normalised: str
    reason: str

    @property
    def sort_key(self) -> tuple[int, int]:
        return (int(self.band), self.ordinal)

    @property
    def is_parseable(self) -> bool:
        return self.band is not RevisionBand.UNPARSEABLE

    @property
    def category(self) -> str:
        return self.band.name

    @property
    def eligible_for_latest(self) -> bool:
        """As-built and unparseable revisions never win latest determination."""
        return self.band in (RevisionBand.NUMERIC, RevisionBand.ALPHABETIC)

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.normalised or self.raw


def parse_revision(value: object) -> Revision:
    """Parse a REV cell into an ordered Revision.

    Accepts the numeric ('0', '1', ... including multi-digit) and alphabetic
    ('A'..'Y') sequences, plus the as-built 'Z' marker. Anything else is
    reported as UNPARSEABLE rather than coerced.
    """
    raw = clean(value)

    if is_null_token(raw):
        return Revision(raw=raw, band=RevisionBand.UNPARSEABLE, ordinal=0,
                        normalised="", reason="REV_EMPTY")

    token = raw.upper()

    # Excel may hand back '3' as 3 or 3.0; normalise a clean integral float.
    if re.fullmatch(r"\d+\.0+", token):
        token = token.split(".")[0]

    if _NUMERIC_RE.fullmatch(token):
        return Revision(raw=raw, band=RevisionBand.NUMERIC, ordinal=int(token),
                        normalised=str(int(token)), reason="REV_NUMERIC")

    if token in AS_BUILT_TOKENS:
        return Revision(raw=raw, band=RevisionBand.AS_BUILT, ordinal=0,
                        normalised=token, reason="REV_AS_BUILT_MARKER")

    if _ALPHA_RE.fullmatch(token):
        return Revision(raw=raw, band=RevisionBand.ALPHABETIC,
                        ordinal=ord(token) - ord("A"), normalised=token,
                        reason="REV_ALPHABETIC")

    return Revision(raw=raw, band=RevisionBand.UNPARSEABLE, ordinal=0,
                    normalised="", reason="REV_UNRECOGNISED_FORMAT")


def compare(a: Revision, b: Revision) -> int:
    """Return -1/0/1 for a<b, a==b, a>b by lifecycle position."""
    ka, kb = a.sort_key, b.sort_key
    return (ka > kb) - (ka < kb)
