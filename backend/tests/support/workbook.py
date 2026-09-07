"""Locating the real workbook for integration and regression tests.

Resolved through `core.config` rather than a hard-coded path, so moving the
data directory does not break the suites. Suites that need it skip themselves
when it is absent.
"""

from __future__ import annotations

import pytest

from app.core.config import settings

#: May be None when no workbook is present - the markers below handle that.
PHASE1_WORKBOOK = settings.default_workbook()
RULES_WORKBOOK = settings.default_rules_workbook()
REFERENCE_WORKBOOK = settings.default_reference_workbook()


def _missing(path) -> bool:
    return path is None or not path.is_file()


#: Apply as `pytestmark` in any module that needs the real workbook.
requires_workbook = pytest.mark.skipif(
    _missing(PHASE1_WORKBOOK), reason="source workbook not available")

requires_rules_workbook = pytest.mark.skipif(
    _missing(RULES_WORKBOOK), reason="rules workbook not available")

requires_reference_workbook = pytest.mark.skipif(
    _missing(RULES_WORKBOOK) or _missing(REFERENCE_WORKBOOK),
    reason="rules or reference workbook not available")
