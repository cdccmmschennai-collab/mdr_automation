"""Document identity normalisation."""

import pytest

from mdr_engine.identity import (
    canonicalise, clean, is_null_token, normalise_identity, strip_ven_prefix,
)


class TestClean:
    def test_collapses_embedded_newlines(self):
        """Workbook cells contain multi-line values such as stacked TN numbers."""
        assert clean("ASMA-TN-0035\nASMA-TN-0030") == "ASMA-TN-0035 ASMA-TN-0030"

    def test_trims_and_collapses_runs_of_space(self):
        assert clean("  4391   MTY  ") == "4391 MTY"

    def test_none_becomes_empty(self):
        assert clean(None) == ""


class TestNullTokens:
    @pytest.mark.parametrize("raw", ["", "-", "  ", "N/A", "#N/A", "none"])
    def test_recognised_null_tokens(self, raw):
        assert is_null_token(raw)

    def test_real_document_number_is_not_null(self):
        assert not is_null_token("4391-MTY-0-16-0129")


class TestCanonicalise:
    def test_separators_and_case_are_removed(self):
        assert canonicalise("4391-MTY-0-16-0129") == "4391MTY0160129"
        assert canonicalise("4391 mty/0.16_0129") == "4391MTY0160129"

    def test_differing_separators_collapse_to_one_key(self):
        assert canonicalise("BQ/IMS/QT-169/DS-02") == canonicalise("BQ-IMS-QT169-DS02")

    def test_case_only_variants_unify(self):
        """The workbook holds both '4391-0-CV-00XX' and '...-00xx'."""
        assert canonicalise("4391-0-CV-00XX") == canonicalise("4391-0-CV-00xx")

    def test_distinct_documents_stay_distinct(self):
        assert canonicalise("4391-MTY-1-19-0051") != canonicalise("4391-MTY-1-19-0052")

    def test_number_segments_are_never_dropped(self):
        """'-001' suffixed documents are genuinely different documents."""
        assert canonicalise("MEWTP-8-83-0001") != canonicalise("MEWTP-8-83-0001-001")


class TestVenPrefix:
    def test_ven_prefix_stripped_from_canonical_key(self):
        assert strip_ven_prefix(canonicalise("VEN-4391-MTY-1-12-0002")) == \
               canonicalise("4391-MTY-1-12-0002")

    def test_non_ven_key_untouched(self):
        assert strip_ven_prefix("4391MTY") == "4391MTY"

    def test_vendor_word_is_not_mistaken_for_prefix(self):
        """Only a leading VEN token is stripped, and only once."""
        assert strip_ven_prefix(canonicalise("VEN-VEN-1")) == "VEN1"


class TestNormaliseIdentity:
    def test_builds_all_three_forms(self):
        ident = normalise_identity("VEN-4391-MTY-1-12-0002")
        assert ident.raw == "VEN-4391-MTY-1-12-0002"
        assert ident.canonical == "VEN4391MTY1120002"
        assert ident.alt_key == "4391MTY1120002"
        assert bool(ident)

    def test_null_identity_is_falsy(self):
        for raw in ["", "-", None]:
            ident = normalise_identity(raw)
            assert ident.is_null
            assert not ident

    def test_raw_value_is_always_preserved(self):
        ident = normalise_identity("  4391-MTY-0-16-0129 ")
        assert ident.raw == "4391-MTY-0-16-0129"
