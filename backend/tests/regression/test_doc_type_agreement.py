"""Agreement with the reference working file's DOC TYPE column.

Column AL of `QatarEnergy-TN WORKING` is the manual result Phase 2A automates.
It is not a clean target: most of its rows hold a scope-of-work or revision
verdict rather than a document type, and the document types it does hold use a
partly different vocabulary from the rules workbook. The thresholds below are
therefore regression floors on the current, measured behaviour - they are not
a claim that the remainder are engine defects. See
`docs/business-rules/classification-rules.md` for the mismatch analysis.

Skipped automatically when the rules or reference workbook is absent.
"""

import pytest

from app.engine.validation.doc_type import (
    NON_DOC_TYPE_VERDICTS, Cause,
)
from app.services.classification_service import validate_doc_types
from tests.support.workbook import (
    REFERENCE_WORKBOOK, RULES_WORKBOOK, requires_reference_workbook,
)

pytestmark = requires_reference_workbook


@pytest.fixture(scope="module")
def report():
    """One comparison over the whole reference sheet, shared by the module."""
    return validate_doc_types(REFERENCE_WORKBOOK, RULES_WORKBOOK)


class TestScale:
    def test_the_whole_working_sheet_is_evaluated(self, report):
        assert report.rows_evaluated > 21000

    def test_most_reference_rows_are_not_doc_types_at_all(self, report):
        """Column AL is dominated by Phase 2B verdicts, not document types."""
        assert report.non_doc_type_reference_rows > report.comparable_rows

    def test_a_useful_number_of_rows_are_comparable(self, report):
        assert report.comparable_rows > 3000


class TestAgreement:
    def test_match_rate_does_not_regress(self, report):
        assert report.match_rate > 0.76

    def test_exact_matches_do_not_regress(self, report):
        assert report.exact_matches >= 2564


class TestEveryMismatchHasACause:
    def test_causes_are_all_known(self, report):
        assert set(report.cause_counts) <= {c.value for c in Cause}

    def test_every_recorded_mismatch_carries_a_cause(self, report):
        assert all(m.cause for m in report.in_scope_mismatches)

    def test_recorded_mismatches_are_only_the_comparable_ones(self, report):
        """Rows with no reference document type are counted, never listed."""
        assert all(m.reference_doc_type
                   and m.reference_doc_type not in NON_DOC_TYPE_VERDICTS
                   for m in report.in_scope_mismatches)

    def test_precedence_explains_almost_no_mismatches(self, report):
        """Choosing a different competing rule would fix very few rows.

        This is the evidence that the remaining gap is vocabulary drift and
        missing rules, not a wrong precedence order.
        """
        competing = report.cause_counts.get(Cause.COMPETING_RULES.value, 0)
        assert competing < 0.01 * report.comparable_rows


class TestScopeBoundary:
    def test_the_reference_doc_type_column_is_never_an_input(self, report):
        """A row whose reference value is a Phase 2B verdict still gets
        classified on its own evidence, or not at all."""
        assert report.rows_evaluated == (
            report.exact_matches
            + len(report.in_scope_mismatches)
            + report.non_doc_type_reference_rows
            + report.blank_reference_rows
        )

    def test_the_engine_never_emits_a_scope_of_work_verdict(self, report):
        assert set(report.engine_doc_type_counts).isdisjoint(NON_DOC_TYPE_VERDICTS)


class TestOldRevisionInteraction:
    def test_old_rev_not_sow_is_concentrated_on_not_latest_rows(self, report):
        """Recorded, not implemented: `OLD REV NOT SOW` tracks LATEST/NOT
        LATEST, which makes it a Phase 2B revision/SOW verdict rather than a
        DOC TYPE. Phase 2A must not reproduce it."""
        interaction = report.latest_flag_interaction
        not_latest = interaction.get("NL / OLD REV NOT SOW", 0)
        latest = interaction.get("L / OLD REV NOT SOW", 0)
        assert not_latest > 9000
        assert latest < 100
