"""DOC IDB COMPLETED STATUS resolution: rules, unknowns and scope boundaries.

The SOW verdicts fed in come from the real `DOCUMENT TYPE` sheet - see
`tests/support/sow.py` - so no test invents a scope verdict the workbook does
not state. Column AN is never touched here; it is the answer this stage is
graded against, and `tests/regression/test_idb_agreement.py` does the grading.
"""

import inspect

import pytest

from app.domain.models.idb import (
    CANCELLED, CHECK_OUTCOMES, COMPLETED, COMPLETED_REV_UPDATED,
    FROM_COMPLETION_SOURCE, FROM_SOW_NOT_REQUIRED, GENERAL_SPECIFICATION,
    NO_COMPLETION_SOURCE, NO_NEED_TO_CHECK, PENDING, REFERENCE,
    SOW_NOT_A_VERDICT, TAG_NOT_IN_FMTL, TO_BE_CHECK, UNKNOWN_OUTCOME, UNMAPPED,
    UNRESOLVED_SOW, IdbStatus,
)
from app.domain.models.sow import SowRequirement
from app.engine.idb.resolver import IdbResolver
from tests.support.idb import requirement, sample_idb_resolver
from tests.support.sow import EXPECTED_SOW


@pytest.fixture(scope="module")
def resolver():
    return sample_idb_resolver()


class TestOutOfScopeMeansNoCheckIsDue:
    """Rule 1: 18,704 of the 18,706 rows whose SOW reads `NO` carry
    `NO NEED TO CHECK`."""

    @pytest.mark.parametrize("doc_type", ["OLD REV NOT SOW", "NOT SOW"])
    def test_a_not_sow_verdict_needs_no_check(self, resolver, doc_type):
        status = resolver.resolve(requirement(doc_type))
        assert status.status == NO_NEED_TO_CHECK
        assert status.source == FROM_SOW_NOT_REQUIRED
        assert status.check_required is False

    def test_the_sow_value_is_carried_for_audit(self, resolver):
        assert resolver.resolve(requirement("NOT SOW")).sow == "NO"

    def test_the_doc_type_is_carried_for_audit(self, resolver):
        status = resolver.resolve(requirement("OLD REV NOT SOW"))
        assert status.doc_type == "OLD REV NOT SOW"

    def test_a_recorded_outcome_cannot_override_it(self, resolver):
        """A document needing no check has no check outcome to have. The
        reference agrees: all 300 rows whose submission was cancelled and
        whose SOW reads `NO` carry `NO NEED TO CHECK`."""
        status = resolver.resolve(requirement("NOT SOW"), COMPLETED)
        assert status.status == NO_NEED_TO_CHECK
        assert status.recorded_outcome == ""


class TestInScopeMeansACheckIsDue:
    """Rule 2: an in-scope document needs a check, and its outcome comes from
    a completion source Phase 2C does not have."""

    @pytest.mark.parametrize("dokar", sorted(EXPECTED_SOW))
    def test_every_dokar_in_the_sow_table_needs_a_check(self, resolver, dokar):
        status = resolver.resolve(requirement(dokar))
        assert status.status == TO_BE_CHECK
        assert status.source == NO_COMPLETION_SOURCE
        assert status.check_required is True

    def test_no_completion_source_is_not_reported_as_a_known_outcome(self,
                                                                    resolver):
        status = resolver.resolve(requirement("MDS"))
        assert status.outcome_known is False
        assert status.recorded_outcome == ""

    def test_the_sow_string_is_carried_verbatim(self, resolver):
        assert resolver.resolve(requirement("MDS")).sow == "YES-MTL/DOC IDB"

    def test_to_be_check_is_not_a_claim_that_the_check_was_never_done(self,
                                                                     resolver):
        """It states the requirement, not the outcome - which is exactly why
        the source is recorded alongside it."""
        assert resolver.resolve(requirement("MPI")).source == NO_COMPLETION_SOURCE


class TestRecordedOutcomes:
    """What the resolver does once a completion source states an outcome."""

    @pytest.mark.parametrize("outcome", [
        COMPLETED, COMPLETED_REV_UPDATED, PENDING, CANCELLED, TAG_NOT_IN_FMTL,
        REFERENCE, GENERAL_SPECIFICATION, TO_BE_CHECK,
    ])
    def test_a_stated_outcome_becomes_the_status(self, resolver, outcome):
        status = resolver.resolve(requirement("MDS"), outcome)
        assert status.status == outcome
        assert status.source == FROM_COMPLETION_SOURCE
        assert status.outcome_known is True
        assert status.recorded_outcome == outcome

    @pytest.mark.parametrize("outcome", sorted(CHECK_OUTCOMES))
    def test_every_vocabulary_outcome_is_reachable(self, resolver, outcome):
        """Gate: the engine can emit every status the column carries."""
        assert resolver.resolve(requirement("MPI"), outcome).status == outcome

    def test_a_stated_outcome_is_normalised_not_reinterpreted(self, resolver):
        assert resolver.resolve(requirement("MDS"), " completed ").status \
            == COMPLETED

    @pytest.mark.parametrize("unknown", ["COMPLETE", "REF", "DONE", "RECEIVED"])
    def test_an_outcome_outside_the_vocabulary_is_unmapped(self, resolver,
                                                           unknown):
        status = resolver.resolve(requirement("MDS"), unknown)
        assert status.status == UNMAPPED
        assert status.source == UNKNOWN_OUTCOME
        assert status.recorded_outcome == unknown.strip().upper()

    def test_an_unknown_outcome_never_falls_back_to_a_business_value(self,
                                                                    resolver):
        status = resolver.resolve(requirement("MDS"), "DONE")
        assert status.status not in {NO_NEED_TO_CHECK, TO_BE_CHECK, COMPLETED}


class TestUnresolvedUpstream:
    """A Phase 2B gap must surface as a gap, never as a business value."""

    @pytest.mark.parametrize("doc_type", [
        "OTHER", "GAD", "TNR", "MATERIAL SUBMITTAL", "CV", "MXB-DEM", "VDR",
    ])
    def test_a_doc_type_outside_the_sow_table_is_unmapped(self, resolver,
                                                          doc_type):
        status = resolver.resolve(requirement(doc_type))
        assert status.status == UNMAPPED
        assert status.source == UNRESOLVED_SOW
        assert status.check_required is None

    @pytest.mark.parametrize("empty", ["", None, "-", "N/A"])
    def test_a_missing_doc_type_is_unmapped(self, resolver, empty):
        status = resolver.resolve(requirement(empty))
        assert status.status == UNMAPPED
        assert status.source == UNRESOLVED_SOW

    def test_no_requirement_at_all_is_unmapped(self, resolver):
        status = resolver.resolve()
        assert status.status == UNMAPPED
        assert status.source == UNRESOLVED_SOW

    @pytest.mark.parametrize("junk", ["CANCELLED", "0", "COMMON", "MTL/DOC IDB"])
    def test_a_sow_value_that_states_no_verdict_is_unmapped(self, resolver,
                                                            junk):
        """Column AM carries these. Reading one as `NO` would turn a
        data-entry state into a business decision."""
        status = resolver.resolve(SowRequirement(doc_type="MDS", sow=junk))
        assert status.status == UNMAPPED
        assert status.source == SOW_NOT_A_VERDICT

    def test_unmapped_is_never_no_need_to_check(self, resolver):
        """The whole point: a rule gap and an out-of-scope document are
        different business facts."""
        assert resolver.resolve(requirement("OTHER")).status != NO_NEED_TO_CHECK

    def test_an_unresolved_row_ignores_a_recorded_outcome(self, resolver):
        """Without a scope verdict there is nothing for an outcome to attach
        to, so stating one must not conjure a status."""
        status = resolver.resolve(requirement("OTHER"), COMPLETED)
        assert status.status == UNMAPPED


class TestRevisionInteraction:
    """Revision reaches IDB only through Phase 2A -> Phase 2B."""

    def test_an_old_revision_arrives_as_a_doc_type_not_as_a_flag(self,
                                                                resolver):
        """Phase 1 decides latest/old; Phase 2A turns old into
        `OLD REV NOT SOW`; Phase 2B turns that into `NO`."""
        assert resolver.resolve(requirement("OLD REV NOT SOW")).status \
            == NO_NEED_TO_CHECK

    def test_an_in_scope_document_is_unaffected_by_its_revision(self, resolver):
        """107 of the 127 rows that are not latest yet still in scope read
        `COMPLETED`, so being an old revision does not by itself change the
        status - and the resolver has no revision input with which to try."""
        params = list(inspect.signature(IdbResolver.resolve).parameters)
        assert "revision" not in params and "latest" not in params

    def test_cancellation_is_not_an_input(self, resolver):
        """Of the 7 in-scope rows whose submission was cancelled, the
        reference reads `CANCELLED` 3 times, `COMPLETED` 3 and `PENDING` once.
        Cancellation therefore does not determine the status, and no branch
        here pretends it does."""
        params = list(inspect.signature(IdbResolver.resolve).parameters)
        assert "cancelled" not in params and "status_code" not in params


class TestStatusValue:
    def test_check_required_is_three_valued(self):
        assert IdbStatus(status=TO_BE_CHECK).check_required is True
        assert IdbStatus(status=NO_NEED_TO_CHECK).check_required is False
        assert IdbStatus().check_required is None

    def test_the_default_status_is_unmapped(self):
        assert IdbStatus().status == UNMAPPED
        assert IdbStatus().is_resolved is False

    def test_a_status_is_never_blank(self, resolver):
        """A blank cell would read as 'nothing to say'; `UNMAPPED` says the
        engine does not know, which is a different thing."""
        for doc_type in ("MDS", "NOT SOW", "OTHER", "", "GAD"):
            assert resolver.resolve(requirement(doc_type)).status != ""

    def test_to_dict_round_trips_the_verdict(self, resolver):
        assert resolver.resolve(requirement("MPI")).to_dict() == {
            "status": TO_BE_CHECK,
            "source": NO_COMPLETION_SOURCE,
            "sow": "YES-MTL/DOC IDB",
            "doc_type": "MPI",
            "recorded_outcome": "",
            "check_required": True,
            "outcome_known": False,
        }


class TestScopeBoundary:
    def test_the_resolver_takes_only_a_requirement_and_an_outcome(self):
        """Gate D, structurally: there is no parameter through which the
        reference workbook's column AN could reach the resolver."""
        params = list(inspect.signature(IdbResolver.resolve).parameters)
        assert params == ["self", "requirement", "recorded_outcome"]

    def test_the_resolver_never_sees_a_document_number_or_title(self, resolver):
        """It does not classify and it does not re-derive scope: DOC TYPE is
        Phase 2A's verdict and the SOW string is Phase 2B's, both consumed."""
        assert "classify" not in dir(resolver)
        assert resolver.resolve(requirement("MDS")) \
            == resolver.resolve(requirement("MDS"))

    def test_the_resolver_holds_no_state_between_calls(self, resolver):
        first = resolver.resolve(requirement("MDS"), COMPLETED)
        second = resolver.resolve(requirement("MDS"))
        assert first.status == COMPLETED
        assert second.status == TO_BE_CHECK

    def test_no_status_is_ever_a_check_status_verdict(self, resolver):
        """Phase 3B is not implemented; nothing here emits its vocabulary."""
        emitted = {resolver.resolve(requirement(d)).status
                   for d in ("MDS", "NOT SOW", "OTHER")}
        assert not emitted & {"RECEIVED", "NOT RECEIVED"}

    def test_no_status_is_ever_a_sow_value(self, resolver):
        """A SOW string contains the words `DOC IDB`; it is not an IDB
        status, and Phase 2C never turns one into the other."""
        for dokar, sow in EXPECTED_SOW.items():
            assert resolver.resolve(requirement(dokar)).status != sow
