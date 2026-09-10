"""Local-filesystem storage for uploaded MDR workbooks (Delivery Phase 3).

The API receives a workbook as bytes and later phases need those bytes back
by `mdr_id` - extraction reads them, and download will serve them. This module
is the one place that knows where they go.

**What is stored where.** Every upload is written under one root
(`settings.uploads_dir`, `/data/uploads` in the compose stack) in a directory
named after the submission:

    <root>/<submission_id>/<original filename>

The database keeps the *key* - `<submission_id>/<filename>` - in
`mdr_submissions.stored_path`, never an absolute path. The root is
configuration; a key that carried it would break the moment the data directory
moved, and would leak the server's layout into the database.

**Never overwrites.** `put` opens the destination with `xb`, so a second write
to the same key fails instead of quietly replacing a workbook that a
submission already points at. Two submissions never share a key because the
key carries the submission id.

**Never the source directory.** `data/input/` and the other engine inputs are
mounted read-only in the compose stack and are not under this root. An upload
cannot land on, or beside, a source workbook.

Kept deliberately small: a `put`, a `resolve`, an `exists` and a `delete`.
That is the surface an object store offers too, which is what makes this
adapter replaceable by one later - the services call these four names and
nothing else.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path, PurePosixPath
from typing import Protocol

from ...core.config import Settings, settings as default_settings

#: A stored filename may carry letters, digits, space, dot, dash, underscore,
#: parentheses and the `&` and `#` an MDR filename sometimes has. Anything else
#: - path separators above all - is replaced, so a filename can never escape
#: its submission directory.
_UNSAFE = re.compile(r"[^A-Za-z0-9 ._()&#\-]")

#: What a stored file is called when the upload had no usable name at all.
_FALLBACK_FILENAME = "mdr-upload.xlsx"


class StorageKeyError(ValueError):
    """A key that does not name a file under the storage root."""


class WorkbookStorage(Protocol):
    """What the workflow services need from a store. See the module docstring."""

    def put(self, data: bytes, *, submission_id: uuid.UUID,
            filename: str) -> str: ...

    def resolve(self, key: str) -> Path: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


def safe_filename(filename: str) -> str:
    """The name a stored workbook is given, derived from the uploaded one.

    Only the final path component is kept - a browser or a client library may
    send a full path - and characters outside a conservative set are replaced
    with `_`. The extension is preserved so the file remains recognisable as
    a workbook.
    """
    name = PurePosixPath(filename.replace("\\", "/")).name.strip()
    name = _UNSAFE.sub("_", name).strip(" .")
    return name or _FALLBACK_FILENAME


class LocalWorkbookStorage:
    """Uploaded workbooks on the local filesystem, under one root."""

    def __init__(self, root: Path):
        self.root = Path(root)

    @classmethod
    def from_settings(cls, settings: Settings = default_settings
                      ) -> "LocalWorkbookStorage":
        return cls(settings.uploads_dir)

    # ---------------------------------------------------------------- write

    def put(self, data: bytes, *, submission_id: uuid.UUID,
            filename: str) -> str:
        """Store `data` for one submission and return its key.

        Raises FileExistsError rather than overwriting: see the module
        docstring. The submission directory is created on demand.
        """
        key = f"{submission_id}/{safe_filename(filename)}"
        path = self.resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "xb") as handle:
            handle.write(data)
        return key

    def delete(self, key: str) -> None:
        """Remove one stored workbook, and its directory if that leaves it
        empty. Missing files are not an error: the point is that the key is
        gone afterwards."""
        path = self.resolve(key)
        if path.is_file():
            path.unlink()
        parent = path.parent
        if parent != self.root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()

    # ----------------------------------------------------------------- read

    def resolve(self, key: str) -> Path:
        """The filesystem path for a key.

        Refuses anything that would resolve outside the root - an absolute
        key, or one carrying `..` - so a corrupted or hand-edited
        `stored_path` cannot make the backend read an arbitrary file. A
        backslash is treated as a separator whatever the host OS, so a key is
        judged the same way on Windows and in the Linux container.
        """
        normalised = key.replace("\\", "/")
        parts = PurePosixPath(normalised).parts
        if not normalised or normalised.startswith("/") or ".." in parts:
            raise StorageKeyError(f"invalid storage key {key!r}")
        candidate = (self.root / PurePosixPath(normalised)).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise StorageKeyError(f"invalid storage key {key!r}")
        return candidate

    def exists(self, key: str) -> bool:
        try:
            return self.resolve(key).is_file()
        except StorageKeyError:
            return False
