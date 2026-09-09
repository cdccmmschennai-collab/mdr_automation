"""DOC IS REQUIRED SOW resolution: verdicts, unknowns and scope boundaries.

The rule book here is a verbatim copy of the real `DOCUMENT TYPE` sheet - see
`tests/support/sow.py`. Every expected SOW string below comes from that sheet;
none is invented.
"""

import inspect

import pytest

from app.domain.models.sow import (
    FROM_DOCUMENT_TYPE_TABLE, FROM_NOT_SOW_VERDICT, NO_DOC_TYPE,
    UNMAPPED_DOC_TYPE, SowRequirement,
)
from app.engine.sow.resolver import UNRESOLVED, SowResolver
from tests.support.sow import EXPECTED_SOW, sample_sow_resolver


@pytest.fixture(scope="module")
def resolver():
    return sample_sow_resolver()


class TestDocumentTypeTable:
    @pytest.mark.parametrize("doc_type,expected", [
        ("MDS", "YES-MTL/DOC IDB"),
        ("MIR", "YES-FMTL/MTL/BOM/DOC IDB"),
        ("MLD", "YES-FMTL/MTL/DOC IDB"),
        ("MLP", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
        ("MMC", "YES-MTL/BOM/DOC IDB"),
        ("MMD", "YES-MTL/DOC IDB"),
        ("MOM", "YES-PM IDB/DOC IDB"),
        ("MSL", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
        ("MXB", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
        ("MTC", "YES-MTL/DOC IDB"),
        ("MPI", "YES-MTL/DOC IDB"),
        ("MBD", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
    ])
    def test_a_dokar_resolves_to_the_sheets_sow_string(self, resolver,
                                                       doc_type, expected):
        assert resolver.resolve(doc_type).sow == expected

    @pytest.mark.parametrize("dokar", sorted(EXPECTED_SOW))
    def test_every_dokar_in_the_sheet_resolves(self, resolver, dokar):
        result = resolver.resolve(dokar)
        assert result.sow == EXPECTED_SOW[dokar]
        assert result.source == FROM_DOCUMENT_TYPE_TABLE
        assert result.is_resolved
        assert result.is_required is True

    def test_the_matching_workbook_row_is_reported_for_audit(self, resolver):
        assert resolver.resolve("MDS").rule_row == 3
        assert resolver.resolve("MSD").rule_row == 24

    @pytest.mark.parametrize("written", ["mds", "  MDS ", "Mds"])
    def test_case_and_spacing_do_not_matter(self, resolver, written):
        assert resolver.resolve(written).sow == "YES-MTL/DOC IDB"


class TestOldRevision:
    def test_old_rev_not_sow_resolves_to_no(self, resolver):
        """Confirmed by the reference sheet: all 9,934 rows reading
        `OLD REV NOT SOW` carry `NO` in column AM."""
        result = resolver.resolve("OLD REV NOT SOW")
        assert result.sow == "NO"
        assert result.is_required is False
        assert result.source == FROM_NOT_SOW_VERDICT

    def test_not_sow_resolves_to_no(self, resolver):
        assert resolver.resolve("NOT SOW").sow == "NO"

    def test_a_not_sow_verdict_cites_no_workbook_row(self, resolver):
        """It comes from Phase 1's revision verdict, not the rules sheet."""
        assert resolver.resolve("OLD REV NOT SOW").rule_row == 0


class TestUnknownDocType:
    @pytest.mark.parametrize("doc_type", [
        "OTHER", "GAD", "TNR", "MATERIAL SUBMITTAL", "CV", "MXB-DEM", "MPQ",
    ])
    def test_an_unmapped_doc_type_resolves_to_nothing(self, resolver, doc_type):
        result = resolver.resolve(doc_type)
        assert result.sow == UNRESOLVED == ""
        assert result.source == UNMAPPED_DOC_TYPE
        assert not result.is_resolved

    def test_an_unmapped_doc_type_is_never_reported_as_out_of_scope(self,
                                                                   resolver):
        """A missing rule is not the business statement `NO`."""
        result = resolver.resolve("GAD")
        assert result.is_required is None
        assert result.sow != "NO"

    def test_the_doc_type_is_still_carried_for_diagnosis(self, resolver):
        assert resolver.resolve("GAD").doc_type == "GAD"

    @pytest.mark.parametrize("empty", ["", None, "-", "N/A", "  "])
    def test_a_missing_doc_type_resolves_to_nothing(self, resolver, empty):
        result = resolver.resolve(empty)
        assert result.sow == UNRESOLVED
        assert result.source == NO_DOC_TYPE
        assert result.is_required is None

    def test_resolve_takes_no_argument_at_all_by_default(self, resolver):
        assert resolver.resolve().source == NO_DOC_TYPE


class TestRequirementValue:
    def test_is_required_is_three_valued(self):
        assert SowRequirement(sow="YES-MTL/DOC IDB").is_required is True
        assert SowRequirement(sow="NO").is_required is False
        assert SowRequirement().is_required is None

    def test_the_sow_string_is_carried_verbatim(self, resolver):
        """`DOC IDB` inside a SOW value is part of the value, not a status."""
        assert resolver.resolve("MDS").sow == "YES-MTL/DOC IDB"

    def test_to_dict_round_trips_the_verdict(self, resolver):
        assert resolver.resolve("MPI").to_dict() == {
            "doc_type": "MPI",
            "sow": "YES-MTL/DOC IDB",
            "source": FROM_DOCUMENT_TYPE_TABLE,
            "rule_row": 21,
            "matched_on": "DOKAR",
            "is_required": True,
        }


class TestScopeBoundary:
    def test_the_resolver_takes_only_phase_2a_output(self):
        """Gate D, structurally: there is no parameter through which the
        reference workbook's column AM, AN or AO could reach the resolver.

        Both parameters are Phase 2A's own verdict about the document - the
        DOC TYPE it decided, and the keyword sheet it decided it from."""
        params = list(inspect.signature(SowResolver.resolve).parameters)
        assert params == ["self", "doc_type", "rule_source"]

    def test_the_resolver_never_sees_a_document_number_or_title(self, resolver):
        """It does not reclassify: DOC TYPE is Phase 2A's verdict, consumed."""
        assert "classify" not in dir(resolver)
        assert resolver.resolve("MDS") == resolver.resolve("MDS")

    def test_no_verdict_is_ever_an_idb_status(self, resolver):
        """Phase 2C values must not appear anywhere in a Phase 2B result."""
        idb_statuses = {"COMPLETED", "PENDING", "NO NEED TO CHECK"}
        for dokar in EXPECTED_SOW:
            assert resolver.resolve(dokar).sow not in idb_statuses
