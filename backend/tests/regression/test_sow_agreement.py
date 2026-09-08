"""Agreement with the reference working file's DOC IS REQUIRED SOW column.

Column AM of `QatarEnergy-TN WORKING` is the manual result Phase 2B automates.
It is not a clean target, and the thresholds below are regression floors on
the current, measured behaviour - not a claim that the remaining mismatches
are engine defects. The rules workbook's `DOCUMENT TYPE` sheet and column AM
genuinely disagree for several DOKARs; see
`docs/business-rules/sow-rules.md` for the analysis.

Skipped automatically when the rules or reference workbook is absent.
"""

import hashlib

import pytest

from app.engine.validation.sow import Cause, canonical_sow
from app.services.sow_service import validate_sow
from tests.support.sow import EXPECTED_SOW
from tests.support.workbook import (
    REFERENCE_WORKBOOK, RULES_WORKBOOK, requires_reference_workbook,
)

pytestmark = requires_reference_workbook


@pytest.fixture(scope="module")
def report():
    """One comparison over the whole reference sheet, shared by the module."""
    return validate_sow(REFERENCE_WORKBOOK, RULES_WORKBOOK)


class TestScale:
    def test_the_whole_working_sheet_is_evaluated(self, report):
        assert report.rows_evaluated > 21000

    def test_most_rows_are_accountable(self, report):
        assert report.accountable_rows > 15000

    def test_the_reference_column_is_effectively_fully_populated(self, report):
        assert report.blank_reference_sow == 0


class TestAgreement:
    def test_match_rate_does_not_regress(self, report):
        assert report.match_rate > 0.93

    def test_exact_matches_do_not_regress(self, report):
        assert report.exact_matches >= 15005

    def test_mismatches_do_not_grow(self, report):
        assert len(report.in_scope_mismatches) <= 972


class TestOldRevisionAndNotSow:
    """The two verdicts Phase 2B consumes rather than recomputes."""

    @pytest.mark.parametrize("verdict", ["OLD REV NOT SOW", "NOT SOW"])
    def test_the_verdict_agrees_with_the_reference_on_every_row(self, report,
                                                                verdict):
        row = next(d for d in report.per_doc_type if d["doc_type"] == verdict)
        assert row["mismatches"] == 0
        assert row["matches"] == row["rows"]

    def test_old_rev_not_sow_covers_most_of_the_sheet(self, report):
        row = next(d for d in report.per_doc_type
                   if d["doc_type"] == "OLD REV NOT SOW")
        assert row["rows"] > 9000


class TestEveryMismatchHasACause:
    def test_causes_are_all_known(self, report):
        assert set(report.cause_counts) <= {c.value for c in Cause}

    def test_every_recorded_mismatch_carries_a_cause(self, report):
        assert all(m.cause for m in report.in_scope_mismatches)

    def test_the_causes_account_for_every_in_scope_mismatch(self, report):
        in_scope = {c.value for c in Cause} - {
            Cause.REFERENCE_BLANK.value,
            Cause.REFERENCE_NOT_A_SOW_VALUE.value,
            Cause.DOC_TYPE_ABSENT.value,
            Cause.DOC_TYPE_NOT_IN_SOW_TABLE.value,
        }
        counted = sum(n for c, n in report.cause_counts.items() if c in in_scope)
        assert counted == len(report.in_scope_mismatches)

    def test_every_row_is_accounted_for(self, report):
        assert report.rows_evaluated == (
            report.exact_matches
            + len(report.in_scope_mismatches)
            + report.unknown_doc_type_rows
            + report.doc_type_absent_rows
            + report.non_sow_reference_rows
            + report.blank_reference_sow
        )


class TestKnownDivergences:
    """The mismatch groups the analysis identified, held as regressions."""

    def test_the_hierarchy_divergence_is_systematic(self, report):
        """Every rule whose SOW contains `/HIERARCHY` is written into column
        AM without it. Reported, never patched into the rule table."""
        assert report.cause_counts[Cause.RULE_STATES_HIERARCHY.value] >= 160

    def test_no_hierarchy_rule_agrees_with_the_reference_on_any_row(self, report):
        hierarchy_dokars = {d for d, sow in EXPECTED_SOW.items()
                            if "HIERARCHY" in sow}
        for row in report.per_doc_type:
            if row["doc_type"] in hierarchy_dokars:
                assert row["matches"] == 0, row

    def test_the_reference_overrides_some_in_scope_rows_to_no(self, report):
        """A manual scope decision DOC TYPE does not predict."""
        assert report.cause_counts[Cause.REFERENCE_OVERRIDES_TO_NO.value] >= 380

    def test_spelling_variants_are_counted_as_mismatches_not_matches(self, report):
        """The canonicalisation triages; it never converts a mismatch."""
        variants = [m for m in report.in_scope_mismatches
                    if m.cause == Cause.REFERENCE_SPELLING_VARIANT.value]
        assert variants
        for m in variants:
            assert m.reference_sow != m.calculated_sow
            assert canonical_sow(m.reference_sow) == canonical_sow(m.calculated_sow)

    def test_the_unmapped_doc_types_are_reported_not_guessed(self, report):
        """5,000+ rows carry a DOC TYPE the `DOCUMENT TYPE` sheet omits."""
        assert report.unknown_doc_type_rows > 5000
        labels = {d["doc_type"] for d in report.unmapped_doc_types}
        assert {"OTHER", "GAD", "TNR", "MATERIAL SUBMITTAL"} <= labels

    def test_an_unmapped_doc_type_never_produces_a_sow_value(self, report):
        assert report.blank_calculated_sow >= report.unknown_doc_type_rows


class TestScopeBoundary:
    def test_the_reference_sow_column_is_never_an_input(self, report):
        """Gate D. Every calculated value the run produced is one the rules
        workbook states, or nothing - never a value copied from column AM."""
        stated = set(EXPECTED_SOW.values()) | {"NO"}
        produced = set(report.calculated_sow_counts) - {"(unresolved)"}
        assert produced <= stated

    def test_the_engine_emits_no_idb_status(self, report):
        """Phase 2C is not implemented; no SOW value is an IDB verdict."""
        assert not set(report.calculated_sow_counts) & {
            "COMPLETED", "PENDING", "NO NEED TO CHECK"}

    def test_no_check_status_verdict_is_emitted(self, report):
        """Phase 3B is not implemented."""
        assert not set(report.calculated_sow_counts) & {
            "RECEIVED", "NOT RECEIVED", "TO BE CHECKED"}


class TestSourceIntegrity:
    def test_validating_changes_neither_source_workbook(self):
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (REFERENCE_WORKBOOK, RULES_WORKBOOK)}
        validate_sow(REFERENCE_WORKBOOK, RULES_WORKBOOK)
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (REFERENCE_WORKBOOK, RULES_WORKBOOK)}
        assert before == after
