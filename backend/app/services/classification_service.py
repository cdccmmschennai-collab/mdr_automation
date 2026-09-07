"""Phase 2A orchestration: build the DOC TYPE classifier, and validate it.

Two jobs, both pure wiring:

* turn the keyword rules workbook into a `DocumentClassifier`;
* run that classifier over the reference working sheet and compare its answers
  with column AL.

No business rule lives here. The keyword semantics belong to
`engine.classification.rules`, the precedence to `engine.classification`, and
the mismatch taxonomy to `engine.validation.doc_type`.

Both workbooks are opened read-only and neither is ever written to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..engine.classification.classifier import DocumentClassifier
from ..engine.classification.rules import RuleBook
from ..engine.validation.doc_type import DocTypeReport, compare_doc_types
from ..infrastructure.excel.reference_workbook import ReferenceWorkbookReader
from ..infrastructure.excel.rules_workbook import RulesWorkbookReader


def build_classifier(rules_workbook: Optional[Path] = None
                     ) -> Optional[DocumentClassifier]:
    """Load the keyword rules and return a classifier.

    Returns None when no rules workbook is available, so a caller that can
    work without DOC TYPE (a plain Phase 1 run) is not forced to handle an
    exception.
    """
    path = rules_workbook or settings.default_rules_workbook()
    if path is None or not Path(path).is_file():
        return None
    rows, _ = RulesWorkbookReader(path).read_rule_rows()
    return DocumentClassifier(RuleBook.from_rows(rows))


def validate_doc_types(reference_workbook: Optional[Path] = None,
                       rules_workbook: Optional[Path] = None) -> DocTypeReport:
    """Compare engine DOC TYPE with column AL of `QatarEnergy-TN WORKING`.

    Raises FileNotFoundError when either workbook is missing: unlike a Phase 1
    run, a validation with nothing to validate against is a caller error.
    """
    reference = reference_workbook or settings.default_reference_workbook()
    if reference is None:
        raise FileNotFoundError(
            f"no reference workbook found in {settings.reference_working_dir}")

    classifier = build_classifier(rules_workbook)
    if classifier is None:
        raise FileNotFoundError(
            f"no rules workbook found in {settings.rules_dir}")

    rows, _ = ReferenceWorkbookReader(reference).read_working_rows()
    return compare_doc_types(rows, classifier)
