"""The two Delivery Phase 3 settings, and the upload-time workbook probe."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.core.config import DEFAULT_MAX_UPLOAD_BYTES, load_settings
from app.infrastructure.excel.mdr_workbook import probe_document_sheet
from app.infrastructure.excel.workbook_reader import (
    SheetNotFoundError, WorkbookUnreadableError,
)
from tests.support.automation import build_source_workbook


class TestSettings:

    def test_uploads_default_under_the_data_dir(self, monkeypatch):
        monkeypatch.delenv("MDR_UPLOADS_DIR", raising=False)
        monkeypatch.setenv("MDR_DATA_DIR", "/srv/mdr/data")
        settings = load_settings()
        assert settings.uploads_dir == Path("/srv/mdr/data/uploads")
        assert settings.uploads_dir_override is None

    def test_uploads_dir_can_be_overridden(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MDR_UPLOADS_DIR", str(tmp_path))
        assert load_settings().uploads_dir == tmp_path

    def test_the_upload_limit_defaults_to_100_mib(self, monkeypatch):
        monkeypatch.delenv("MDR_MAX_UPLOAD_BYTES", raising=False)
        assert load_settings().max_upload_bytes == DEFAULT_MAX_UPLOAD_BYTES
        assert DEFAULT_MAX_UPLOAD_BYTES == 100 * 1024 * 1024

    def test_the_upload_limit_is_configurable(self, monkeypatch):
        monkeypatch.setenv("MDR_MAX_UPLOAD_BYTES", "2048")
        assert load_settings().max_upload_bytes == 2048

    def test_a_non_integer_limit_is_a_configuration_error(self, monkeypatch):
        monkeypatch.setenv("MDR_MAX_UPLOAD_BYTES", "lots")
        with pytest.raises(ValueError, match="MDR_MAX_UPLOAD_BYTES"):
            load_settings()


class TestProbe:

    def test_an_mdr_workbook_is_recognised_from_bytes(self, tmp_path):
        path = build_source_workbook(tmp_path / "small.xlsx")
        sheet, header_row = probe_document_sheet(io.BytesIO(path.read_bytes()))
        assert sheet == "QatarEnergy-TN"
        assert header_row == 5

    def test_and_from_a_path(self, tmp_path):
        path = build_source_workbook(tmp_path / "small.xlsx")
        assert probe_document_sheet(path) == ("QatarEnergy-TN", 5)

    def test_garbage_is_unreadable(self):
        with pytest.raises(WorkbookUnreadableError):
            probe_document_sheet(io.BytesIO(b"definitely not a zip"))

    def test_a_workbook_without_the_sheet_is_not_an_mdr(self):
        wb = Workbook()
        wb.active["A1"] = "x"
        buffer = io.BytesIO()
        wb.save(buffer)
        with pytest.raises(SheetNotFoundError):
            probe_document_sheet(io.BytesIO(buffer.getvalue()))
