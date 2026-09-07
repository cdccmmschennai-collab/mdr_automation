"""Document identity normalisation.

The QatarEnergy DOCUMENT NO. is the anchor identity. Vendor rows carry up to
three candidate identifiers (Vendor Document No., PROJECT DOCUMENT/DRAWING NO.,
PROJECT DOC NO.) which are resolved against it.

Normalisation is deliberately conservative: we only ever collapse separators
and case. We never drop or invent number segments, because doing so would
merge genuinely distinct documents.

`clean` and `is_null_token` also define this project's convention for what a
cell value *means* ("-", "N/A" and friends mean no value), which is why the
revision parser, the Status Code loader and the workbook reader all use them.
"""

from __future__ import annotations

import re

from ...domain.models.document import DocumentIdentity

# Values that appear in the workbooks as "no value".
NULL_TOKENS = {"", "-", "--", "N/A", "NA", "#N/A", "NONE", "NIL"}

_SEPARATORS = re.compile(r"[^A-Z0-9]+")
_VEN_PREFIX = re.compile(r"^VEN[-_ ]?", re.IGNORECASE)


def clean(value: object) -> str:
    """Collapse whitespace (incl. embedded newlines) and strip."""
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def is_null_token(value: object) -> bool:
    """True when the cell means 'no value' in this workbook's conventions."""
    return clean(value).upper() in NULL_TOKENS


def canonicalise(value: object) -> str:
    """Case/separator-insensitive key: 'VEN-4391/MTY 1' -> 'VEN4391MTY1'.

    Used for NORMALIZED_EXACT matching only; the original string is always
    preserved alongside it.
    """
    return _SEPARATORS.sub("", clean(value).upper())


def strip_ven_prefix(canonical: str) -> str:
    """Drop a leading VEN prefix from an already-canonical key.

    The workbooks use 'VEN-4391-MTY-...' and '4391-MTY-...' for the same
    document in some vendor rows, so this supports ALTERNATIVE_IDENTIFIER
    matching. Applied to canonical keys only.
    """
    return canonical[3:] if canonical.startswith("VEN") else canonical


def normalise_identity(value: object) -> DocumentIdentity:
    """Build a DocumentIdentity from a raw cell value."""
    raw = clean(value)
    if is_null_token(raw):
        return DocumentIdentity(raw=raw, canonical="", alt_key="", is_null=True)
    canonical = canonicalise(raw)
    if not canonical:
        return DocumentIdentity(raw=raw, canonical="", alt_key="", is_null=True)
    return DocumentIdentity(
        raw=raw, canonical=canonical, alt_key=strip_ven_prefix(canonical)
    )
