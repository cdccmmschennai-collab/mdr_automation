"""The Phase 2A -> Phase 2B chain: document -> DOC TYPE -> DOC IS REQUIRED SOW.

Both stages run from verbatim workbook fixtures, so this suite needs no Excel
file, no row or column coordinates, no FastAPI and no frontend. It asserts the
two stages compose: the classifier's DOC TYPE is exactly what the resolver
consumes, and nothing between them re-reads the document.
"""

import pytest

from app.domain.models.sow import FROM_DOCUMENT_TYPE_TABLE, UNMAPPED_DOC_TYPE
from app.engine.classification.classifier import UNCLASSIFIED
from tests.support.rules import sample_classifier
from tests.support.sow import sample_sow_resolver


@pytest.fixture(scope="module")
def pipeline():
    """Phase 2A then Phase 2B, wired the way the real pipeline wires them."""
    classifier = sample_classifier()
    resolver = sample_sow_resolver()

    def run(document_number: str, document_title: str):
        classification = classifier.classify(document_number, document_title)
        return classification, resolver.resolve(classification.doc_type)

    return run


class TestRealDocumentsEndToEnd:
    @pytest.mark.parametrize("number,title,doc_type,sow", [
        ("4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR - NEWTP",
         "MDS", "YES-MTL/DOC IDB"),
        ("VEN-MEWTP-5-43-0011", "SPIR INITIAL: LOCAL PANEL, RCU, VSD",
         "MIR", "YES-FMTL/MTL/BOM/DOC IDB"),
        ("4391-M3UT-4-66-0002", "F&G LOOP DIAGRAMS NGL-3",
         "MLP", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
        ("4391-M3UT-6-51-0007-001", "UTILITY P&ID: LAYDOWN AREA RUNOFF",
         "MXB", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
        ("VEN-MEWTP-2-54-0001", "SINGLE LINE DIAGRAM FOR APFC PANEL",
         "MSL", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
        ("VEN-MEWTP-2-16-0011", "TYPE TEST CERTIFICATE FOR LV BUSDUCT",
         "MTC", "YES-MTL/DOC IDB"),
        ("VEN-MEWTP-4-31-0002", "BILL OF MATERIAL HVAC CONTROL PANEL",
         "MMC", "YES-MTL/BOM/DOC IDB"),
    ])
    def test_a_document_reaches_its_sow_value(self, pipeline, number, title,
                                              doc_type, sow):
        classification, requirement = pipeline(number, title)
        assert classification.doc_type == doc_type
        assert requirement.sow == sow
        assert requirement.source == FROM_DOCUMENT_TYPE_TABLE


class TestStagesCompose:
    def test_the_resolver_consumes_exactly_the_classifier_verdict(self, pipeline):
        classification, requirement = pipeline(
            "4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR - NEWTP")
        assert requirement.doc_type == classification.doc_type

    def test_an_unclassified_document_yields_no_sow_value(self, pipeline):
        """Phase 2A saying nothing must not become a Phase 2B `NO`."""
        classification, requirement = pipeline(
            "4391-XXX-9-99-9999", "SOMETHING NO KEYWORD RULE COVERS")
        assert classification.doc_type == UNCLASSIFIED
        assert requirement.sow == ""
        assert requirement.is_required is None

    def test_a_doc_type_outside_the_sow_table_yields_no_sow_value(self, pipeline):
        """`CV` is a real Phase 2A verdict the `DOCUMENT TYPE` sheet omits."""
        classification, requirement = pipeline(
            "4391-MG-CV-0001", "CV OF THE PROPOSED QA/QC ENGINEER")
        assert classification.doc_type == "CV"
        assert requirement.source == UNMAPPED_DOC_TYPE
        assert requirement.sow == ""


class TestNoLeakageBetweenStages:
    def test_the_sow_stage_does_not_reclassify(self, pipeline):
        """Two documents with the same DOC TYPE get the same SOW, whatever
        their number and title say."""
        _, one = pipeline("4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR")
        _, two = pipeline("VEN-4391-MTY-6-13-0099",
                          "PROCESS DATA SHEET FOR IRRIGATION TANK")
        assert one.sow == two.sow == "YES-MTL/DOC IDB"

    def test_the_sow_stage_emits_no_idb_status(self, pipeline):
        """`YES-MTL/DOC IDB` stays a SOW string; Phase 2C is not implemented."""
        _, requirement = pipeline("4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR")
        assert requirement.sow == "YES-MTL/DOC IDB"
        assert requirement.to_dict().keys() == {
            "doc_type", "sow", "source", "rule_row", "matched_on", "is_required"}
