"""Agreement with the reference working file's DOC IDB COMPLETED STATUS.

Column AN of `QatarEnergy-TN WORKING` is the manual result Phase 2C automates.
Half of it is a rule the engine reproduces; the other half records the outcome
of a check performed against the IDB folder and the FMTL, neither of which is
in any workbook this project reads. The thresholds below are regression floors
on the current, measured behaviour - not a claim that the remaining mismatches
are engine defects. See `docs/business-rules/idb-rules.md`.

Skipped automatically when the rules or reference workbook is absent.
"""

import hashlib

import pytest

from app.domain.models.idb import (
    NO_NEED_TO_CHECK, TO_BE_CHECK, UNMAPPED,
)
from app.engine.validation.idb import (
    Cause, canonical_status, is_idb_status,
)
from app.services.idb_service import validate_idb
from tests.support.idb import AN_CENSUS, WORKING_ROW_COUNT
from tests.support.sow import EXPECTED_SOW
from tests.support.workbook import (
    REFERENCE_WORKBOOK, RULES_WORKBOOK, requires_reference_workbook,
)

pytestmark = requires_reference_workbook


@pytest.fixture(scope="module")
def report():
    """One comparison over the whole reference sheet, shared by the module."""
    return validate_idb(REFERENCE_WORKBOOK, RULES_WORKBOOK)


class TestScale:
    def test_the_whole_working_sheet_is_evaluated(self, report):
        assert report.rows_evaluated == WORKING_ROW_COUNT

    def test_most_rows_are_accountable(self, report):
        assert report.accountable_rows > 15000

    def test_the_reference_column_is_effectively_fully_populated(self, report):
        assert report.blank_reference_idb == 2


class TestTheCensusStillHolds:
    """`tests/support/idb.py` records what column AN contains. The unit suite
    reasons from that census, so the real file must still match it."""

    def test_every_census_value_is_present_with_its_count(self, report):
        counts = dict(report.reference_idb_counts)
        counts[""] = counts.pop("(blank)", 0)
        assert counts == AN_CENSUS

    def test_the_census_accounts_for_every_row(self):
        assert sum(AN_CENSUS.values()) == WORKING_ROW_COUNT

    def test_no_value_outside_the_census_has_appeared(self, report):
        seen = set(report.reference_idb_counts) - {"(blank)"}
        assert seen <= set(AN_CENSUS)


class TestAgreement:
    def test_exact_match_rate_does_not_regress(self, report):
        assert report.match_rate > 0.855

    def test_exact_matches_do_not_regress(self, report):
        assert report.exact_matches >= 13689

    def test_mismatches_do_not_grow(self, report):
        assert report.in_scope_mismatch_count <= 2290

    def test_the_check_due_rate_is_the_number_that_grades_the_rules(self, report):
        """Whether an IDB check is due is the half of column AN Phase 2C
        decides on its own, and it decides it for 97.5% of accountable rows."""
        assert report.requirement_rate > 0.975
        assert report.requirement_matches >= 15586

    def test_the_check_due_rate_beats_the_exact_rate(self, report):
        """Because the gap between them is the missing completion source, not
        a wrong rule."""
        assert report.requirement_rate > report.match_rate


class TestRuleOne:
    """Out of scope means no check is due."""

    @pytest.mark.parametrize("verdict", ["OLD REV NOT SOW", "NOT SOW"])
    def test_the_verdict_agrees_with_the_reference_on_every_row(self, report,
                                                                verdict):
        row = next(d for d in report.per_doc_type if d["doc_type"] == verdict)
        assert row["mismatches"] == 0
        assert row["matches"] == row["rows"]

    def test_it_covers_most_of_the_sheet(self, report):
        rows = sum(d["rows"] for d in report.per_doc_type
                   if d["doc_type"] in ("OLD REV NOT SOW", "NOT SOW"))
        assert rows == 13582

    def test_every_no_need_to_check_the_engine_emits_is_correct(self, report):
        """13,582 rows, no exceptions - the strongest rule in the phase."""
        assert report.calculated_idb_counts[NO_NEED_TO_CHECK] == 13582
        wrong = [m for m in report.recorded_mismatches
                 if m.calculated_idb == NO_NEED_TO_CHECK]
        assert wrong == []


class TestRuleTwo:
    """In scope means a check is due, and its outcome lives elsewhere."""

    def test_every_in_scope_row_resolves_to_to_be_check(self, report):
        assert report.calculated_idb_counts[TO_BE_CHECK] == 2402

    def test_no_completion_source_exists_so_none_is_claimed(self, report):
        """The engine emits exactly three statuses, and no recorded outcome
        is among them."""
        assert set(report.calculated_idb_counts) == {
            NO_NEED_TO_CHECK, TO_BE_CHECK, UNMAPPED}

    def test_the_missing_outcomes_are_counted_not_hidden(self, report):
        assert report.cause_counts[
            Cause.COMPLETION_EVIDENCE_NOT_AVAILABLE.value] >= 1876


class TestEveryMismatchHasACause:
    def test_causes_are_all_known(self, report):
        assert set(report.cause_counts) <= {c.value for c in Cause}

    def test_every_recorded_mismatch_carries_a_cause(self, report):
        assert all(m.cause for m in report.recorded_mismatches)

    def test_the_causes_account_for_every_in_scope_mismatch(self, report):
        out_of_scope = {
            Cause.REFERENCE_BLANK.value,
            Cause.REFERENCE_NOT_AN_IDB_VALUE.value,
            Cause.UPSTREAM_SOW_UNRESOLVED.value,
        }
        counted = sum(n for c, n in report.cause_counts.items()
                      if c not in out_of_scope)
        assert counted == report.in_scope_mismatch_count

    def test_every_row_is_accounted_for(self, report):
        assert report.rows_evaluated == (
            report.exact_matches
            + report.in_scope_mismatch_count
            + report.upstream_unresolved_rows
            + report.non_idb_reference_rows
            + report.blank_reference_idb
        )


class TestKnownDivergences:
    """The mismatch groups the analysis identified, held as regressions."""

    def test_only_two_rows_question_the_phase_2c_rules(self, report):
        """Both are in-scope rows the working sheet marks `NO NEED TO CHECK`
        while its own column AM marks them in scope - the sheet contradicting
        itself. Reported, never patched into the rules."""
        assert report.cause_counts[
            Cause.RULE_DISAGREES_WITH_REFERENCE.value] == 2

    def test_both_of_those_rows_are_recorded_as_examples(self, report):
        """The per-cause cap exists so the smallest and most important group
        is never crowded out of the report by the largest."""
        rows = [m for m in report.recorded_mismatches
                if m.cause == Cause.RULE_DISAGREES_WITH_REFERENCE.value]
        assert len(rows) == 2
        for m in rows:
            assert m.reference_idb == NO_NEED_TO_CHECK
            assert m.calculated_idb == TO_BE_CHECK
            assert m.reference_sow.startswith("YES")

    def test_every_cause_is_illustrated_by_at_least_one_example(self, report):
        in_scope = {c for c in report.cause_counts
                    if c not in {Cause.REFERENCE_BLANK.value,
                                 Cause.REFERENCE_NOT_AN_IDB_VALUE.value,
                                 Cause.UPSTREAM_SOW_UNRESOLVED.value}}
        illustrated = {m.cause for m in report.recorded_mismatches}
        assert in_scope == illustrated

    def test_the_upstream_sow_gap_is_the_largest_group(self, report):
        """5,384 rows carry a DOC TYPE the `DOCUMENT TYPE` sheet omits, so
        Phase 2B states no scope verdict and Phase 2C cannot start."""
        assert report.upstream_unresolved_rows >= 5384
        labels = {d["doc_type"] for d in report.upstream_unresolved_doc_types}
        assert {"OTHER", "GAD", "TNR", "MATERIAL SUBMITTAL"} <= labels

    def test_the_phase_2b_override_is_reported_as_upstream(self, report):
        """Phase 2B already records these as REFERENCE_OVERRIDES_TO_NO: the
        rules sheet puts the DOC TYPE in scope and column AM overrides it."""
        assert report.cause_counts[Cause.UPSTREAM_SOW_OVERRIDDEN.value] >= 391
        for m in report.recorded_mismatches:
            if m.cause == Cause.UPSTREAM_SOW_OVERRIDDEN.value:
                assert m.reference_sow == "NO"
                assert m.calculated_sow.startswith("YES")

    def test_the_not_generatable_values_are_reported_not_guessed(self, report):
        """`GENERAL SPECIFICATION`, `REFERENCE` and `TAG NOT IN FMTL` are
        human judgements or need the FMTL. 14 + 2 + 3 rows."""
        assert report.cause_counts[
            Cause.REFERENCE_VALUE_NOT_GENERATABLE.value] == 19

    def test_spelling_variants_are_counted_as_mismatches_not_matches(self, report):
        """The canonicalisation triages; it never converts a mismatch."""
        variants = [m for m in report.recorded_mismatches
                    if m.cause == Cause.REFERENCE_SPELLING_VARIANT.value]
        assert len(variants) == 2
        for m in variants:
            assert m.reference_idb != m.calculated_idb
            assert canonical_status(m.reference_idb) != m.reference_idb

    def test_the_non_status_reference_values_are_excluded(self, report):
        """The seven `0` cells state nothing to compare against."""
        assert report.non_idb_reference_rows == 7
        assert not is_idb_status("0")


class TestScopeBoundary:
    def test_the_reference_idb_column_is_never_an_input(self, report):
        """Gate D. Every value the run produced is one of the three the rules
        can state - never a value copied from column AN."""
        produced = set(report.calculated_idb_counts)
        assert produced == {NO_NEED_TO_CHECK, TO_BE_CHECK, UNMAPPED}

    def test_the_engine_produced_no_recorded_outcome(self, report):
        """No completion source ran, so no row may carry one."""
        assert "COMPLETED" not in report.calculated_idb_counts
        assert "PENDING" not in report.calculated_idb_counts
        assert "CANCELLED" not in report.calculated_idb_counts

    def test_the_engine_never_leaves_a_status_blank(self, report):
        """A rule gap is `UNMAPPED`, which is a statement; blank is not."""
        assert report.blank_calculated_idb == 0
        assert report.unmapped_calculated_idb == 5388

    def test_no_check_status_verdict_is_emitted(self, report):
        """Phase 3B is not implemented."""
        assert not set(report.calculated_idb_counts) & {
            "RECEIVED", "NOT RECEIVED"}

    def test_no_sow_value_is_emitted_as_an_idb_status(self, report):
        """Phase 2B's strings contain the words `DOC IDB`; none is one."""
        assert not set(report.calculated_idb_counts) & set(EXPECTED_SOW.values())


class TestSourceIntegrity:
    def test_validating_changes_neither_source_workbook(self):
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (REFERENCE_WORKBOOK, RULES_WORKBOOK)}
        validate_idb(REFERENCE_WORKBOOK, RULES_WORKBOOK)
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (REFERENCE_WORKBOOK, RULES_WORKBOOK)}
        assert before == after
