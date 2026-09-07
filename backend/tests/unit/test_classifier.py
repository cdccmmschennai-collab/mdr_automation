"""DOC TYPE classification: verdicts, precedence and no-match behaviour.

The rule book here is a verbatim slice of the real keyword workbook - see
`tests/support/rules.py`. Document numbers and titles are real rows from the
QatarEnergy MDR unless a test says otherwise.
"""

import pytest

from app.engine.classification.classifier import UNCLASSIFIED
from app.engine.classification.rules import NOT_REQUIRED, REQUIRED
from tests.support.rules import sample_classifier


@pytest.fixture(scope="module")
def classifier():
    return sample_classifier()


class TestRequiredKeywords:
    @pytest.mark.parametrize("number,title,expected", [
        ("4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR - NEWTP", "MDS"),
        ("4391-MEWTP-6-13-0004", "PROCESS DATA SHEETS FOR IRRIGATION TANK", "MDS"),
        ("VEN-MEWTP-5-43-0011", "SPIR INITIAL: LOCAL PANEL, RCU, VSD", "MIR"),
        ("VEN-4391-MTY-5-43-0003",
         "SPARE PARTS AND INTERCHANGEABILITY RECORD (SPIR)", "MIR"),
        ("4391-M3UT-4-66-0002", "F&G LOOP DIAGRAMS NGL-3", "MLP"),
        ("4391-M3UT-6-51-0007-001", "UTILITY P&ID: LAYDOWN AREA RUNOFF", "MXB"),
        ("4391-M3GE-2-54-0001-001", "SLD-415V SWITCHBOARD (6530-SB-03)", "MSL"),
        ("VEN-MEWTP-2-54-0001", "SINGLE LINE DIAGRAM FOR APFC PANEL", "MSL"),
        ("VEN-MEWTP-2-16-0011", "TYPE TEST CERTIFICATE FOR LV BUSDUCT", "MTC"),
        ("VEN-MEWTP-4-31-0002", "BILL OF MATERIAL HVAC CONTROL PANEL", "MMC"),
    ])
    def test_required_keyword_gives_its_doc_type(self, classifier, number,
                                                 title, expected):
        assert classifier.classify(number, title).doc_type == expected

    @pytest.mark.parametrize("title", [
        "HOOK-UP DRAWING FOR PRESSURE TRANSMITTERS",
        "HOOK UP DRAWING FOR PRESSURE TRANSMITTERS",
        "HOOKUP DRAWING FOR PRESSURE TRANSMITTERS",
    ])
    def test_all_three_hook_up_spellings_reach_mva(self, classifier, title):
        assert classifier.classify("VEN-MEWTP-4-70-0001", title).doc_type == "MVA"

    @pytest.mark.parametrize("title", [
        "LIGHTING LAYOUT FOR SUBSTATION BUILDING",
        "LIGHTNING LAYOUT FOR SUBSTATION BUILDING",
    ])
    def test_both_alternatives_of_an_or_rule_reach_mld(self, classifier, title):
        assert classifier.classify("4391-M3UT-2-50-0001", title).doc_type == "MLD"

    def test_a_required_verdict_records_its_source(self, classifier):
        result = classifier.classify("", "SPIR INITIAL PAGA")
        assert result.rule_source == REQUIRED
        assert result.winning_match.rule_row == 17


class TestNotRequiredKeywords:
    @pytest.mark.parametrize("number,title,expected", [
        ("4391-M2UT-5-50-0102-001", "OVERALL PLOT PLAN", "PLAN"),
        ("4391-0-TQ-0004", "CLARIFICATION ON DRAWING SCALE", "TECHNICAL QUERY"),
        ("4391-0-XX-0001", "TECHNICAL QUERY ON TANK COATING", "TECHNICAL QUERY"),
        ("4391-0-CV-0053", "CV OF KHAJA NIZAMUDDIN BADAR", "CV"),
        ("4391-0-AR-0001", "INTERNAL AUDIT OF THE QUALITY SYSTEM",
         "AUDIT REPORT"),
        ("4391-0-PQD-0001", "SUBCONTRACTOR SUBMISSION", "PREQUALIFICATION"),
        ("4391-0-WPR-0012", "PROGRESS UPDATE", "WEEKLY PROGRESS REPORT"),
        ("4391-0-NCR-0007", "WELD REJECTION", "NON CONFORMANCE REPORT"),
        ("4391-0-XX-0002", "METHOD STATEMENT FOR TANK ERECTION",
         "METHOD STATEMENT"),
        ("4391-0-XX-0003", "SHOP DRAWING FOR STEEL PIPERACK", "SHOP DRAWING"),
    ])
    def test_not_required_keyword_gives_its_doc_type(self, classifier, number,
                                                     title, expected):
        assert classifier.classify(number, title).doc_type == expected

    def test_a_not_required_verdict_records_its_source(self, classifier):
        result = classifier.classify("4391-0-CV-0053", "CV OF SOMEONE")
        assert result.rule_source == NOT_REQUIRED


class TestPrecedence:
    """Derived from the reference workbook - see classification-rules.md."""

    def test_required_beats_not_required(self, classifier):
        """`LAYOUT PLAN` is a not-required rule; `*LAYOUT*PLAN*` a required one.

        Where rules from both sheets matched, the reference workbook sided
        with the required sheet 84 times and the not-required sheet never.
        """
        result = classifier.classify(
            "4391-M3UT-1-50-0101-001", "EQUIPMENT LAYOUT PLAN FOR NGL-3")
        assert result.doc_type == "MLD"
        assert result.rule_source == REQUIRED
        assert "LAYOUT" in result.competing_doc_types

    def test_earlier_workbook_row_wins_within_a_sheet(self, classifier):
        """`*P&ID*LEGEND*` (row 10) outranks `P&ID` (row 51)."""
        result = classifier.classify("4391-MGEN-6-51-0001",
                                     "UTILITY P&ID LEGEND AND SYMBOLS")
        assert result.doc_type == "LGD"
        assert result.competing_doc_types == ("LGD", "MXB")

    def test_every_matching_rule_is_retained(self, classifier):
        result = classifier.classify("4391-0-CV-0012",
                                     "CV OF BENCY IDICULLA - PLANNING ENGINEER")
        assert set(result.competing_doc_types) == {"PLAN", "CV"}
        assert len(result.matches) >= 3

    def test_a_single_match_is_not_ambiguous(self, classifier):
        result = classifier.classify("", "SINGLE LINE DIAGRAM FOR APFC PANEL")
        assert not result.is_ambiguous

    def test_competing_rules_are_flagged_ambiguous(self, classifier):
        result = classifier.classify("", "UTILITY P&ID LEGEND AND SYMBOLS")
        assert result.is_ambiguous


class TestNoMatch:
    def test_an_uncovered_document_is_unclassified(self, classifier):
        result = classifier.classify("4391-MTY-0-04-0034",
                                     "OPERATIONS READINESS BRIEFING")
        assert result.doc_type == UNCLASSIFIED
        assert result.matches == ()
        assert not result.is_classified

    def test_empty_inputs_are_unclassified(self, classifier):
        assert classifier.classify("", "").doc_type == UNCLASSIFIED

    def test_missing_inputs_are_unclassified(self, classifier):
        assert classifier.classify().doc_type == UNCLASSIFIED

    @pytest.mark.parametrize("token", ["-", "N/A", "#N/A", "NONE", "nil"])
    def test_null_tokens_are_treated_as_absent(self, classifier, token):
        assert classifier.classify(token, token).doc_type == UNCLASSIFIED

    def test_a_null_document_number_does_not_block_the_title(self, classifier):
        assert classifier.classify("-", "LOOP DIAGRAM FOR F&G").doc_type == "MLP"

    def test_a_blank_title_does_not_block_the_document_number(self, classifier):
        assert classifier.classify("4391-0-CV-0053", "").doc_type == "CV"


class TestInputNormalisation:
    @pytest.mark.parametrize("title", [
        "single line diagram for apfc panel",
        "   SINGLE LINE DIAGRAM FOR APFC PANEL   ",
        "SINGLE    LINE DIAGRAM FOR APFC PANEL",
        "SINGLE\nLINE DIAGRAM FOR APFC PANEL",
    ])
    def test_case_and_spacing_do_not_change_the_verdict(self, classifier, title):
        assert classifier.classify("VEN-MEWTP-2-54-0001", title).doc_type == "MSL"

    def test_ampersands_and_hyphens_survive_normalisation(self, classifier):
        assert classifier.classify("", "utility p&id: laydown area").doc_type \
            == "MXB"
