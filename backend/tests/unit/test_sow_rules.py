"""The SOW rule book: what it loads, how it is keyed, what it refuses.

The rules here are a verbatim copy of the real `DOCUMENT TYPE` sheet - see
`tests/support/sow.py`.
"""

import pytest

from app.engine.sow.rules import (
    DOCUMENT_TYPE, DOKAR, SELF_STATING_VERDICTS, SowRule, SowRuleBook,
    SowRuleRow, normalise,
)
from tests.support.sow import DOCUMENT_TYPE_ROWS, EXPECTED_SOW


@pytest.fixture(scope="module")
def book():
    return SowRuleBook.from_rows(DOCUMENT_TYPE_ROWS)


class TestLoading:
    def test_the_whole_sheet_loads(self, book):
        assert len(book) == 22

    def test_rules_are_held_in_workbook_row_order(self, book):
        assert [r.row for r in book] == sorted(r.row for r in book)

    def test_every_dokar_is_indexed(self, book):
        assert set(book.dokars) == set(EXPECTED_SOW)

    def test_the_sheet_states_seven_distinct_sow_values(self, book):
        """Twenty-two document types share seven scope-of-work strings."""
        assert len(book.sow_values) == 7

    def test_every_sow_value_states_a_requirement(self, book):
        assert all(v.startswith("YES") for v in book.sow_values)


class TestKeying:
    @pytest.mark.parametrize("dokar", sorted(EXPECTED_SOW))
    def test_a_dokar_finds_its_rule(self, book, dokar):
        rule, matched_on = book.lookup(dokar)
        assert rule.sow == EXPECTED_SOW[dokar]
        assert matched_on == DOKAR

    @pytest.mark.parametrize("name,expected", [
        ("EQPT DATA SHEET", "YES-MTL/DOC IDB"),
        ("SPIR", "YES-FMTL/MTL/BOM/DOC IDB"),
        ("SCHEMATIC DIAGRAM", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
        ("TEST CERTIFICATE", "YES-MTL/DOC IDB"),
    ])
    def test_a_document_type_name_finds_its_rule(self, book, name, expected):
        """The sheet names the type and its code on one row, so both key it."""
        rule, matched_on = book.lookup(name)
        assert rule.sow == expected
        assert matched_on == DOCUMENT_TYPE

    def test_an_unknown_label_finds_nothing(self, book):
        assert book.lookup("GAD") == (None, "")

    def test_a_dokar_wins_over_a_document_type_name(self):
        """Stated so that adding a row cannot silently shadow a DOKAR."""
        book = SowRuleBook.from_rows((
            SowRuleRow(3, "OTHER NAME", "MDS", "YES-MTL/DOC IDB"),
            SowRuleRow(4, "MDS", "MZZ", "YES-DOC IDB"),
        ))
        rule, matched_on = book.lookup("MDS")
        assert (rule.sow, matched_on) == ("YES-MTL/DOC IDB", DOKAR)


class TestUnusableRows:
    def test_a_row_without_a_sow_value_is_dropped(self):
        book = SowRuleBook.from_rows((
            SowRuleRow(3, "EQPT DATA SHEET", "MDS", ""),
            SowRuleRow(4, "SPIR", "MIR", "YES-FMTL/MTL/BOM/DOC IDB"),
        ))
        assert len(book) == 1
        assert book.lookup("MDS") == (None, "")

    def test_a_row_with_no_label_at_all_is_dropped(self):
        book = SowRuleBook.from_rows((SowRuleRow(3, "", "", "YES-DOC IDB"),))
        assert len(book) == 0

    def test_is_usable_needs_a_sow_and_a_label(self):
        assert SowRule(3, "", "MDS", "YES-MTL/DOC IDB").is_usable
        assert SowRule(3, "EQPT DATA SHEET", "", "YES-MTL/DOC IDB").is_usable
        assert not SowRule(3, "EQPT DATA SHEET", "MDS", "").is_usable


class TestNormalisation:
    @pytest.mark.parametrize("raw,expected", [
        ("mds", "MDS"),
        ("  MDS  ", "MDS"),
        ("EQPT  DATA\nSHEET", "EQPT DATA SHEET"),
        (None, ""),
    ])
    def test_labels_are_upper_cased_and_whitespace_collapsed(self, raw, expected):
        assert normalise(raw) == expected

    def test_punctuation_is_never_stripped(self):
        """`YES-MTL/DOC IDB` and `YES-MTL/BOM/DOC IDB` differ by separators."""
        assert normalise("YES-MTL/DOC IDB") == "YES-MTL/DOC IDB"


class TestSelfStatingVerdicts:
    def test_the_two_not_sow_verdicts_map_to_no(self):
        assert SELF_STATING_VERDICTS == {
            "OLD REV NOT SOW": "NO", "NOT SOW": "NO"}

    def test_other_is_not_treated_as_a_verdict(self):
        """`OTHER` reads NO in most reference rows but YES in 174 of them, so
        it states no rule - see docs/business-rules/sow-rules.md."""
        assert "OTHER" not in SELF_STATING_VERDICTS
