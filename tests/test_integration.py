"""End-to-end checks against the real workbooks.

Skipped automatically when the input workbooks are not present.
"""

import hashlib
from pathlib import Path

import pytest

from mdr_engine.engine import MdrEngine, RevisionStatus
from mdr_engine.validate import Cause, validate_latest

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "input" / "new" / "_20260720-184-Transmittal Log (9) MDR.xlsx"

pytestmark = pytest.mark.skipif(not WORKBOOK.is_file(),
                                reason="source workbook not available")


@pytest.fixture(scope="module")
def result():
    return MdrEngine(WORKBOOK).run()


class TestDiscovery:
    def test_sheets_are_discovered_by_name_not_position(self, result):
        assert result.discovery["qe_sheet"] == "QatarEnergy-TN"
        assert result.discovery["vendor_sheet"] == "TN FROM VENDORS"

    def test_header_row_is_detected(self, result):
        assert result.discovery["qe_header_row"] == 5
        assert result.discovery["vendor_header_row"] == 5

    def test_status_codes_loaded_from_workbook(self, result):
        assert len(result.status_codes.review_codes) == 7
        assert "CODE-11" in result.status_codes.review_codes
        assert "ASB" in result.status_codes.issue_codes


class TestScale:
    def test_all_document_rows_processed(self, result):
        assert len(result.documents) > 21000

    def test_every_row_has_an_identity_and_a_status(self, result):
        assert all(d.document_identity for d in result.documents)
        assert all(d.revision_status for d in result.documents)

    def test_every_row_has_an_explanation(self, result):
        assert all(d.reason or d.exception_reason for d in result.documents)


class TestLatestInvariants:
    def test_at_most_one_latest_per_document(self, result):
        from collections import Counter
        counts = Counter(d.document_identity for d in result.documents
                         if d.revision_status == RevisionStatus.LATEST)
        assert not [k for k, v in counts.items() if v > 1]

    def test_as_built_rows_are_never_latest(self, result):
        asb = [d for d in result.documents
               if d.revision_status == RevisionStatus.AS_BUILT]
        assert asb, "expected as-built rows in this workbook"
        assert all(not d.is_latest_revision for d in asb)


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


class TestSourceIsNotModified:
    def test_workbook_is_unchanged_by_a_run(self):
        """Phase 1 must never write to the source workbook."""
        before = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
        mtime_before = WORKBOOK.stat().st_mtime
        MdrEngine(WORKBOOK).run()
        assert hashlib.sha256(WORKBOOK.read_bytes()).hexdigest() == before
        assert WORKBOOK.stat().st_mtime == mtime_before
