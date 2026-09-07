"""QatarEnergy <-> vendor matching."""

import pytest

from mdr_engine.identity import normalise_identity
from mdr_engine.matching import MatchStatus, QeIndex, match_vendor_row


@pytest.fixture
def index():
    return QeIndex.build(normalise_identity(d) for d in [
        "4391-MTY-1-G-0071",
        "VEN-4391-MTY-1-12-0002",
        "BQ-IMS-QT-169/DS-01-B",
        "4391-MTY-0-16-0129",
    ])


def row(**kw):
    base = {"PROJECT_DOCUMENT_DRAWING_NO": "", "PROJECT_DOC_NO": "",
            "VENDOR_DOCUMENT_NO": ""}
    base.update(kw)
    return base


class TestExact:
    def test_exact_match_on_project_drawing_no(self, index):
        m = match_vendor_row(row(PROJECT_DOCUMENT_DRAWING_NO="4391-MTY-1-G-0071"), index)
        assert m.status is MatchStatus.EXACT
        assert m.matched_document == "4391-MTY-1-G-0071"
        assert m.source_field == "PROJECT_DOCUMENT_DRAWING_NO"

    def test_exact_match_on_project_doc_no(self, index):
        m = match_vendor_row(row(PROJECT_DOC_NO="VEN-4391-MTY-1-12-0002"), index)
        assert m.status is MatchStatus.EXACT

    def test_reason_is_always_populated(self, index):
        m = match_vendor_row(row(PROJECT_DOCUMENT_DRAWING_NO="4391-MTY-1-G-0071"), index)
        assert m.reason


class TestNormalised:
    def test_separator_variant_matches(self, index):
        m = match_vendor_row(row(PROJECT_DOCUMENT_DRAWING_NO="BQ/IMS/QT-169/DS-01-B"),
                             index)
        assert m.status in (MatchStatus.EXACT, MatchStatus.NORMALIZED_EXACT)

    def test_case_and_space_variant_matches(self, index):
        m = match_vendor_row(row(PROJECT_DOCUMENT_DRAWING_NO="4391 mty 1 g 0071"), index)
        assert m.status is MatchStatus.NORMALIZED_EXACT
        assert m.matched_document == "4391-MTY-1-G-0071"


class TestAlternativeIdentifier:
    def test_ven_prefix_tolerated(self, index):
        """Vendor writes '4391-MTY-1-12-0002'; QE holds the VEN- form."""
        m = match_vendor_row(row(PROJECT_DOCUMENT_DRAWING_NO="4391-MTY-1-12-0002"), index)
        assert m.status is MatchStatus.ALTERNATIVE_IDENTIFIER
        assert m.matched_document == "VEN-4391-MTY-1-12-0002"


class TestPriority:
    def test_project_fields_win_over_vendor_internal_number(self, index):
        m = match_vendor_row(row(PROJECT_DOCUMENT_DRAWING_NO="4391-MTY-1-G-0071",
                                 VENDOR_DOCUMENT_NO="4391-MTY-0-16-0129"), index)
        assert m.source_field == "PROJECT_DOCUMENT_DRAWING_NO"


class TestNegative:
    def test_unknown_identifier_is_not_matched(self, index):
        m = match_vendor_row(row(VENDOR_DOCUMENT_NO="DEW-5718-PP-001"), index)
        assert m.status is MatchStatus.NOT_MATCHED
        assert m.matched_document == ""

    def test_no_identifier_is_reported_distinctly(self, index):
        m = match_vendor_row(row(), index)
        assert m.status is MatchStatus.NO_IDENTIFIER

    def test_null_tokens_are_not_identifiers(self, index):
        m = match_vendor_row(row(PROJECT_DOCUMENT_DRAWING_NO="-",
                                 VENDOR_DOCUMENT_NO="-"), index)
        assert m.status is MatchStatus.NO_IDENTIFIER

    def test_never_guesses_a_partial_match(self, index):
        """A prefix of a real document must not match it."""
        m = match_vendor_row(row(PROJECT_DOCUMENT_DRAWING_NO="4391-MTY-1"), index)
        assert m.status is MatchStatus.NOT_MATCHED


class TestAmbiguity:
    def test_ambiguous_key_matches_nothing_and_lists_candidates(self):
        idx = QeIndex.build(normalise_identity(d)
                            for d in ["4391-0-CV-00XX", "4391-0-CV-00xx"])
        m = match_vendor_row(row(PROJECT_DOCUMENT_DRAWING_NO="4391 0 cv 00xx"), idx)
        assert m.status is MatchStatus.AMBIGUOUS
        assert m.matched_document == ""
        assert len(m.candidates) == 2
