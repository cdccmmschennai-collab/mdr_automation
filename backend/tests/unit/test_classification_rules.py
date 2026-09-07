"""Keyword syntax: how a rules-workbook cell becomes a match.

Every pattern exercised here is a real cell from
`INPUT-KEYWORDS  FOR MDR TOOL.xlsx` - see `tests/support/rules.py`.
"""

import pytest

from app.engine.classification.rules import (
    NOT_APPLICABLE, NOT_REQUIRED, REQUIRED, KeywordRule, RuleBook, RuleRow,
    normalise, parse_keyword,
)
from tests.support.rules import SAMPLE_RULE_ROWS, sample_rulebook


def rule(number, title, doc_type, source=REQUIRED, row=1) -> KeywordRule:
    return KeywordRule.parse(RuleRow(source, row, number, title, doc_type))


class TestNormalisation:
    def test_case_is_folded(self):
        assert normalise("data sheet") == "DATA SHEET"

    def test_leading_and_trailing_space_is_stripped(self):
        assert normalise("   SPIR   ") == "SPIR"

    def test_runs_of_whitespace_collapse_to_one(self):
        assert normalise("DATA    SHEET") == "DATA SHEET"

    def test_embedded_newlines_collapse(self):
        assert normalise("TEST\nCERTIFICATE") == "TEST CERTIFICATE"

    def test_punctuation_is_preserved(self):
        """HOOK-UP, HOOK UP and HOOKUP are three separate rules."""
        assert normalise("hook-up") == "HOOK-UP"
        assert normalise("P&ID") == "P&ID"


class TestKeywordParsing:
    def test_not_applicable_yields_no_pattern(self):
        assert parse_keyword(NOT_APPLICABLE) == ()

    def test_blank_yields_no_pattern(self):
        assert parse_keyword("") == ()
        assert parse_keyword(None) == ()

    def test_literal_yields_one_pattern(self):
        assert [p for p, _ in parse_keyword("TEST CERTIFICATE")] == \
            ["TEST CERTIFICATE"]

    def test_alternation_yields_both_alternatives(self):
        patterns = [p for p, _ in
                    parse_keyword("LIGHTING LAYOUT or LIGHTNING LAYOUT")]
        assert patterns == ["LIGHTING LAYOUT", "LIGHTNING LAYOUT"]

    def test_alternation_is_case_insensitive_on_the_or(self):
        assert len(parse_keyword("SPIR OR SPARE PARTS")) == 2

    def test_or_inside_a_word_is_not_alternation(self):
        """`or` needs whitespace both sides, so `ROUTING` stays intact."""
        assert [p for p, _ in parse_keyword("ROUTING LAYOUT")] == \
            ["ROUTING LAYOUT"]


class TestLiteralMatching:
    """Plain keywords match as substrings - the workbook's own convention."""

    def test_literal_matches_anywhere_in_the_title(self):
        r = rule(NOT_APPLICABLE, "SINGLE LINE", "MSL")
        assert r.match("", "SINGLE LINE DIAGRAM FOR APFC PANEL")

    def test_singular_keyword_matches_a_plural_title(self):
        """`TEST CERTIFICATE` must catch `TEST CERTIFICATES`."""
        r = rule(NOT_APPLICABLE, "TEST CERTIFICATE", "MTC")
        assert r.match("", "TYPE TEST CERTIFICATES FOR LV POWER CABLES")

    def test_singular_keyword_matches_an_inflected_title(self):
        """`CROSS SECTION` must catch `CROSS SECTIONAL`."""
        r = rule(NOT_APPLICABLE, "CROSS SECTION", "MXS")
        assert r.match("", "PUMP CROSS SECTIONAL DRAWING - NGL-1")

    def test_match_is_case_insensitive(self):
        r = rule(NOT_APPLICABLE, "DATA SHEET", "MDS")
        assert r.match("", "process data sheet for irrigation tank")

    def test_non_matching_title_yields_nothing(self):
        r = rule(NOT_APPLICABLE, "LOOP DIAGRAM", "MLP")
        assert r.match("", "OVERALL PLOT PLAN") == []


class TestWildcardMatching:
    def test_star_separated_terms_must_appear_in_order(self):
        r = rule(NOT_APPLICABLE, "*P&ID*LEGEND*", "LGD")
        assert r.match("", "UTILITY P&ID LEGEND SHEET 1")

    def test_star_allows_text_between_the_terms(self):
        r = rule(NOT_APPLICABLE, "*MATERIAL*SUBMITTAL*", "MATERIAL SUBMITTAL")
        assert r.match("", "MATERIAL AND EQUIPMENT SUBMITTAL FOR TIE WIRE")

    def test_reversed_order_does_not_match(self):
        r = rule(NOT_APPLICABLE, "*P&ID*LEGEND*", "LGD")
        assert r.match("", "LEGEND SHEET FOR THE P&ID") == []

    def test_a_star_wrapped_short_token_matches_inside_a_word(self):
        """`*CV*` is written with stars precisely so it matches loosely."""
        r = rule(NOT_APPLICABLE, "*CV*", "CV", source=NOT_REQUIRED)
        assert r.match("", "CV OF SANTOSH DHAWARE - SENIOR ENGINEER")


class TestDocumentNumberMatching:
    def test_bracketed_token_matches_within_the_number(self):
        r = rule("-TQ-", NOT_APPLICABLE, "TECHNICAL QUERY", source=NOT_REQUIRED)
        assert r.match("4391-0-TQ-0004", "")

    def test_digit_run_matches_four_digits(self):
        r = rule("-13-XXXX", NOT_APPLICABLE, "MDS")
        assert r.match("4391-MEWTP-2-13-0005", "")

    def test_digit_run_does_not_match_letters(self):
        r = rule("-13-XXXX", NOT_APPLICABLE, "MDS")
        assert r.match("4391-MEWTP-2-13-ABCD", "") == []

    def test_digit_run_needs_the_full_run(self):
        r = rule("-43-XXXX", NOT_APPLICABLE, "MIR")
        assert r.match("VEN-MEWTP-5-43-11", "") == []

    def test_document_number_keyword_ignores_the_title(self):
        r = rule("-CV-", NOT_APPLICABLE, "CV", source=NOT_REQUIRED)
        assert r.match("4391-MTY-1-14-0003", "CV OF SOMEONE") == []


class TestTwoSidedRules:
    """A rule with both keywords filled fires when *either* side matches."""

    def test_document_number_alone_fires(self):
        r = rule("-WPR-", "WEEKLY PROGRESS REPORT", "WEEKLY PROGRESS REPORT",
                 source=NOT_REQUIRED)
        matches = r.match("4391-0-WPR-0012", "SOMETHING ELSE ENTIRELY")
        assert [m.field for m in matches] == ["DOCUMENT_NUMBER"]

    def test_title_alone_fires(self):
        r = rule("-WPR-", "WEEKLY PROGRESS REPORT", "WEEKLY PROGRESS REPORT",
                 source=NOT_REQUIRED)
        matches = r.match("4391-0-XXX-0012", "WEEKLY PROGRESS REPORT NO. 12")
        assert [m.field for m in matches] == ["DOCUMENT_TITLE"]

    def test_both_sides_are_reported_when_both_match(self):
        r = rule("-MS-", "*MATERIAL*SUBMITTAL*", "MATERIAL SUBMITTAL")
        matches = r.match("4391-1-MS-0038",
                          "MATERIAL SUBMITTAL FOR FORMWORK RELEASE AGENT")
        assert [m.field for m in matches] == ["DOCUMENT_NUMBER", "DOCUMENT_TITLE"]
        assert {m.doc_type for m in matches} == {"MATERIAL SUBMITTAL"}


class TestRuleBook:
    def test_required_rules_sort_before_not_required(self):
        book = sample_rulebook()
        sources = [r.source for r in book]
        n_required = sources.count(REQUIRED)
        assert sources == ([REQUIRED] * n_required
                           + [NOT_REQUIRED] * (len(sources) - n_required))

    def test_rules_keep_workbook_row_order_within_a_sheet(self):
        book = sample_rulebook()
        for source in (REQUIRED, NOT_REQUIRED):
            rows = [r.row for r in book.by_source(source)]
            assert rows == sorted(rows)

    def test_all_sample_rows_are_usable(self):
        assert len(sample_rulebook()) == len(SAMPLE_RULE_ROWS)

    def test_a_rule_with_no_doc_type_is_dropped(self):
        book = RuleBook.from_rows([RuleRow(REQUIRED, 1, NOT_APPLICABLE,
                                           "LOOP DIAGRAM", "")])
        assert len(book) == 0

    def test_a_rule_with_neither_keyword_is_dropped(self):
        book = RuleBook.from_rows([RuleRow(REQUIRED, 1, NOT_APPLICABLE,
                                           NOT_APPLICABLE, "MDS")])
        assert len(book) == 0

    def test_doc_types_are_listed_in_precedence_order(self):
        assert sample_rulebook().doc_types[0] == "LGD"


HOOK_UP_SPELLINGS = ("HOOK-UP", "HOOK UP", "HOOKUP")


@pytest.mark.parametrize("keyword", HOOK_UP_SPELLINGS)
@pytest.mark.parametrize("spelling", HOOK_UP_SPELLINGS)
def test_the_three_hook_up_spellings_stay_distinct(keyword, spelling):
    """The workbook lists all three because none normalises into another.

    Collapsing punctuation would make one rule cover all three titles and
    erase a distinction the business drew deliberately.
    """
    matched = bool(rule(NOT_APPLICABLE, keyword, "MVA")
                   .match("", f"{spelling} DRAWING FOR TRANSMITTERS"))
    assert matched is (keyword == spelling)
