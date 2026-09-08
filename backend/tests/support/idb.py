"""Verbatim column AN evidence for the IDB tests.

Phase 2C has no rules sheet to copy - its authority is the observed behaviour
of `DOC IDB COMPLETED STATUS` in `QatarEnergy-TN WORKING`. The census below is
that observation, recorded exactly as measured so the unit suite can run
without the workbook; `tests/regression/test_idb_agreement.py` reads the real
file and holds it honest.

Nothing here is invented, and nothing here is an input to the resolver: the
census is evidence *about* the reference column, kept beside the tests that
cite it.
"""

from __future__ import annotations

from app.domain.models.sow import SowRequirement
from app.engine.idb.resolver import IdbResolver
from tests.support.sow import sample_sow_resolver

#: Every distinct value in column AN, with its row count over the sheet's
#: 21,372 data rows. `""` is the blank cell; `"0"` is the literal zero the
#: column carries on a handful of rows.
AN_CENSUS: dict[str, int] = {
    "NO NEED TO CHECK": 18706,
    "COMPLETED": 2364,
    "PENDING": 142,
    "TO BE CHECK": 114,
    "GENERAL SPECIFICATION": 14,
    "COMPLETED (REV UPDATED)": 9,
    "0": 7,
    "CANCELLED": 6,
    "TAG NOT IN FMTL": 3,
    "REFERENCE": 2,
    "COMPLETE": 2,
    "": 2,
    "REF": 1,
}

#: The census values that are actual IDB statuses - `0` and the blank are not.
#: `COMPLETE` and `REF` are in here because they *name* a status; they are
#: spelling variants of one, which the validation triage records as such.
AN_STATUS_VALUES: tuple[str, ...] = tuple(
    v for v in AN_CENSUS if v not in {"", "0"})

#: Rows in the sheet, for the census to be checked against.
WORKING_ROW_COUNT = 21372


def requirement(doc_type: str) -> SowRequirement:
    """The real Phase 2B verdict for a DOC TYPE, from the real rules sheet.

    Tests state a DOC TYPE and get the `SowRequirement` the pipeline would
    hand Phase 2C, so no test has to hand-build a scope verdict that the
    `DOCUMENT TYPE` sheet does not actually state.
    """
    return sample_sow_resolver().resolve(doc_type)


def sample_idb_resolver() -> IdbResolver:
    return IdbResolver()
