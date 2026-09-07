"""The real keyword rules workbook: loading, contents and integrity.

This is what makes `tests/support/rules.py` trustworthy - the unit suite runs
against a hand-copied slice of the workbook, and this module proves that slice
still matches the file.

Skipped automatically when the rules workbook is not present.
"""

import hashlib

import pytest

from app.engine.classification.rules import NOT_REQUIRED, REQUIRED, RuleBook
from app.infrastructure.excel.rules_workbook import RulesWorkbookReader
from app.services.classification_service import build_classifier
from tests.support.rules import SAMPLE_RULE_ROWS
from tests.support.workbook import RULES_WORKBOOK, requires_rules_workbook

pytestmark = requires_rules_workbook


@pytest.fixture(scope="module")
def rule_rows():
    rows, _ = RulesWorkbookReader(RULES_WORKBOOK).read_rule_rows()
    return rows


@pytest.fixture(scope="module")
def discovery():
    _, disc = RulesWorkbookReader(RULES_WORKBOOK).read_rule_rows()
    return disc


class TestDiscovery:
    def test_sheets_are_found_by_name_not_position(self, discovery):
        assert discovery.required_sheet == "REQUIRED-KEY DOC.WORDS"
        assert discovery.not_required_sheet == "NOT REQUIRED-KEY DOC.WORDS"

    def test_both_keyword_sheets_are_fully_loaded(self, discovery):
        assert discovery.required_rules == 82
        assert discovery.not_required_rules == 100

    def test_the_sow_and_folder_sheets_are_not_read(self, rule_rows):
        """`DOCUMENT TYPE` and `FOLDER-UPDATE` belong to later phases."""
        assert {r.source for r in rule_rows} == {REQUIRED, NOT_REQUIRED}


class TestSampleFixtureMatchesTheWorkbook:
    def test_every_sampled_rule_is_present_verbatim(self, rule_rows):
        by_position = {(r.source, r.row): r for r in rule_rows}
        for sample in SAMPLE_RULE_ROWS:
            actual = by_position.get((sample.source, sample.row))
            assert actual is not None, f"{sample.source} row {sample.row} missing"
            assert actual == sample


class TestRuleBookFromTheWorkbook:
    def test_every_workbook_rule_is_usable(self, rule_rows):
        assert len(RuleBook.from_rows(rule_rows)) == len(rule_rows)

    def test_required_rules_come_first(self, rule_rows):
        sources = [r.source for r in RuleBook.from_rows(rule_rows)]
        assert sources == ([REQUIRED] * 82 + [NOT_REQUIRED] * 100)

    def test_the_dokar_codes_are_all_reachable(self, rule_rows):
        produced = set(RuleBook.from_rows(rule_rows).doc_types)
        assert {"MDS", "MIR", "MLD", "MLP", "MMC", "MMD", "MOM", "MSL", "MXB",
                "MTC", "MPI", "MBD", "MXS", "MCE", "MNP", "MSS", "MVA", "MXX",
                "LGD", "MSI", "MHR", "MDR", "VDR", "EDR", "TNR", "DEM"} <= produced

    def test_no_rule_produces_a_scope_of_work_verdict(self, rule_rows):
        """`OTHER`, `NOT SOW` and friends are Phase 2B, not DOC TYPE."""
        produced = set(RuleBook.from_rows(rule_rows).doc_types)
        assert produced.isdisjoint(
            {"OTHER", "NOT SOW", "OLD REV NOT SOW", "NO", "SOW"})


class TestClassifierWiring:
    def test_the_service_builds_a_classifier_from_the_workbook(self):
        classifier = build_classifier(RULES_WORKBOOK)
        assert classifier is not None
        assert len(classifier.rules) == 182

    def test_a_missing_rules_workbook_yields_no_classifier(self, tmp_path):
        assert build_classifier(tmp_path / "nothing.xlsx") is None


class TestSourceIsNotModified:
    def test_reading_the_rules_does_not_touch_the_file(self):
        before = hashlib.sha256(RULES_WORKBOOK.read_bytes()).hexdigest()
        mtime_before = RULES_WORKBOOK.stat().st_mtime
        RulesWorkbookReader(RULES_WORKBOOK).read_rule_rows()
        assert hashlib.sha256(RULES_WORKBOOK.read_bytes()).hexdigest() == before
        assert RULES_WORKBOOK.stat().st_mtime == mtime_before
