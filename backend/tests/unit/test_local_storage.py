"""`infrastructure.storage.local`: where uploaded workbooks go, and what it
refuses to do. No database, no engine, no HTTP."""

from __future__ import annotations

import uuid

import pytest

from app.infrastructure.storage import (
    LocalWorkbookStorage, StorageKeyError, safe_filename,
)


@pytest.fixture
def storage(tmp_path) -> LocalWorkbookStorage:
    return LocalWorkbookStorage(tmp_path / "uploads")


class TestPut:

    def test_the_key_is_submission_then_filename(self, storage):
        submission_id = uuid.uuid4()
        key = storage.put(b"bytes", submission_id=submission_id,
                          filename="MDR (9).xlsx")
        assert key == f"{submission_id}/MDR (9).xlsx"
        assert storage.resolve(key).read_bytes() == b"bytes"
        assert storage.exists(key)

    def test_the_root_is_created_on_demand(self, tmp_path):
        store = LocalWorkbookStorage(tmp_path / "does" / "not" / "exist")
        key = store.put(b"x", submission_id=uuid.uuid4(), filename="a.xlsx")
        assert store.exists(key)

    def test_a_second_put_to_the_same_key_never_overwrites(self, storage):
        submission_id = uuid.uuid4()
        storage.put(b"first", submission_id=submission_id, filename="a.xlsx")
        with pytest.raises(FileExistsError):
            storage.put(b"second", submission_id=submission_id, filename="a.xlsx")
        assert storage.resolve(f"{submission_id}/a.xlsx").read_bytes() == b"first"

    def test_two_submissions_with_one_filename_do_not_collide(self, storage):
        a = storage.put(b"a", submission_id=uuid.uuid4(), filename="log.xlsx")
        b = storage.put(b"b", submission_id=uuid.uuid4(), filename="log.xlsx")
        assert a != b
        assert storage.resolve(a).read_bytes() == b"a"
        assert storage.resolve(b).read_bytes() == b"b"

    def test_a_filename_with_a_path_in_it_stays_in_its_directory(self, storage):
        submission_id = uuid.uuid4()
        key = storage.put(b"x", submission_id=submission_id,
                          filename="../../etc/passwd.xlsx")
        assert key == f"{submission_id}/passwd.xlsx"
        assert storage.resolve(key).parent.name == str(submission_id)


class TestDelete:

    def test_delete_removes_the_file_and_its_empty_directory(self, storage):
        key = storage.put(b"x", submission_id=uuid.uuid4(), filename="a.xlsx")
        path = storage.resolve(key)
        storage.delete(key)
        assert not path.exists()
        assert not path.parent.exists()
        assert not storage.exists(key)

    def test_deleting_a_missing_key_is_not_an_error(self, storage):
        storage.delete(f"{uuid.uuid4()}/nothing.xlsx")


class TestResolve:

    @pytest.mark.parametrize("key", ["", "/abs/path.xlsx", "..\\up.xlsx",
                                     "a/../../b.xlsx", "../outside.xlsx"])
    def test_keys_that_leave_the_root_are_refused(self, storage, key):
        with pytest.raises(StorageKeyError):
            storage.resolve(key)
        assert storage.exists(key) is False

    def test_a_key_resolves_under_the_root(self, storage):
        path = storage.resolve("abc/def.xlsx")
        assert path == (storage.root / "abc" / "def.xlsx").resolve()


class TestSafeFilename:

    @pytest.mark.parametrize("given,expected", [
        ("20260720-184-Transmittal Log (9) MDR.xlsx",
         "20260720-184-Transmittal Log (9) MDR.xlsx"),
        ("C:\\Users\\me\\Desktop\\log.xlsx", "log.xlsx"),
        ("/tmp/../log.xlsx", "log.xlsx"),
        ("weird:name?.xlsx", "weird_name_.xlsx"),
        ("", "mdr-upload.xlsx"),
        ("...", "mdr-upload.xlsx"),
        ("INPUT-KEYWORDS  FOR MDR TOOL.xlsx", "INPUT-KEYWORDS  FOR MDR TOOL.xlsx"),
    ])
    def test_only_the_final_component_survives_and_is_sanitised(self, given,
                                                                 expected):
        assert safe_filename(given) == expected

    def test_from_settings_uses_the_configured_uploads_dir(self, tmp_path):
        import dataclasses

        from app.core.config import settings

        custom = dataclasses.replace(settings, uploads_dir_override=tmp_path)
        assert LocalWorkbookStorage.from_settings(custom).root == tmp_path
        assert LocalWorkbookStorage.from_settings(settings).root == (
            settings.data_dir / "uploads")
