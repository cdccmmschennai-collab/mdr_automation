"""`DOC WITH REV`: the first of the five automation columns.

The rule is the working file's own - `DOCUMENT NO.` + '-' + `REV`, which holds
on 21,371 of its 21,372 rows. `tests/regression/test_doc_with_rev_agreement.py`
measures that against the real sheet; this suite pins the edges the sheet does
not happen to exercise.
"""

import pytest

from app.engine.identity.normalisation import doc_with_rev


class TestTheLabel:
    @pytest.mark.parametrize("number,rev,expected", [
        ("VEN-4391-MEWTP-3-04-0005", "0", "VEN-4391-MEWTP-3-04-0005-0"),
        ("ASMA-MG-PR-01-4391-SD-0001", "0", "ASMA-MG-PR-01-4391-SD-0001-0"),
        ("4391-M3UT-6-51-0007-001", "A", "4391-M3UT-6-51-0007-001-A"),
        ("4391-MEWTP-2-13-0005", "12", "4391-MEWTP-2-13-0005-12"),
        ("4391-MG-ASB-0001", "Z", "4391-MG-ASB-0001-Z"),
    ])
    def test_the_number_and_the_revision_are_joined_by_a_dash(self, number,
                                                              rev, expected):
        assert doc_with_rev(number, rev) == expected

    def test_it_is_upper_case(self):
        assert doc_with_rev("ven-mewtp-1-01-0001", "a") == "VEN-MEWTP-1-01-0001-A"

    def test_surrounding_whitespace_is_collapsed(self):
        assert doc_with_rev("  4391-MEWTP-2-13-0005 ", " 0 ") == \
            "4391-MEWTP-2-13-0005-0"

    def test_an_embedded_newline_becomes_a_single_space(self):
        assert doc_with_rev("4391-MEWTP\n2-13-0005", "0") == \
            "4391-MEWTP 2-13-0005-0"


class TestNothingIsInvented:
    @pytest.mark.parametrize("rev", ["", "-", "N/A", "#N/A", None, "NIL"])
    def test_a_document_with_no_revision_keeps_no_dangling_separator(self, rev):
        """232 rows of the input sheet have a blank REV and 64 hold a dash.
        A label ending in '-' would read as revision-blank; the number alone
        reads as what it is."""
        assert doc_with_rev("4391-MEWTP-2-13-0005", rev) == "4391-MEWTP-2-13-0005"

    @pytest.mark.parametrize("number", ["", "-", "N/A", None, "  "])
    def test_a_row_with_no_document_number_has_no_label(self, number):
        assert doc_with_rev(number, "0") == ""

    def test_a_number_that_looks_numeric_is_not_reinterpreted(self):
        assert doc_with_rev("0001", "0") == "0001-0"

    def test_separators_inside_the_number_are_left_alone(self):
        """Identity normalisation collapses separators for *matching*; this
        label is read back against the workbook and must not."""
        assert doc_with_rev("VEN-4391/MTY 1", "B") == "VEN-4391/MTY 1-B"
