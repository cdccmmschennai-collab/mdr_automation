"""`DOC WITH REV` against column AK of `QatarEnergy-TN WORKING`.

Column AK is the manually maintained label the first automation column
replaces, and it is the evidence for the rule
`engine.identity.normalisation.doc_with_rev` implements. This suite measures
the rule against all 21,372 rows of it, so a change to the rule has to change
a measured number rather than a comment.

The 86 rows that do not match exactly are not defects; each is a place where
the manual label is worse than the automated one, and each is counted
separately below so that a *new* kind of disagreement fails the suite rather
than hiding inside a tolerance. In summary:

* 53 rows have no DOCUMENT NO., where the manual formula produced `--0` or
  `---` for a row that names no document at all;
* 26 rows have a document number but no REV, where it left a dangling
  separator (`ISO-Index Sys-001--`);
*  6 rows differ only in case, because the automation writes upper case
  throughout, as the rest of the workbook does;
*  1 row differs only by a trailing space inside the document number
  (`VEN-MEWTP-5-25-0015 -0`).

The reference workbook is read only, and column AK is an *expected answer*
here - never an input to anything the engine computes.
"""

import inspect

import pytest

from app.core.config import settings
from app.engine.identity.normalisation import (
    clean, doc_with_rev, is_null_token,
)
from app.infrastructure.excel.reference_workbook import ReferenceWorkbookReader
from tests.support.workbook import REFERENCE_WORKBOOK, requires_reference_workbook

pytestmark = requires_reference_workbook

EXPECTED_ROWS = 21372
#: Rows whose manual label the automation reproduces character for character.
EXPECTED_EXACT = 21286
#: The four kinds of disagreement, as measured.
EXPECTED_NO_DOCUMENT_NO = 53
EXPECTED_NO_REVISION = 26
EXPECTED_CASE_ONLY = 6
EXPECTED_WHITESPACE_ONLY = 1
#: Rows that agree once case and whitespace are set aside - the measure of the
#: rule itself, as opposed to the house style it is written in.
EXPECTED_EQUIVALENT = 21293


@pytest.fixture(scope="module")
def rows():
    reference = REFERENCE_WORKBOOK or settings.default_reference_workbook()
    return ReferenceWorkbookReader(reference).read_working_rows()[0]


@pytest.fixture(scope="module")
def disagreements(rows):
    return [r for r in rows
            if doc_with_rev(r.document_no, r.rev) != r.doc_with_rev]


def _loose(text: str) -> str:
    return clean(text).upper().replace(" ", "")


class TestAgreementWithTheManualColumn:
    def test_the_sheet_still_has_the_rows_the_measurement_was_taken_over(self,
                                                                        rows):
        assert len(rows) == EXPECTED_ROWS

    def test_every_reference_row_carries_a_label(self, rows):
        assert all(r.doc_with_rev for r in rows)

    def test_the_exact_agreement_count_is_what_was_measured(self, rows,
                                                            disagreements):
        assert len(rows) - len(disagreements) == EXPECTED_EXACT

    def test_the_agreement_rate_is_over_99_percent(self, rows, disagreements):
        assert (len(rows) - len(disagreements)) / len(rows) > 0.995


class TestEveryDisagreementIsAccountedFor:
    """Four known causes, and no fifth."""

    def test_the_total_is_what_was_measured(self, disagreements):
        assert len(disagreements) == (
            EXPECTED_NO_REVISION + EXPECTED_NO_DOCUMENT_NO
            + EXPECTED_CASE_ONLY + EXPECTED_WHITESPACE_ONLY)

    def test_the_rows_with_no_revision_lose_a_dangling_separator(self,
                                                                disagreements):
        rows = [r for r in disagreements
                if not is_null_token(r.document_no) and is_null_token(r.rev)]
        assert len(rows) == EXPECTED_NO_REVISION
        for row in rows:
            assert row.doc_with_rev.endswith("--")
            assert doc_with_rev(row.document_no, row.rev) == \
                clean(row.document_no).upper()

    def test_the_rows_with_no_document_number_get_no_label(self,
                                                           disagreements):
        rows = [r for r in disagreements if is_null_token(r.document_no)]
        assert len(rows) == EXPECTED_NO_DOCUMENT_NO
        for row in rows:
            assert doc_with_rev(row.document_no, row.rev) == ""

    def test_the_remaining_rows_differ_only_in_case_or_whitespace(self,
                                                                  disagreements):
        rows = [r for r in disagreements
                if not is_null_token(r.rev) and not is_null_token(r.document_no)]
        assert len(rows) == EXPECTED_CASE_ONLY + EXPECTED_WHITESPACE_ONLY
        for row in rows:
            assert _loose(doc_with_rev(row.document_no, row.rev)) == \
                _loose(row.doc_with_rev)

    def test_exactly_one_of_them_is_the_trailing_space_row(self,
                                                           disagreements):
        rows = [r for r in disagreements
                if not is_null_token(r.rev) and not is_null_token(r.document_no)
                and clean(r.doc_with_rev).upper()
                != doc_with_rev(r.document_no, r.rev)]
        assert [r.source_row for r in rows] == [3618]

    def test_setting_case_and_whitespace_aside_the_rule_agrees(self, rows):
        equivalent = sum(
            1 for r in rows
            if _loose(doc_with_rev(r.document_no, r.rev)) == _loose(r.doc_with_rev))
        assert equivalent == EXPECTED_EQUIVALENT


class TestTheColumnIsNeverAnInput:
    def test_the_engine_helper_takes_a_number_and_a_revision_only(self):
        assert list(inspect.signature(doc_with_rev).parameters) == \
            ["document_no", "revision"]

    def test_the_label_is_derived_not_looked_up(self):
        """A number that appears in no workbook still gets a label, so the
        helper cannot be reading one out of column AK."""
        assert doc_with_rev("9999-NOSUCH-0-00-0000", "Q") == \
            "9999-NOSUCH-0-00-0000-Q"
