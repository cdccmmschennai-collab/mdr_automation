"""Status Codes sheet interpretation."""

import pytest

from app.engine.revision.status_codes import (
    IssueCode, ReviewCode, StatusCodeBook, normalise_code,
)

# Mirrors the real 'Status Codes' sheet layout: review codes in cols A/B,
# issue codes in cols D/E/F.
SHEET_ROWS = [
    ("REVIEW CODE FROM QatarEnergy", "DESCRIPTION", None,
     "ISSUE CODE", "DESCRIPTION", "REVISION SEQUENCE"),
    ("CODE-1", "Approved without comments - Resubmission is required.", None,
     "IFC", "ISSUED FOR COMMENTS", "0"),
    ("CODE-2", "Approved with comments - Incorporate and resubmit.", None,
     "RE-IFC", "RE-ISSUED FOR COMMENTS", "1,2,3â€¦ IF QatarEnergy ISSUE CODE AS CODE-3"),
    ("CODE-3", "Not Approved - Work shall not proceed.", None,
     "IFA", "ISSUED FOR APPROVAL", "1,2,3,4.."),
    ("CODE-6", "FOR INFORMATION ONLY", None,
     "RE-IFA", "RE-ISSUED FOR APPROVAL", "NEXT REV AFTER SUBSEQUENT APPROVAL"),
    ("CODE-7", "SEE REMARKS", None, "AFC", "APPROVED FOR CONSTRUCTION", "A,B,C,D"),
    ("CODE-10", "APPROVED", None, "ACH", "APPROVED FOR CONSTRUCTION (WITH HOLD)", "A,B,C,D"),
    ("CODE-11", "CANCELLATION ACCEPTED", None, "ADM", "APPROVED FOR DEMOLITION", "A,B,C,D"),
    (None, None, None, "ASB", "AS-BUILTS", "AFC-GRASS FIELD Z-BROWN FIELD"),
    (None, None, None, "RET", "ISSUED FOR RETENTION", "0,1,2,3"),
    (None, None, None, "CAN", "ISSUED FOR CANCELATION", "1,2,3 OR A,B,C,D"),
    (None, None, None, "IFI", "ISSUED FOR INFORMAITON", "0,1,2,3"),
]


@pytest.fixture
def book():
    return StatusCodeBook.from_rows(SHEET_ROWS)


class TestLoading:
    def test_codes_are_loaded_from_the_sheet_not_hard_coded(self, book):
        assert set(book.review_codes) == {
            "CODE-1", "CODE-2", "CODE-3", "CODE-6", "CODE-7", "CODE-10", "CODE-11"}
        assert {"IFC", "IFA", "AFC", "ASB", "CAN", "IFI"} <= set(book.issue_codes)

    def test_header_row_is_not_ingested_as_a_code(self, book):
        assert "ISSUECODE" not in book.issue_codes


class TestReviewCodes:
    def test_bare_number_resolves_to_a_code(self, book):
        """The STATUS column holds '2' where the sheet says 'CODE-2'."""
        assert book.review("2").code == "CODE-2"
        assert book.review("10").code == "CODE-10"

    def test_prefixed_form_resolves(self, book):
        assert book.review("CODE-3").number == 3

    def test_unknown_value_returns_none(self, book):
        assert book.review("UR") is None
        assert book.review("") is None

    @pytest.mark.parametrize("code,resubmit", [
        ("CODE-1", True), ("CODE-2", True), ("CODE-3", True),
        ("CODE-6", False), ("CODE-10", False), ("CODE-11", False),
    ])
    def test_resubmission_semantics(self, book, code, resubmit):
        assert book.review(code).requires_resubmission is resubmit

    def test_work_may_proceed(self, book):
        assert book.review("CODE-1").work_may_proceed
        assert book.review("CODE-2").work_may_proceed
        assert not book.review("CODE-3").work_may_proceed

    def test_cancellation_code(self, book):
        assert book.review("CODE-11").is_cancellation


class TestIssueCodes:
    def test_casing_variants_normalise(self):
        """The data holds 'AfC', 'Re-AFC' and 'RE--IFA'."""
        assert normalise_code("AfC") == "AFC"
        assert normalise_code("Re-AFC") == "RE-AFC"
        assert normalise_code("RE--IFA") == "RE-IFA"

    def test_reissue_resolves_via_its_base_code(self, book):
        code = book.issue("RE-AFC")
        assert code is not None
        assert code.base_code == "AFC"
        assert code.is_reissue

    def test_malformed_reissue_still_resolves(self, book):
        assert book.issue("RE--IFA").base_code == "IFA"

    def test_base_codes_are_not_reissues(self, book):
        assert not book.issue("IFC").is_reissue

    def test_as_built_detected(self, book):
        assert book.issue("ASB").is_as_built
        assert not book.issue("AFC").is_as_built

    @pytest.mark.parametrize("code,band", [
        ("AFC", "ALPHABETIC"), ("ACH", "ALPHABETIC"), ("ADM", "ALPHABETIC"),
        ("IFC", "NUMERIC"), ("IFA", "NUMERIC"), ("RET", "NUMERIC"), ("IFI", "NUMERIC"),
    ])
    def test_expected_revision_band_from_sheet_text(self, book, code, band):
        assert book.issue(code).expected_revision_band == band

    def test_unknown_issue_code_returns_none(self, book):
        assert book.issue("ZZZ") is None
