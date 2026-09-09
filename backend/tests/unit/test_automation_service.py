"""Phase 2D assembly: four engines in, one five-column row out.

The service is wiring, so this suite tests the wiring: that each stage is fed
exactly the previous stage's verdict, that an unknown stays an unknown, and
that no completion source and no historical column can reach the IDB
resolver - which is the only way `COMPLETED` could appear in an output the
project has no evidence for.

The SOW verdicts come from the real `DOCUMENT TYPE` sheet fixture, so no test
invents a scope verdict the rules workbook does not state.
"""

import ast
import inspect

import pytest

from app.domain.models.automation import AutomationRow
from app.domain.models.document import DocumentRecord
from app.domain.models.idb import (
    CANCELLED, COMPLETED, COMPLETED_REV_UPDATED, GENERAL_SPECIFICATION,
    NO_NEED_TO_CHECK, PENDING, REFERENCE, TAG_NOT_IN_FMTL, TO_BE_CHECK,
    UNMAPPED,
)
from app.services import automation_service
from app.services.automation_service import AutomationRun, build_automation_rows
from tests.support.idb import sample_idb_resolver
from tests.support.sow import sample_sow_resolver

#: Values that only ever appear in the historical `DOC IDB COMPLETED STATUS`
#: column, because each needs an input this project does not read - the IDB
#: folder, the FMTL, or a human judgement. None may appear in an output.
HISTORICAL_ONLY = (COMPLETED, COMPLETED_REV_UPDATED, PENDING, CANCELLED,
                   TAG_NOT_IN_FMTL, REFERENCE, GENERAL_SPECIFICATION)


def code_literals(module) -> set[str]:
    """Every string literal in a module that is not a docstring.

    The docstrings of `automation_service` name the historical statuses in
    order to say they are not consulted; the code must not name them at all,
    and this separates the two.
    """
    tree = ast.parse(inspect.getsource(module))
    docstrings = {
        ast.get_docstring(n, clean=False)
        for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                          ast.AsyncFunctionDef))
    }
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docstrings}


def imported_modules(module) -> set[str]:
    """Every module name `module` imports, absolute and relative alike."""
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def doc(row: int, number: str = "4391-MEWTP-2-13-0005", rev: str = "0",
        doc_type: str = "MDS", doc_type_source: str = "") -> DocumentRecord:
    """A Phase 1 + 2A record, as `MdrEngine._build_documents` leaves it.

    `doc_type_source` is the keyword sheet Phase 2A matched on - `REQUIRED`
    or `NOT_REQUIRED` - which Phase 2B reads as a scope statement.
    """
    return DocumentRecord(source_row=row, document_identity=number,
                          qatarenergy_document_no=number, revision=rev,
                          revision_raw=rev, doc_type=doc_type,
                          doc_type_source=doc_type_source)


@pytest.fixture
def resolvers():
    return sample_sow_resolver(), sample_idb_resolver()


class TestTheChain:
    def test_an_in_scope_document_carries_its_values_and_a_blank_idb(self,
                                                                     resolvers):
        """Four columns answered, and DOC IDB COMPLETED STATUS deliberately
        blank: the document *is* required, so somebody has to go and check
        whether its IDB is complete. Nothing here can know that."""
        rows = build_automation_rows([doc(6)], *resolvers)
        assert rows == [AutomationRow(
            source_row=6, doc_with_rev="4391-MEWTP-2-13-0005-0",
            doc_type="MDS", sow="YES-MTL/DOC IDB", idb_status="",
            sow_source="DOCUMENT_TYPE_TABLE",
            idb_source="NO_COMPLETION_SOURCE")]

    def test_the_blank_idb_is_distinguishable_from_an_unresolved_one(self,
                                                                     resolvers):
        """Both cells are empty on the sheet, but the provenance separates
        'required, go and look' from 'no rule covers this'."""
        required, unknown = build_automation_rows(
            [doc(6), doc(7, doc_type="NOT A DOCUMENT TYPE")], *resolvers)
        assert required.idb_status == ""
        assert required.idb_source == "NO_COMPLETION_SOURCE"
        assert unknown.idb_status == UNMAPPED
        assert unknown.idb_source == "UNRESOLVED_SOW"

    def test_phase_2c_still_states_that_a_check_is_due(self, resolvers):
        """The blank is Phase 2D's presentation of Phase 2C's verdict, not a
        loss of it: the resolver itself still answers `TO BE CHECK`."""
        sow_resolver, idb_resolver = resolvers
        status = idb_resolver.resolve(sow_resolver.resolve("MDS"))
        assert status.status == TO_BE_CHECK
        assert status.check_required is True

    def test_an_out_of_scope_document_needs_no_check(self, resolvers):
        """Phase 1's old-revision verdict reaches IDB through the DOC TYPE and
        by no other route."""
        row, = build_automation_rows([doc(6, doc_type="OLD REV NOT SOW")],
                                     *resolvers)
        assert row.sow == "NO"
        assert row.idb_status == NO_NEED_TO_CHECK
        assert row.idb_source == "SOW_NOT_REQUIRED"

    def test_the_row_number_is_the_workbook_row(self, resolvers):
        rows = build_automation_rows([doc(6), doc(9), doc(4102)], *resolvers)
        assert [r.source_row for r in rows] == [6, 9, 4102]

    def test_doc_with_rev_comes_from_phase_1(self, resolvers):
        row, = build_automation_rows(
            [doc(6, "ven-mewtp-5-43-0011", "a")], *resolvers)
        assert row.doc_with_rev == "VEN-MEWTP-5-43-0011-A"

    def test_doc_type_is_carried_verbatim_and_not_reclassified(self, resolvers):
        """The service must not run the keyword rules again; whatever Phase 2A
        put on the record is what reaches the column."""
        row, = build_automation_rows([doc(6, doc_type="MXB")], *resolvers)
        assert row.doc_type == "MXB"
        assert row.sow == "YES-FMTL/MTL/HIERARCHY/DOC IDB"


class TestUnknownsStayUnknown:
    def test_no_doc_type_gives_no_sow_and_no_idb_status(self, resolvers):
        row, = build_automation_rows([doc(6, doc_type="")], *resolvers)
        assert row.doc_type == ""
        assert row.sow == ""
        assert row.idb_status == UNMAPPED
        assert row.idb_source == "UNRESOLVED_SOW"

    def test_a_doc_type_outside_both_sheets_is_reported_not_defaulted(
            self, resolvers):
        """A DOC TYPE neither the `DOCUMENT TYPE` table nor the not-required
        keyword sheet states. Reading that gap as `NO` would tell the employee
        the document is out of scope, which nothing states."""
        row, = build_automation_rows(
            [doc(6, doc_type="SOMETHING NOBODY CLASSIFIED")], *resolvers)
        assert row.sow == ""
        assert row.idb_status == UNMAPPED
        assert row.idb_status != NO_NEED_TO_CHECK

    def test_a_run_without_a_rules_workbook_resolves_nothing(self):
        """`sow_service.build_resolver` returns None when there is no rules
        workbook. That must produce honest unknowns, not a crash and not a
        column of `NO`."""
        rows = build_automation_rows([doc(6), doc(7)], None,
                                     sample_idb_resolver())
        assert [r.sow for r in rows] == ["", ""]
        assert [r.idb_status for r in rows] == [UNMAPPED, UNMAPPED]


class TestTheNotRequiredSheetStatesScope:
    """`NOT REQUIRED-KEY DOC.WORDS` is a classification *and* a scope verdict.

    Its 63 document types appear in none of the 22 `DOCUMENT TYPE` rows, so
    looking for them only in that table is what left thousands of rows
    `UNMAPPED`. Being on the not-required sheet is the statement.
    """

    @pytest.mark.parametrize("doc_type", [
        "CV", "METHOD STATEMENT", "PLAN", "PLOT PLAN", "LAYOUT",
    ])
    def test_a_not_required_document_is_out_of_scope_and_needs_no_check(
            self, resolvers, doc_type):
        row, = build_automation_rows(
            [doc(6, doc_type=doc_type, doc_type_source="NOT_REQUIRED")],
            *resolvers)
        assert row.doc_type == doc_type
        assert row.sow == "NO"
        assert row.sow_source == "NOT_REQUIRED_KEYWORDS"
        assert row.idb_status == NO_NEED_TO_CHECK
        assert row.check_status == ""

    def test_the_document_type_table_still_wins_where_it_speaks(self,
                                                                resolvers):
        """Precedence, stated: a type the rules workbook puts in scope keeps
        its `YES-...` string whatever sheet classified the document."""
        row, = build_automation_rows(
            [doc(6, doc_type="MDS", doc_type_source="NOT_REQUIRED")],
            *resolvers)
        assert row.sow == "YES-MTL/DOC IDB"
        assert row.sow_source == "DOCUMENT_TYPE_TABLE"

    def test_a_required_sheet_classification_is_never_read_as_no(self,
                                                                 resolvers):
        """A DOC TYPE from `REQUIRED-KEY DOC.WORDS` that the `DOCUMENT TYPE`
        table omits stays an honest unknown. The required sheet says what a
        document *is*, not whether it is in scope."""
        row, = build_automation_rows(
            [doc(6, doc_type="MATERIAL SUBMITTAL", doc_type_source="REQUIRED")],
            *resolvers)
        assert row.sow == ""
        assert row.idb_status == UNMAPPED


class TestNoHistoricalValueCanEnter:
    """The historical column is a manual result, not an input."""

    def test_no_document_can_produce_a_historical_only_status(self, resolvers):
        docs = [doc(6, doc_type=t) for t in
                ("MDS", "MXB", "MTC", "CV", "", "OLD REV NOT SOW", "NOT SOW")]
        docs += [doc(7, doc_type="CV", doc_type_source="NOT_REQUIRED")]
        produced = {r.idb_status for r in build_automation_rows(docs, *resolvers)}
        # Three answers and a blank; `TO BE CHECK` never reaches the column.
        assert produced <= {"", NO_NEED_TO_CHECK, UNMAPPED}
        assert not produced & set(HISTORICAL_ONLY)

    def test_the_idb_resolver_is_never_given_a_recorded_outcome(self, resolvers):
        """Spy on the one parameter through which a completion source - or a
        historical `AN` value - could reach the resolver."""
        sow_resolver, idb_resolver = resolvers
        seen = []
        real = idb_resolver.resolve

        def spy(requirement=None, recorded_outcome=""):
            seen.append(recorded_outcome)
            return real(requirement, recorded_outcome)

        idb_resolver.resolve = spy
        build_automation_rows([doc(6), doc(7, doc_type="CV")], sow_resolver,
                              idb_resolver)
        assert seen == ["", ""]

    def test_the_service_takes_no_completion_source_argument(self):
        """There is nowhere to pass one, so no caller can start."""
        params = set(inspect.signature(build_automation_rows).parameters)
        assert params == {"documents", "sow_resolver", "idb_resolver"}

    def test_the_service_imports_no_reference_or_excel_reader(self):
        """The historical workbook cannot be an input to something that never
        opens it, and the service opens nothing at all."""
        imported = imported_modules(automation_service)
        assert not any("reference_workbook" in m or "excel" in m
                       for m in imported), imported


class TestCheckStatus:
    def test_every_row_leaves_it_blank(self, resolvers):
        docs = [doc(r, doc_type=t) for r, t in
                enumerate(("MDS", "CV", "OLD REV NOT SOW", ""), start=6)]
        rows = build_automation_rows(docs, *resolvers)
        assert all(r.check_status == "" for r in rows)

    def test_the_service_code_never_names_a_received_status(self):
        literals = code_literals(automation_service)
        for forbidden in ("RECEIVED", "NOT RECEIVED", "#N/A"):
            assert not any(forbidden in s for s in literals), forbidden


class TestTheRunSummary:
    def test_it_counts_what_each_phase_populated(self, resolvers):
        docs = [doc(6), doc(7, doc_type="UNKNOWN TYPE"),
                doc(8, doc_type="OLD REV NOT SOW")]
        run = AutomationRun(result=None,
                            rows=build_automation_rows(docs, *resolvers))
        summary = run.summary()
        assert summary["rows"] == 3
        assert summary["doc_with_rev_populated"] == 3
        assert summary["doc_type_populated"] == 3
        assert summary["sow_populated"] == 2       # the unknown type resolves
        assert summary["sow_unresolved"] == 1      # to nothing
        assert summary["idb_unmapped"] == 1
        assert summary["check_status_populated"] == 0

    def test_it_counts_the_rows_awaiting_a_manual_idb_check(self, resolvers):
        """The blanks are a decision, so they are counted rather than left to
        look like rows the pipeline missed."""
        docs = [doc(6), doc(7), doc(8, doc_type="OLD REV NOT SOW")]
        run = AutomationRun(result=None,
                            rows=build_automation_rows(docs, *resolvers))
        summary = run.summary()
        assert summary["idb_manual_check_required"] == 2
        assert summary["idb_populated"] == 1

    def test_it_reports_the_idb_distribution(self, resolvers):
        docs = [doc(6), doc(7, doc_type="OLD REV NOT SOW")]
        run = AutomationRun(result=None,
                            rows=build_automation_rows(docs, *resolvers))
        assert run.summary()["idb_counts"] == {"": 1, NO_NEED_TO_CHECK: 1}
