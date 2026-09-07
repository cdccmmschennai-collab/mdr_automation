"""Latest-revision determination.

Within each document identity group, the eligible row with the highest
(band, ordinal) wins. Ties are never broken by guessing: two rows sharing the
top revision produce an exception, as does a group in which no row is eligible
at all.
"""

from __future__ import annotations

from ...domain.enums.status_codes import RevisionStatus
from ...domain.models.document import DocumentRecord
from ...domain.models.revision import RevisionBand
from ..identity.grouping import group_by_identity


def determine_latest(records: list[DocumentRecord]) -> None:
    """Mark the latest revision within each document identity group.

    Mutates `records` in place: sets `revision_status`, `is_latest_revision`,
    `reason` and, where applicable, `is_exception` / `exception_reason`.
    """
    groups = group_by_identity(records)

    for group in groups.values():
        eligible = [r for r in group if getattr(r, "_eligible", False)]
        if not eligible:
            for r in group:
                r.revision_status = RevisionStatus.EXCEPTION
                r.is_latest_revision = False
                if not r.exception_reason:
                    r.is_exception = True
                    r.exception_reason = (
                        "no revision in this document group is eligible to be "
                        "the latest")
            continue

        best_key = max((r.revision_band, r.revision_rank) for r in eligible)
        winners = [r for r in eligible
                   if (r.revision_band, r.revision_rank) == best_key]

        for r in group:
            is_winner = r in winners
            r.is_latest_revision = is_winner and len(winners) == 1
            if len(winners) > 1 and is_winner:
                # Duplicate top revision - refuse to pick one.
                r.revision_status = RevisionStatus.EXCEPTION
                r.is_exception = True
                r.is_latest_revision = False
                r.exception_reason = (
                    f"{len(winners)} rows share the highest revision "
                    f"{r.revision!r}; latest is ambiguous")
                r.reason = "AMBIGUOUS_TOP_REVISION"
            elif is_winner:
                r.revision_status = RevisionStatus.LATEST
                r.reason = (
                    f"highest revision in group ({len(group)} row(s)); "
                    f"band={RevisionBand(r.revision_band).name} rank={r.revision_rank}")
            elif getattr(r, "_eligible", False):
                r.revision_status = RevisionStatus.OLD
                top = winners[0]
                r.reason = (
                    f"superseded by revision {top.revision!r} "
                    f"(band={RevisionBand(top.revision_band).name})")
            elif r.revision_band == int(RevisionBand.AS_BUILT):
                r.revision_status = RevisionStatus.AS_BUILT
                r.is_latest_revision = False
                r.reason = ("as-built (Z) issue: outside the revision "
                            "sequence, never the latest revision")
            else:
                r.revision_status = RevisionStatus.EXCEPTION
                r.is_latest_revision = False
                r.is_exception = True
                if not r.exception_reason:
                    r.exception_reason = "row not eligible for latest determination"
                r.reason = r.exception_reason
