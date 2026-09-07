"""DOC TYPE as produced by the pipeline over the real MDR workbook.

Uses the session-scoped Phase 1 run, so this costs no extra pass over the
21,000-row sheet. Skipped when the input workbook is absent.
"""

import pytest

from app.engine.validation.doc_type import NON_DOC_TYPE_VERDICTS
from app.services.mdr_pipeline import MdrEngine
from tests.support.workbook import (
    PHASE1_WORKBOOK, requires_rules_workbook, requires_workbook,
)

pytestmark = [requires_workbook, requires_rules_workbook]


class TestPipelineClassifies:
    def test_the_rules_workbook_is_loaded(self, result):
        assert result.discovery["classification_rules"] == 182

    def test_a_substantial_share_of_rows_is_classified(self, result):
        classified = [d for d in result.documents if d.doc_type]
        assert len(classified) > 0.5 * len(result.documents)
        assert result.summary()["doc_type_classified_rows"] == len(classified)

    def test_every_classified_row_names_the_rule_that_decided_it(self, result):
        assert all(d.doc_type_rule for d in result.documents if d.doc_type)

    def test_unclassified_rows_carry_no_rule(self, result):
        assert all(not d.doc_type_rule
                   for d in result.documents if not d.doc_type)

    def test_no_row_is_given_a_scope_of_work_verdict(self, result):
        """SOW, IDB and CHECK STATUS are later phases."""
        assert {d.doc_type for d in result.documents}.isdisjoint(
            NON_DOC_TYPE_VERDICTS)

    def test_known_documents_get_their_expected_type(self, result):
        by_number = {d.qatarenergy_document_no: d for d in result.documents}
        expected = {
            "4391-MEWTP-2-13-0005": "MDS",
            "VEN-MEWTP-5-43-0011": "MIR",
            "VEN-MEWTP-2-54-0001": "MSL",
        }
        for number, doc_type in expected.items():
            record = by_number.get(number)
            if record is None:
                pytest.skip(f"{number} not in this workbook")
            assert record.doc_type == doc_type


class TestClassificationIsOptional:
    def test_a_run_without_rules_leaves_doc_type_empty(self, tmp_path):
        """Phase 1 must still work on its own."""
        engine = MdrEngine(PHASE1_WORKBOOK,
                           rules_workbook=tmp_path / "no-rules.xlsx")
        assert engine.load_classifier() is None
