"""The five-column row model, and the one column it refuses to carry.

`AutomationRow` is where Phase 2D's hard requirement lives: CHECK STATUS is
not evaluated until the received-document dump exists, so the model rejects
any attempt to give it a value. These tests are the guard on that rule - if a
later phase starts filling the column, it has to delete a test that says why
it must not.
"""

import dataclasses

import pytest

from app.domain.models.automation import (
    AUTOMATION_COLUMNS, CHECK_STATUS, CHECK_STATUS_NOT_EVALUATED,
    AutomationRow, CheckStatusNotEvaluated,
)


class TestTheFiveColumns:
    def test_the_captions_are_the_working_files_own_spelling(self):
        assert AUTOMATION_COLUMNS == (
            "DOC WITH REV", "DOC TYPE", "DOC IS REQUIRED SOW",
            "DOC IDB COMPLETED STATUS", "CHECK STATUS")

    def test_values_are_in_caption_order(self):
        row = AutomationRow(source_row=6, doc_with_rev="DOC-0",
                            doc_type="MDS", sow="YES-MTL/DOC IDB",
                            idb_status="TO BE CHECK")
        assert row.values == ("DOC-0", "MDS", "YES-MTL/DOC IDB",
                              "TO BE CHECK", "")
        assert len(row.values) == len(AUTOMATION_COLUMNS)

    def test_a_row_is_immutable(self):
        row = AutomationRow(source_row=6)
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.idb_status = "COMPLETED"

    def test_provenance_is_carried_but_is_not_a_column(self):
        row = AutomationRow(source_row=6, doc_type_rule="REQUIRED#51 'P&ID'",
                            sow_source="DOCUMENT_TYPE_TABLE",
                            idb_source="NO_COMPLETION_SOURCE")
        assert row.doc_type_rule and row.sow_source and row.idb_source
        assert len(row.values) == 5


class TestCheckStatusIsStructurallyBlank:
    """There is no received-document dump, so there is no CHECK STATUS."""

    def test_it_defaults_to_blank(self):
        assert CHECK_STATUS_NOT_EVALUATED == ""
        assert AutomationRow(source_row=6).check_status == ""

    @pytest.mark.parametrize("value", [
        "RECEIVED", "NOT RECEIVED", "#N/A", "N/A", "-", " ", "0",
    ])
    def test_no_value_may_be_put_in_it(self, value):
        """`NOT RECEIVED` in particular: the absence of a dump is not
        evidence that a document was not received."""
        with pytest.raises(CheckStatusNotEvaluated):
            AutomationRow(source_row=6, check_status=value)

    def test_the_refusal_names_the_row(self):
        with pytest.raises(CheckStatusNotEvaluated, match="4321"):
            AutomationRow(source_row=4321, check_status="NOT RECEIVED")

    def test_it_is_still_one_of_the_five_columns(self):
        """Blank, but present: the employee sees the column exists and is
        waiting on Phase 3."""
        assert CHECK_STATUS in AUTOMATION_COLUMNS
        assert AUTOMATION_COLUMNS[-1] == CHECK_STATUS


class TestSerialisation:
    def test_to_dict_publishes_the_values_and_their_provenance(self):
        row = AutomationRow(source_row=6, doc_with_rev="DOC-0", doc_type="MDS",
                            sow="YES-MTL/DOC IDB", idb_status="TO BE CHECK",
                            idb_source="NO_COMPLETION_SOURCE")
        assert row.to_dict() == {
            "source_row": 6, "doc_with_rev": "DOC-0", "doc_type": "MDS",
            "sow": "YES-MTL/DOC IDB", "idb_status": "TO BE CHECK",
            "check_status": "", "doc_type_rule": "", "sow_source": "",
            "idb_source": "NO_COMPLETION_SOURCE",
        }

    def test_the_model_carries_no_excel_coordinate_but_the_row_number(self):
        fields = {f.name for f in dataclasses.fields(AutomationRow)}
        assert "source_row" in fields
        assert not {"column", "sheet", "cell", "workbook"} & fields
