"""Phase 2B orchestration: build the SOW resolver, and validate it.

Two jobs, both pure wiring:

* turn the rules workbook's `DOCUMENT TYPE` sheet into a `SowResolver`;
* run that resolver over the reference working sheet's DOC TYPE column and
  compare its answers with column AM.

No business rule lives here. The DOKAR table belongs to `engine.sow.rules`,
the resolution to `engine.sow.resolver`, and the mismatch taxonomy to
`engine.validation.sow`.

Both workbooks are opened read-only and neither is ever written to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..engine.sow.resolver import SowResolver
from ..engine.sow.rules import SowRuleBook
from ..engine.validation.sow import SowReport, compare_sow
from ..infrastructure.excel.reference_workbook import ReferenceWorkbookReader
from ..infrastructure.excel.rules_workbook import RulesWorkbookReader


def build_resolver(rules_workbook: Optional[Path] = None
                   ) -> Optional[SowResolver]:
    """Load the `DOCUMENT TYPE` sheet and return a resolver.

    Returns None when no rules workbook is available, so a caller that can
    work without SOW (a plain Phase 1 run) is not forced to handle an
    exception.
    """
    path = rules_workbook or settings.default_rules_workbook()
    if path is None or not Path(path).is_file():
        return None
    rows, _ = RulesWorkbookReader(path).read_sow_rows()
    return SowResolver(SowRuleBook.from_rows(rows))


def validate_sow(reference_workbook: Optional[Path] = None,
                 rules_workbook: Optional[Path] = None) -> SowReport:
    """Compare resolved SOW with column AM of `QatarEnergy-TN WORKING`.

    The DOC TYPE fed to the resolver is column AL - the reference's own,
    already-established Phase 2A result - so this measures Phase 2B alone and
    does not compound Phase 2A's classification error into it. Phase 2A's own
    agreement is reported separately by `classification_service`.

    Raises FileNotFoundError when either workbook is missing: a validation
    with nothing to validate against is a caller error.
    """
    reference = reference_workbook or settings.default_reference_workbook()
    if reference is None:
        raise FileNotFoundError(
            f"no reference workbook found in {settings.reference_working_dir}")

    resolver = build_resolver(rules_workbook)
    if resolver is None:
        raise FileNotFoundError(
            f"no rules workbook found in {settings.rules_dir}")

    rows, _ = ReferenceWorkbookReader(reference).read_working_rows()
    return compare_sow(rows, resolver)
