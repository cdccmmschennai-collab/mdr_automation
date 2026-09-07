"""End-to-end checks against the real workbooks.

Skipped automatically when the input workbook is not present. The ground-truth
comparison lives in `tests/regression/test_ground_truth_agreement.py`.
"""

import hashlib
from collections import Counter

import pytest

from app.domain.enums.status_codes import RevisionStatus
from app.services.mdr_pipeline import MdrEngine
from tests.support.workbook import PHASE1_WORKBOOK, requires_workbook

pytestmark = requires_workbook


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
        counts = Counter(d.document_identity for d in result.documents
                         if d.revision_status == RevisionStatus.LATEST)
        assert not [k for k, v in counts.items() if v > 1]

    def test_as_built_rows_are_never_latest(self, result):
        asb = [d for d in result.documents
               if d.revision_status == RevisionStatus.AS_BUILT]
        assert asb, "expected as-built rows in this workbook"
        assert all(not d.is_latest_revision for d in asb)


class TestSourceIsNotModified:
    def test_workbook_is_unchanged_by_a_run(self):
        """Phase 1 must never write to the source workbook."""
        before = hashlib.sha256(PHASE1_WORKBOOK.read_bytes()).hexdigest()
        mtime_before = PHASE1_WORKBOOK.stat().st_mtime
        MdrEngine(PHASE1_WORKBOOK).run()
        assert hashlib.sha256(PHASE1_WORKBOOK.read_bytes()).hexdigest() == before
        assert PHASE1_WORKBOOK.stat().st_mtime == mtime_before
