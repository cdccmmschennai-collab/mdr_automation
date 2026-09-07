"""QatarEnergy-TN <-> TN FROM VENDORS matching.

A deterministic tier ladder. The first tier that yields exactly one QE identity
wins; a tier yielding more than one records AMBIGUOUS and matches nothing.
Uncertain matches are never made silently.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from .identity import DocumentIdentity, normalise_identity


class MatchStatus(str, Enum):
    EXACT = "EXACT"
    NORMALIZED_EXACT = "NORMALIZED_EXACT"
    ALTERNATIVE_IDENTIFIER = "ALTERNATIVE_IDENTIFIER"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_MATCHED = "NOT_MATCHED"
    NO_IDENTIFIER = "NO_IDENTIFIER"


@dataclass(frozen=True)
class MatchResult:
    status: MatchStatus
    matched_document: str = ""
    match_method: str = ""
    source_field: str = ""
    candidates: tuple[str, ...] = ()
    reason: str = ""


@dataclass
class QeIndex:
    """Lookup structure over QE document identities.

    Built once and reused for every vendor row - never re-scan per row.
    """

    exact: dict[str, str] = field(default_factory=dict)
    canonical: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    alt: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    @classmethod
    def build(cls, identities: Iterable[DocumentIdentity]) -> "QeIndex":
        idx = cls()
        for ident in identities:
            if not ident:
                continue
            idx.exact.setdefault(ident.raw, ident.raw)
            idx.canonical[ident.canonical].add(ident.raw)
            idx.alt[ident.alt_key].add(ident.raw)
        return idx

    def __len__(self) -> int:  # pragma: no cover - convenience only
        return len(self.canonical)


#: Vendor identifier columns, in priority order. The project-level identifiers
#: are tried before the vendor-internal one because they are the fields that
#: actually carry the QatarEnergy document number.
VENDOR_FIELD_PRIORITY = (
    "PROJECT_DOCUMENT_DRAWING_NO",
    "PROJECT_DOC_NO",
    "VENDOR_DOCUMENT_NO",
)


def match_vendor_row(candidates: dict[str, str], index: QeIndex) -> MatchResult:
    """Resolve one vendor row against the QE index.

    `candidates` maps a field name from VENDOR_FIELD_PRIORITY to its raw value.
    """
    idents = {}
    for fieldname in VENDOR_FIELD_PRIORITY:
        ident = normalise_identity(candidates.get(fieldname, ""))
        if ident:
            idents[fieldname] = ident

    if not idents:
        return MatchResult(status=MatchStatus.NO_IDENTIFIER,
                           reason="no usable identifier on the vendor row")

    # Tier 1 - byte-exact on the raw document number.
    for fieldname, ident in idents.items():
        if ident.raw in index.exact:
            return MatchResult(status=MatchStatus.EXACT,
                               matched_document=index.exact[ident.raw],
                               match_method="EXACT", source_field=fieldname,
                               reason=f"exact match on {fieldname}")

    # Tier 2 - case/separator-insensitive.
    for fieldname, ident in idents.items():
        hits = index.canonical.get(ident.canonical)
        if not hits:
            continue
        if len(hits) == 1:
            return MatchResult(status=MatchStatus.NORMALIZED_EXACT,
                               matched_document=next(iter(hits)),
                               match_method="NORMALIZED_EXACT",
                               source_field=fieldname,
                               reason=f"normalised match on {fieldname}")
        return MatchResult(status=MatchStatus.AMBIGUOUS,
                           match_method="NORMALIZED_EXACT", source_field=fieldname,
                           candidates=tuple(sorted(hits)),
                           reason=f"{len(hits)} QE documents share this normalised key")

    # Tier 3 - tolerate the VEN- prefix convention.
    for fieldname, ident in idents.items():
        hits = index.alt.get(ident.alt_key)
        if not hits:
            continue
        if len(hits) == 1:
            return MatchResult(status=MatchStatus.ALTERNATIVE_IDENTIFIER,
                               matched_document=next(iter(hits)),
                               match_method="ALT_VEN_PREFIX",
                               source_field=fieldname,
                               reason=f"VEN-prefix-tolerant match on {fieldname}")
        return MatchResult(status=MatchStatus.AMBIGUOUS,
                           match_method="ALT_VEN_PREFIX", source_field=fieldname,
                           candidates=tuple(sorted(hits)),
                           reason=f"{len(hits)} QE documents share this alternative key")

    return MatchResult(status=MatchStatus.NOT_MATCHED,
                       reason="no QE document carries any of this row's identifiers")
