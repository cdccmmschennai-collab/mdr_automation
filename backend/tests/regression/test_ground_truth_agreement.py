"""Agreement with the workbook's own LATEST/NOT LATEST column.

This is regression coverage for the real-world cases the validation layer
classifies: a stale reference workbook, duplicate LATEST flags, and groups
with no LATEST at all. A new genuine conflict here means the engine has
regressed against the reference data.

Skipped automatically when the input workbook is not present.
"""

import pytest

from app.engine.validation.latest import Cause, validate_latest
from tests.support.workbook import requires_workbook

pytestmark = requires_workbook


class TestValidationAgainstGroundTruth:
    def test_no_genuine_conflicts_remain(self, result):
        """Every disagreement with the workbook must have an identified cause."""
        report = validate_latest(result)
        assert report.genuine_conflicts == []

    def test_raw_agreement_is_high(self, result):
        report = validate_latest(result)
        assert report.agreement_rate > 0.97

    def test_disagreements_are_all_classified(self, result):
        report = validate_latest(result)
        known = {c.value for c in Cause}
        assert set(report.cause_counts) <= known
        assert Cause.GENUINE_CONFLICT.value not in report.cause_counts
