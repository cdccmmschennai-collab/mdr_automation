"""Revision domain model.

A `Revision` is a parsed REV value with an explicit, explainable sort
position. The parsing rules live in `engine.revision.parsing`; this module
holds only the shape and the ordering semantics of the value itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RevisionBand(IntEnum):
    """Ordering bands. Higher band == later in the document lifecycle.

    UNPARSEABLE sorts lowest and is never eligible to be the latest revision;
    such rows are surfaced as exceptions instead of being guessed at.
    """

    UNPARSEABLE = -1
    NUMERIC = 0
    ALPHABETIC = 1
    AS_BUILT = 2


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


def compare(a: Revision, b: Revision) -> int:
    """Return -1/0/1 for a<b, a==b, a>b by lifecycle position."""
    ka, kb = a.sort_key, b.sort_key
    return (ka > kb) - (ka < kb)
