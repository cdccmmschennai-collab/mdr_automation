"""The Phase 2C rule primitives: the vocabulary, scope reading and outcomes.

Every status asserted here is one the reference column actually carries - see
`tests/support/idb.py` for the census.
"""

import pytest

from app.domain.models.idb import (
    CANCELLED, CHECK_OUTCOMES, COMPLETED, COMPLETED_REV_UPDATED,
    GENERAL_SPECIFICATION, IDB_STATUSES, NO_NEED_TO_CHECK, PENDING, REFERENCE,
    TAG_NOT_IN_FMTL, TO_BE_CHECK, UNMAPPED,
)
from app.engine.idb.rules import normalise, outcome_of, scope_of
from tests.support.idb import AN_CENSUS, AN_STATUS_VALUES


class TestVocabulary:
    def test_every_status_the_reference_states_is_in_the_vocabulary(self):
        """Except the two spelling variants, which are data-entry errors the
        engine must not adopt."""
        variants = {"COMPLETE", "REF"}
        stated = set(AN_STATUS_VALUES) - variants
        assert stated <= IDB_STATUSES

    def test_the_spelling_variants_are_not_in_the_vocabulary(self):
        assert "COMPLETE" not in IDB_STATUSES
        assert "REF" not in IDB_STATUSES

    def test_unmapped_is_a_status_but_not_a_check_outcome(self):
        """It is the engine saying it does not know, not a business value."""
        assert UNMAPPED in IDB_STATUSES
        assert UNMAPPED not in CHECK_OUTCOMES

    def test_no_need_to_check_is_not_a_check_outcome_either(self):
        """It states that no check is due, so no outcome can exist for it."""
        assert NO_NEED_TO_CHECK in IDB_STATUSES
        assert NO_NEED_TO_CHECK not in CHECK_OUTCOMES

    @pytest.mark.parametrize("status", [
        COMPLETED, COMPLETED_REV_UPDATED, PENDING, TO_BE_CHECK, CANCELLED,
        TAG_NOT_IN_FMTL, REFERENCE, GENERAL_SPECIFICATION,
    ])
    def test_each_check_outcome_is_a_value_the_reference_carries(self, status):
        assert status in AN_CENSUS
        assert status in CHECK_OUTCOMES


class TestNormalise:
    @pytest.mark.parametrize("written,expected", [
        ("completed", "COMPLETED"),
        ("  Completed  ", "COMPLETED"),
        ("no need\nto check", "NO NEED TO CHECK"),
        ("COMPLETED (REV UPDATED)", "COMPLETED (REV UPDATED)"),
    ])
    def test_case_and_whitespace_are_collapsed(self, written, expected):
        assert normalise(written) == expected

    def test_punctuation_is_left_alone(self):
        """`COMPLETED (REV UPDATED)` must stay distinct from `COMPLETED`."""
        assert normalise("COMPLETED (REV UPDATED)") != normalise("COMPLETED")


class TestScopeOf:
    @pytest.mark.parametrize("sow", [
        "YES-MTL/DOC IDB", "YES-FMTL/MTL/HIERARCHY/DOC IDB", "YES-DOC IDB",
        "YES-PM IDB/DOC IDB", "YES-COMMON", "yes-mtl/doc idb",
    ])
    def test_a_yes_value_states_a_requirement(self, sow):
        assert scope_of(sow) is True

    def test_the_yee_typo_still_reads_as_a_requirement(self):
        """`YEE-MTL/DOC IDB` appears once in column AM and plainly means yes."""
        assert scope_of("YEE-MTL/DOC IDB") is True

    def test_no_states_out_of_scope(self):
        assert scope_of("NO") is False

    @pytest.mark.parametrize("empty", ["", None, "-", "N/A", "  ", "#N/A"])
    def test_an_absent_value_states_no_verdict(self, empty):
        assert scope_of(empty) is None

    @pytest.mark.parametrize("junk", ["CANCELLED", "0", "COMMON", "MTL/DOC IDB"])
    def test_a_non_verdict_value_states_no_verdict(self, junk):
        """Column AM carries these; none of them says yes or no, so none may
        be read as `NO`."""
        assert scope_of(junk) is None


class TestOutcomeOf:
    @pytest.mark.parametrize("outcome", sorted(CHECK_OUTCOMES))
    def test_every_vocabulary_outcome_is_accepted(self, outcome):
        assert outcome_of(outcome) == outcome

    def test_case_and_spacing_do_not_matter(self):
        assert outcome_of("  completed  ") == COMPLETED

    @pytest.mark.parametrize("variant", ["COMPLETE", "REF"])
    def test_a_spelling_variant_is_rejected_not_repaired(self, variant):
        """Guessing which value was meant is exactly what Phase 2C must not
        do; the validation triage records the variant instead."""
        assert outcome_of(variant) == ""

    @pytest.mark.parametrize("outside", [
        "RECEIVED", "NOT RECEIVED", "YES-MTL/DOC IDB", "OLD REV NOT SOW", "0",
    ])
    def test_a_value_outside_the_vocabulary_is_rejected(self, outside):
        assert outcome_of(outside) == ""

    @pytest.mark.parametrize("empty", ["", None, "-", "N/A"])
    def test_an_absent_outcome_is_empty(self, empty):
        assert outcome_of(empty) == ""

    def test_no_need_to_check_is_not_an_outcome_a_source_can_state(self):
        """Whether a check is due is the engine's decision, not a source's."""
        assert outcome_of(NO_NEED_TO_CHECK) == ""


class TestRuleSource:
    def test_the_rules_are_stated_in_code_not_loaded_from_a_sheet(self):
        """Gate: no sheet of the rules workbook states an IDB status, so
        Phase 2C must not pretend to load one. The module reads no file and
        opens no workbook."""
        import app.engine.idb.rules as rules

        source = open(rules.__file__, encoding="utf-8").read()
        for forbidden in ("open(", "load_workbook", "read_table", "Path("):
            assert forbidden not in source

    def test_the_rules_module_cites_its_evidence(self):
        """The two rules are evidenced by column AN, and the docstring must
        say so - it is the only place the derivation is recorded in code."""
        import app.engine.idb.rules as rules

        assert "18,704 of 18,706" in rules.__doc__
        assert "idb-rules.md" in rules.__doc__
