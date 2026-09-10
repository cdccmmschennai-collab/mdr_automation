"""Storage adapters for uploaded and generated files.

Delivery Phase 3 adds `local`: uploaded MDR workbooks on the local filesystem
under `settings.uploads_dir`, keyed by submission. It is the only adapter; an
object store would be a second module here exposing the same four calls
(`put`, `resolve`, `exists`, `delete`) - see `local.WorkbookStorage`.
"""

from .local import (
    LocalWorkbookStorage, StorageKeyError, WorkbookStorage, safe_filename,
)

__all__ = [
    "LocalWorkbookStorage",
    "StorageKeyError",
    "WorkbookStorage",
    "safe_filename",
]
