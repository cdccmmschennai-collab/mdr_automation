"""Phase 2C orchestration: build the IDB resolver, and validate it.

Two jobs, both pure wiring:

* hand back an `IdbResolver` together with the `SowResolver` it consumes;
* run that pair over the reference working sheet's DOC TYPE column and compare
  their answers with column AN.

No business rule lives here. The two IDB rules belong to `engine.idb.rules`,
the resolution to `engine.idb.resolver`, the scope verdict to `engine.sow`,
and the mismatch taxonomy to `engine.validation.idb`.

Both workbooks are opened read-only and neither is ever written to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..engine.idb.resolver import IdbResolver
from ..engine.sow.resolver import SowResolver
from ..engine.validation.idb import IdbReport, compare_idb
from ..infrastructure.excel.reference_workbook import ReferenceWorkbookReader
from .sow_service import build_resolver as build_sow_resolver


def build_idb_resolver() -> IdbResolver:
    """Return an IDB resolver.

    It takes no arguments because it loads nothing: Phase 2C's rules are
    stated in code, from the evidence recorded in
    `docs/business-rules/idb-rules.md`, and no sheet of the rules workbook
    states an IDB status. The function exists so callers wire Phase 2C the
    same way they wire Phase 2B, and so that gaining a rules sheet later is a
    change here rather than at every call site.
    """
    return IdbResolver()


def build_resolvers(rules_workbook: Optional[Path] = None
                    ) -> tuple[Optional[SowResolver], IdbResolver]:
    """The Phase 2B -> Phase 2C pair, in the order the pipeline runs them.

    The SOW resolver is None when no rules workbook is available, exactly as
    `sow_service.build_resolver` reports it; without it Phase 2C has no scope
    verdict to act on and every document would resolve to `UNMAPPED`.
    """
    return build_sow_resolver(rules_workbook), build_idb_resolver()


def validate_idb(reference_workbook: Optional[Path] = None,
                 rules_workbook: Optional[Path] = None) -> IdbReport:
    """Compare resolved IDB with column AN of `QatarEnergy-TN WORKING`.

    The DOC TYPE fed to the chain is column AL - the reference's own,
    already-established Phase 2A result - so this measures Phases 2B+2C and
    does not compound Phase 2A's classification error into them. Phase 2A's
    own agreement is reported separately by `classification_service`, and
    Phase 2B's by `sow_service`.

    No completion source is supplied, because Phase 2C implements none. Every
    in-scope document therefore resolves to `TO BE CHECK`, and the report
    counts how many rows that leaves waiting on an input this phase does not
    have.

    Raises FileNotFoundError when either workbook is missing: a validation
    with nothing to validate against is a caller error.
    """
    reference = reference_workbook or settings.default_reference_workbook()
    if reference is None:
        raise FileNotFoundError(
            f"no reference workbook found in {settings.reference_working_dir}")

    sow_resolver, idb_resolver = build_resolvers(rules_workbook)
    if sow_resolver is None:
        raise FileNotFoundError(
            f"no rules workbook found in {settings.rules_dir}")

    rows, _ = ReferenceWorkbookReader(reference).read_working_rows()
    return compare_idb(rows, sow_resolver, idb_resolver)
