"""Revision parsing and banding.

Rules established from the source workbooks (see docs/business-rules/
revision-rules.md and docs/architecture/DECISION_LOG.md):

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

The ordering semantics themselves live on the `Revision` domain model.
"""

from __future__ import annotations

import re

from ...domain.models.revision import Revision, RevisionBand, compare  # noqa: F401
from ..identity.normalisation import clean, is_null_token

#: Revision tokens that denote an as-built/brown-field issue rather than a
#: position in the normal A,B,C.. sequence.
AS_BUILT_TOKENS = {"Z"}

_NUMERIC_RE = re.compile(r"^\d{1,3}$")
_ALPHA_RE = re.compile(r"^[A-Y]$")


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
