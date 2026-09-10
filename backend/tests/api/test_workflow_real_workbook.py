"""The real MDR workbook through the real HTTP workflow into PostgreSQL.

`test_workflow_api.py` proves the workflow on nine rows. This proves it on the
~22k-row workbook Delivery Phase 1 was verified against: uploaded over HTTP,
extracted, automated, downloaded, and the database compared with what
`run_automation` says about the same file. It is the slowest test module in
the repository and runs the engine three times (extract, automate, oracle)
and the Phase 1 writer once (download); it skips when the workbook or the
rules workbook is not present, and it never writes to either.

The download stage (Delivery Phase 4) pins the Phase 1 counts as literals -
see `EXPECTED_COUNTS`. They are the numbers the CLI's `--excel` produced for
this workbook and must not be edited to make the test pass; a difference is
something to investigate.
"""

from __future__ import annotations

import hashlib
from urllib.parse import unquote

import pytest
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from app.domain.enums.lifecycle import SubmissionStatus
from app.domain.models.automation import (
    AUTOMATION_COLUMNS, CHECK_STATUS, DOC_IDB_COMPLETED_STATUS,
    DOC_IS_REQUIRED_SOW, DOC_TYPE, DOC_WITH_REV,
)
from app.infrastructure.excel.output_workbook import (
    AUTOMATED_SHEET, read_automation_columns,
)
from app.services.automation_service import run_automation
from app.services.export_service import AUTOMATED_WORKBOOK_SUFFIX
from app.services.rule_set_service import file_digest
from tests.support.workbook import (
    PHASE1_WORKBOOK, RULES_WORKBOOK, requires_rules_workbook,
    requires_workbook,
)

from .conftest import stored_rows, stored_submission, upload

pytestmark = [requires_workbook, requires_rules_workbook]

#: Delivery Phase 1's verified output for this workbook: how many rows carry a
#: value in each automation column of `QatarEnergy-TN Automated`, and how
#: many automation rows there are. Literals on purpose.
EXPECTED_ROWS = 21_718
EXPECTED_COUNTS = {
    DOC_WITH_REV: 21_718,
    DOC_TYPE: 16_369,
    DOC_IS_REQUIRED_SOW: 14_988,
    DOC_IDB_COMPLETED_STATUS: 13_230,
    CHECK_STATUS: 0,
}


@pytest.fixture(scope="module")
def oracle():
    """One run of the existing engine over the real workbook."""
    return run_automation(PHASE1_WORKBOOK)


@pytest.fixture(scope="module")
def processed(workflow_settings):
    """upload -> extract -> automate, once for the module; hands back the
    three response bodies, the plant and the source digest taken before."""
    import uuid

    from fastapi.testclient import TestClient

    from app.api.deps import get_settings
    from app.infrastructure.persistence.database import session_scope
    from app.infrastructure.persistence.repositories import PlantRepository
    from app.main import app

    with session_scope(workflow_settings) as session:
        plant = PlantRepository(session).add(
            code=f"REAL-{uuid.uuid4().hex[:8]}", name="QatarEnergy TN")

    before = file_digest(PHASE1_WORKBOOK)
    mtime = PHASE1_WORKBOOK.stat().st_mtime_ns
    app.dependency_overrides[get_settings] = lambda: workflow_settings
    try:
        client = TestClient(app, raise_server_exceptions=False)
        up = upload(client, plant, PHASE1_WORKBOOK)
        assert up.status_code == 201, up.text
        mdr_id = up.json()["mdr_id"]
        ex = client.post(f"/api/v1/mdr/{mdr_id}/extract")
        assert ex.status_code == 200, ex.text
        au = client.post(f"/api/v1/mdr/{mdr_id}/automate")
        assert au.status_code == 200, au.text
        su = client.get(f"/api/v1/mdr/{mdr_id}/summary")
        assert su.status_code == 200, su.text
    finally:
        app.dependency_overrides.pop(get_settings, None)
    return {"upload": up.json(), "extract": ex.json(), "automate": au.json(),
            "summary": su.json(), "plant": plant, "digest_before": before,
            "mtime_before": mtime}


class TestTheSourceIsUntouched:

    def test_the_source_digest_is_unchanged(self, processed):
        assert file_digest(PHASE1_WORKBOOK) == processed["digest_before"]

    def test_the_source_file_was_not_rewritten(self, processed):
        assert PHASE1_WORKBOOK.stat().st_mtime_ns == processed["mtime_before"]

    def test_the_upload_digest_is_the_source_digest(self, processed):
        assert processed["upload"]["source_sha256"] == processed["digest_before"]
        assert processed["upload"]["source_byte_size"] == PHASE1_WORKBOOK.stat().st_size

    def test_the_stored_copy_is_byte_identical(self, processed,
                                               workflow_settings):
        stored = stored_submission(workflow_settings, processed["upload"]["mdr_id"])
        copy = workflow_settings.uploads_dir / stored.stored_path
        assert copy != PHASE1_WORKBOOK
        assert hashlib.sha256(copy.read_bytes()).hexdigest() == processed[
            "digest_before"]


class TestExtraction:

    def test_the_discovery_matches_the_engine(self, processed, oracle):
        discovery = oracle.result.discovery
        assert processed["extract"]["source_sheet_name"] == discovery["qe_sheet"]
        assert processed["extract"]["source_header_row"] == discovery["qe_header_row"]
        assert processed["extract"]["source_row_count"] == discovery["qe_data_rows"]

    def test_every_document_row_is_stored_once_by_source_row(
            self, processed, oracle, workflow_settings):
        rows = stored_rows(workflow_settings, processed["upload"]["mdr_id"])
        assert len(rows) == len(oracle.result.documents)
        assert sorted(r.source_row for r in rows) == sorted(
            d.source_row for d in oracle.result.documents)


class TestAutomation:

    def test_the_row_count_is_the_engines(self, processed, oracle):
        assert processed["automate"]["row_count"] == len(oracle.rows)
        assert processed["automate"]["status"] == SubmissionStatus.AUTOMATED

    def test_every_stored_verdict_matches_the_engine(self, processed, oracle,
                                                     workflow_settings):
        """All ~22k rows, all four columns and the three provenance fields."""
        stored = {r.source_row: r for r in
                  stored_rows(workflow_settings, processed["upload"]["mdr_id"])}
        assert len(stored) == len(oracle.rows)
        mismatches = [
            row.source_row for row in oracle.rows
            if (stored[row.source_row].doc_with_rev, stored[row.source_row].doc_type,
                stored[row.source_row].sow,
                stored[row.source_row].idb_completed_status,
                stored[row.source_row].doc_type_rule,
                stored[row.source_row].sow_source,
                stored[row.source_row].idb_source)
            != (row.doc_with_rev, row.doc_type, row.sow, row.idb_status,
                row.doc_type_rule, row.sow_source, row.idb_source)
        ]
        assert mismatches == []

    def test_check_status_is_blank_on_every_row(self, processed,
                                                workflow_settings):
        rows = stored_rows(workflow_settings, processed["upload"]["mdr_id"])
        assert {r.check_status for r in rows} == {""}

    def test_the_rule_set_is_the_real_rules_workbook(self, processed):
        rule_set = processed["automate"]["rule_set"]
        assert rule_set["content_sha256"] == file_digest(RULES_WORKBOOK)
        assert rule_set["source_filename"] == RULES_WORKBOOK.name


class TestSummary:

    def test_the_summary_is_the_engines_summary(self, processed, oracle):
        body = processed["summary"]
        expected = oracle.summary()
        for key in ("doc_with_rev_populated", "doc_type_populated",
                    "sow_populated", "sow_unresolved", "idb_populated",
                    "idb_unmapped", "idb_manual_check_required"):
            assert body[key] == expected[key], key
        assert body["row_count"] == expected["rows"]
        assert body["check_status_populated"] == 0
        assert body["counts"]["doc_type_counts"] == expected["doc_type_counts"]
        assert body["counts"]["sow_counts"] == expected["sow_counts"]
        assert body["counts"]["idb_counts"] == expected["idb_counts"]

    def test_the_summary_names_plant_status_and_rules(self, processed):
        body = processed["summary"]
        assert body["plant_code"] == processed["plant"].code
        assert body["status"] == SubmissionStatus.AUTOMATED
        assert body["rule_set"] == processed["automate"]["rule_set"]
        assert body["failure_reason"] == ""


# ================================================================ DOWNLOAD
# Delivery Phase 4: the same submission, downloaded, and the file inspected.

@pytest.fixture(scope="module")
def downloaded(processed, workflow_settings, tmp_path_factory):
    """One download of the processed submission, saved to disk. Also records
    the stored upload's digest and mtime before, and the engine being
    forbidden during: the download must be served from the database."""
    from fastapi.testclient import TestClient

    from app.api.deps import get_settings
    from app.main import app
    from app.services import workflow_service

    mdr_id = processed["upload"]["mdr_id"]
    stored = stored_submission(workflow_settings, mdr_id)
    upload_path = workflow_settings.uploads_dir / stored.stored_path
    upload_before = (file_digest(upload_path), upload_path.stat().st_mtime_ns)

    def forbidden(*args, **kwargs):
        raise AssertionError("download must not run the engine")

    patch = pytest.MonkeyPatch()
    patch.setattr(workflow_service, "run_automation", forbidden)
    patch.setattr(workflow_service, "MdrEngine", forbidden)
    app.dependency_overrides[get_settings] = lambda: workflow_settings
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/api/v1/mdr/{mdr_id}/download")
    finally:
        app.dependency_overrides.pop(get_settings, None)
        patch.undo()
    assert response.status_code == 200, response.text

    path = tmp_path_factory.mktemp("real-download") / "downloaded.xlsx"
    path.write_bytes(response.content)
    return {"response": response, "path": path, "mdr_id": mdr_id,
            "upload_path": upload_path, "upload_before": upload_before,
            "submission_before": stored}


@pytest.fixture(scope="module")
def downloaded_columns(downloaded):
    """The five columns read back out of the downloaded file."""
    return read_automation_columns(downloaded["path"])


class TestDownload:

    def test_it_answers_with_an_xlsx_attachment(self, downloaded):
        response = downloaded["response"]
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment;")
        # Either RFC 6266 form decodes to the upload's stem plus the suffix.
        value = disposition.split("filename", 1)[1]
        name = (unquote(value.split("''", 1)[1]) if value.startswith("*=")
                else value.split('"')[1])
        assert name == PHASE1_WORKBOOK.stem + AUTOMATED_WORKBOOK_SUFFIX
        assert str(downloaded["upload_path"].parent) not in disposition

    def test_every_original_sheet_survives_in_order(self, downloaded):
        wb = load_workbook(PHASE1_WORKBOOK, read_only=True)
        try:
            before = list(wb.sheetnames)
        finally:
            wb.close()
        wb = load_workbook(downloaded["path"], read_only=True)
        try:
            after = list(wb.sheetnames)
        finally:
            wb.close()
        assert after[:-1] == before
        assert after[-1] == AUTOMATED_SHEET
        assert after.count(AUTOMATED_SHEET) == 1

    def test_the_source_sheet_is_unchanged(self, downloaded, processed):
        """The title band, the header row and the first data rows of
        `QatarEnergy-TN`, cell for cell, against the file that was uploaded:
        every value the source has, the download has, unchanged.

        Not `data_only`: a formula cell is compared as its formula. openpyxl
        does not carry a formula's *cached* value through a save - Excel
        recalculates it on opening - and that is the documented behaviour of
        the Phase 1 writer, not a change to the sheet's content.

        One openpyxl round-trip quirk is tolerated and named: a cell that
        holds a hyperlink but no display text (AG4, the `184-Vendors` folder
        link) comes back showing its target. The CLI's own `--excel` output
        has the same cell; nothing else may differ."""
        header_row = processed["extract"]["source_header_row"]
        sheet = processed["extract"]["source_sheet_name"]

        def head(path):
            wb = load_workbook(path, read_only=True)
            try:
                return [list(r) for r in wb[sheet].iter_rows(
                    min_row=1, max_row=header_row + 200, values_only=True)]
            finally:
                wb.close()

        before, after = head(PHASE1_WORKBOOK), head(downloaded["path"])
        assert len(after) == len(before)
        gained = []
        for n, (src, out) in enumerate(zip(before, after), start=1):
            assert len(src) == len(out), n
            for col, (x, y) in enumerate(zip(src, out), start=1):
                if x == y:
                    continue
                # A value the source has must come back exactly.
                assert x is None, (n, col, x, y)
                gained.append((n, col, y))
        # Only hyperlink targets may appear where the source showed nothing.
        assert all(isinstance(v, str) and v.startswith(("file:", "http", "mailto:"))
                   for _, _, v in gained), gained
        assert len(gained) <= 1, gained
        # And there is a formula in the band, kept as a formula.
        assert any(isinstance(v, str) and v.startswith("=")
                   for row in after[:header_row] for v in row)

    def test_the_automation_row_count_is_phase_1s(self, downloaded_columns):
        _, _, rows = downloaded_columns
        assert len(rows) == EXPECTED_ROWS

    @pytest.mark.parametrize("caption", AUTOMATION_COLUMNS)
    def test_the_populated_count_is_phase_1s(self, downloaded_columns, caption):
        _, _, rows = downloaded_columns
        assert sum(1 for r in rows if r[caption]) == EXPECTED_COUNTS[caption], \
            caption

    def test_the_persisted_summary_agrees_with_the_file(self, downloaded_columns,
                                                        processed):
        """The counts the API reported for the submission are the counts of
        the file it hands out."""
        _, _, rows = downloaded_columns
        body = processed["summary"]
        assert body["row_count"] == len(rows) == EXPECTED_ROWS
        assert body["doc_with_rev_populated"] == EXPECTED_COUNTS[DOC_WITH_REV]
        assert body["doc_type_populated"] == EXPECTED_COUNTS[DOC_TYPE]
        assert body["sow_populated"] == EXPECTED_COUNTS[DOC_IS_REQUIRED_SOW]
        assert body["idb_populated"] == EXPECTED_COUNTS[DOC_IDB_COMPLETED_STATUS]
        assert body["check_status_populated"] == 0

    def test_every_cell_is_the_persisted_value_by_source_row(
            self, downloaded_columns, workflow_settings, downloaded):
        """All ~22k rows, the four columns, against `mdr_document_rows`."""
        _, _, rows = downloaded_columns
        stored = {r.source_row: r for r in
                  stored_rows(workflow_settings, downloaded["mdr_id"])}
        assert {r["source_row"] for r in rows} == set(stored)
        mismatches = [
            r["source_row"] for r in rows
            if (r[DOC_WITH_REV], r[DOC_TYPE], r[DOC_IS_REQUIRED_SOW],
                r[DOC_IDB_COMPLETED_STATUS])
            != (stored[r["source_row"]].doc_with_rev.upper(),
                stored[r["source_row"]].doc_type.upper(),
                stored[r["source_row"]].sow.upper(),
                stored[r["source_row"]].idb_completed_status.upper())
        ]
        assert mismatches == []

    def test_the_file_matches_the_engine_too(self, downloaded_columns, oracle):
        """Transitively true given the tests above, stated directly: what is
        downloaded is what `run_automation` says about the workbook."""
        _, _, rows = downloaded_columns
        expected = {r.source_row: r for r in oracle.rows}
        assert {r["source_row"] for r in rows} == set(expected)
        mismatches = [
            r["source_row"] for r in rows
            if (r[DOC_WITH_REV], r[DOC_TYPE], r[DOC_IS_REQUIRED_SOW],
                r[DOC_IDB_COMPLETED_STATUS])
            != (expected[r["source_row"]].doc_with_rev,
                expected[r["source_row"]].doc_type,
                expected[r["source_row"]].sow,
                expected[r["source_row"]].idb_status)
        ]
        assert mismatches == []

    def test_skipped_source_rows_carry_nothing(self, downloaded, processed,
                                               downloaded_columns):
        """Rows of the sheet with no persisted counterpart - spacers, rows
        without a DOCUMENT NO. - have five empty automation cells."""
        header_row, letters, rows = downloaded_columns
        populated = {r["source_row"] for r in rows}
        wb = load_workbook(downloaded["path"], read_only=True, data_only=True)
        try:
            ws = wb[AUTOMATED_SHEET]
            seen_populated = skipped = 0
            for n, row in enumerate(ws.iter_rows(
                    min_row=header_row + 1,
                    min_col=column_index_from_string(letters[DOC_WITH_REV]),
                    max_col=column_index_from_string(letters[CHECK_STATUS]),
                    values_only=True), start=header_row + 1):
                if n in populated:
                    seen_populated += 1
                else:
                    skipped += 1
                    assert set(row) <= {None}, n
        finally:
            wb.close()
        assert seen_populated == EXPECTED_ROWS
        # The sheet has more rows than documents; the rest carry nothing.
        assert skipped > 0

    def test_check_status_is_blank(self, downloaded_columns):
        _, letters, rows = downloaded_columns
        assert CHECK_STATUS in letters
        assert {r[CHECK_STATUS] for r in rows} == {""}

    def test_the_columns_sit_where_the_working_sheet_puts_them(
            self, downloaded_columns):
        _, letters, _ = downloaded_columns
        assert [letters[c] for c in AUTOMATION_COLUMNS] == \
            ["AK", "AL", "AM", "AN", "AO"]

    def test_the_stored_upload_and_the_source_are_untouched(self, downloaded,
                                                            processed):
        assert (file_digest(downloaded["upload_path"]),
                downloaded["upload_path"].stat().st_mtime_ns) == \
            downloaded["upload_before"]
        assert file_digest(PHASE1_WORKBOOK) == processed["digest_before"]
        assert PHASE1_WORKBOOK.stat().st_mtime_ns == processed["mtime_before"]

    def test_the_submission_is_unchanged(self, downloaded, processed,
                                         workflow_settings):
        before = downloaded["submission_before"]
        after = stored_submission(workflow_settings, downloaded["mdr_id"])
        assert after.status == before.status == SubmissionStatus.AUTOMATED
        assert after.automated_at == before.automated_at
        assert after.updated_at == before.updated_at
        assert after.failure_reason == ""
        assert processed["summary"]["status"] == SubmissionStatus.AUTOMATED
