"""The Phase 2A -> 2B -> 2C chain: document -> DOC TYPE -> SOW -> IDB status.

All three stages run from verbatim workbook fixtures, so this suite needs no
Excel file, no row or column coordinates, no FastAPI and no frontend. It
asserts the stages compose - each consumes exactly the previous one's verdict
- and that the Phase 2C engine stays independent of the layers around it.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from app.domain.models.idb import (
    COMPLETED, FROM_SOW_NOT_REQUIRED, NO_COMPLETION_SOURCE, NO_NEED_TO_CHECK,
    TO_BE_CHECK, UNMAPPED, UNRESOLVED_SOW,
)
from app.engine.classification.classifier import UNCLASSIFIED
from tests.support.idb import sample_idb_resolver
from tests.support.rules import sample_classifier
from tests.support.sow import sample_sow_resolver

#: backend/app - the tree the boundary checks walk.
APP = Path(__file__).resolve().parents[2] / "app"

#: The Phase 2C engine and the domain model it returns. Nothing else may be
#: reachable from them.
IDB_MODULES = [
    APP / "engine" / "idb" / "__init__.py",
    APP / "engine" / "idb" / "rules.py",
    APP / "engine" / "idb" / "resolver.py",
    APP / "domain" / "models" / "idb.py",
]


@pytest.fixture(scope="module")
def pipeline():
    """2A then 2B then 2C, wired the way the real pipeline wires them."""
    classifier = sample_classifier()
    sow_resolver = sample_sow_resolver()
    idb_resolver = sample_idb_resolver()

    def run(document_number: str, document_title: str):
        classification = classifier.classify(document_number, document_title)
        requirement = sow_resolver.resolve(classification.doc_type)
        return classification, requirement, idb_resolver.resolve(requirement)

    return run


class TestRealDocumentsEndToEnd:
    @pytest.mark.parametrize("number,title,doc_type,sow,idb", [
        ("4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR - NEWTP",
         "MDS", "YES-MTL/DOC IDB", TO_BE_CHECK),
        ("VEN-MEWTP-5-43-0011", "SPIR INITIAL: LOCAL PANEL, RCU, VSD",
         "MIR", "YES-FMTL/MTL/BOM/DOC IDB", TO_BE_CHECK),
        ("4391-M3UT-6-51-0007-001", "UTILITY P&ID: LAYDOWN AREA RUNOFF",
         "MXB", "YES-FMTL/MTL/HIERARCHY/DOC IDB", TO_BE_CHECK),
        ("VEN-MEWTP-2-16-0011", "TYPE TEST CERTIFICATE FOR LV BUSDUCT",
         "MTC", "YES-MTL/DOC IDB", TO_BE_CHECK),
    ])
    def test_an_in_scope_document_reaches_to_be_check(self, pipeline, number,
                                                      title, doc_type, sow, idb):
        classification, requirement, status = pipeline(number, title)
        assert classification.doc_type == doc_type
        assert requirement.sow == sow
        assert status.status == idb
        assert status.source == NO_COMPLETION_SOURCE

    @pytest.mark.parametrize("number,title", [
        ("4391-MG-WPR-0041", "WEEKLY PROGRESS REPORT - MARCH 2026"),
        ("4391-MG-TQ-0007", "TECHNICAL QUERY ON TANK FOUNDATION"),
        ("4391-MG-NCR-0012", "NON CONFORMANCE REPORT - WELDING"),
    ])
    def test_a_not_required_doc_type_is_still_a_sow_table_gap(self, pipeline,
                                                              number, title):
        """These classify to a NOT REQUIRED type, which Phase 2A reports as a
        document type the `DOCUMENT TYPE` sheet does not cover - so the chain
        must report a gap, not `NO NEED TO CHECK`."""
        _, requirement, status = pipeline(number, title)
        assert requirement.sow == ""
        assert status.status == UNMAPPED

    def test_an_old_revision_verdict_reaches_no_need_to_check(self, pipeline):
        """Phase 1's old-revision verdict arrives as a DOC TYPE, and that is
        the only route by which revision affects the IDB status."""
        sow_resolver = sample_sow_resolver()
        idb_resolver = sample_idb_resolver()
        status = idb_resolver.resolve(sow_resolver.resolve("OLD REV NOT SOW"))
        assert status.status == NO_NEED_TO_CHECK
        assert status.source == FROM_SOW_NOT_REQUIRED


class TestStagesCompose:
    def test_the_idb_stage_consumes_exactly_the_sow_verdict(self, pipeline):
        _, requirement, status = pipeline(
            "4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR - NEWTP")
        assert status.sow == requirement.sow
        assert status.doc_type == requirement.doc_type

    def test_an_unclassified_document_yields_no_idb_status(self, pipeline):
        """Phase 2A saying nothing must not become a Phase 2C business
        value."""
        classification, _, status = pipeline(
            "4391-XXX-9-99-9999", "SOMETHING NO KEYWORD RULE COVERS")
        assert classification.doc_type == UNCLASSIFIED
        assert status.status == UNMAPPED
        assert status.source == UNRESOLVED_SOW
        assert status.check_required is None

    def test_a_doc_type_outside_the_sow_table_yields_no_idb_status(self,
                                                                  pipeline):
        """`CV` is a real Phase 2A verdict the `DOCUMENT TYPE` sheet omits."""
        classification, _, status = pipeline(
            "4391-MG-CV-0001", "CV OF THE PROPOSED QA/QC ENGINEER")
        assert classification.doc_type == "CV"
        assert status.status == UNMAPPED

    def test_the_idb_stage_does_not_reclassify(self, pipeline):
        """Two documents with the same DOC TYPE get the same status, whatever
        their number and title say."""
        _, _, one = pipeline("4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR")
        _, _, two = pipeline("VEN-4391-MTY-6-13-0099",
                             "PROCESS DATA SHEET FOR IRRIGATION TANK")
        assert one.status == two.status == TO_BE_CHECK
        assert one.sow == two.sow


class TestNoLeakageIntoTheEngine:
    def test_no_stage_receives_a_reference_column(self, pipeline):
        """Gate D. The chain's whole input is a document number and title;
        columns AM, AN and AO appear nowhere in it."""
        classification, requirement, status = pipeline(
            "4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR - NEWTP")
        produced = {classification.doc_type, requirement.sow, status.status}
        assert "COMPLETED" not in produced
        assert status.recorded_outcome == ""

    def test_the_idb_stage_emits_no_check_status(self, pipeline):
        """Phase 3B is not implemented."""
        _, _, status = pipeline("4391-MEWTP-2-13-0005", "DATASHEET FOR LV MOTOR")
        assert status.to_dict().keys() == {
            "status", "source", "sow", "doc_type", "recorded_outcome",
            "check_required", "outcome_known"}

    def test_a_completion_source_is_the_only_route_to_a_recorded_outcome(self):
        """And nothing in this project supplies one, so the chain above can
        never produce `COMPLETED` on its own."""
        idb_resolver = sample_idb_resolver()
        requirement = sample_sow_resolver().resolve("MDS")
        assert idb_resolver.resolve(requirement).status == TO_BE_CHECK
        assert idb_resolver.resolve(requirement, COMPLETED).status == COMPLETED


class TestArchitectureBoundary:
    """Gate F: the Phase 2C engine is pure business logic."""

    @pytest.mark.parametrize("path", IDB_MODULES, ids=lambda p: p.name)
    def test_no_infrastructure_import_appears_in_the_source(self, path):
        forbidden = {"fastapi", "openpyxl", "uvicorn", "pydantic", "starlette",
                     "requests", "sqlalchemy"}
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imported.add(node.module.split(".")[0])
        assert not imported & forbidden, imported & forbidden

    @pytest.mark.parametrize("path", IDB_MODULES, ids=lambda p: p.name)
    def test_no_module_reaches_into_infrastructure_or_the_api(self, path):
        """Relative imports must stay inside domain and engine."""
        source = path.read_text(encoding="utf-8")
        for forbidden in ("infrastructure", "app.api", "services", "excel"):
            assert f"import {forbidden}" not in source
            assert f"from {forbidden}" not in source

    def test_importing_the_engine_pulls_in_no_excel_or_web_framework(self):
        """Checked in a fresh interpreter, so an import another suite already
        performed cannot mask a dependency."""
        code = (
            "import sys; import app.engine.idb; "
            "print(sorted(m for m in ('fastapi', 'openpyxl', 'uvicorn', "
            "'starlette') if m in sys.modules))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            cwd=str(APP.parent), check=True)
        assert out.stdout.strip() == "[]", out.stdout

    def test_the_engine_does_not_know_where_the_workbook_lives(self):
        """No path, no configuration, no filesystem."""
        for path in IDB_MODULES:
            source = path.read_text(encoding="utf-8")
            assert "pathlib" not in source
            assert "core.config" not in source
            assert "settings" not in source
