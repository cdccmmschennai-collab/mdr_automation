"""Writing result artefacts to disk.

Serialisation mechanics only: which artefacts get written, and where, is the
export service's decision. Nothing here knows what an MDR document is beyond
"a dataclass whose private fields are not published".
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Hex SHA-256 of a file, read in chunks so a large workbook is not
    loaded whole.

    Used to prove that a source workbook came out of a run byte-for-byte
    identical to how it went in.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def public_fields(record) -> dict:
    """Dataclass fields minus the private ones the pipeline attaches.

    `DocumentRecord` carries a private `_eligible` attribute between assembly
    and ranking; it is internal state and is never published.
    """
    return {k: v for k, v in asdict(record).items() if not k.startswith("_")}


def write_json(payload: dict, path: Path) -> None:
    """Write a JSON artefact, creating the directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def write_csv(rows: Iterable, path: Path) -> None:
    """Write dataclass rows as CSV. An empty sequence writes an empty file.

    UTF-8 with BOM, because these files are opened in Excel.
    """
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = [k for k in public_fields(rows[0])]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            d = public_fields(r)
            writer.writerow({k: ("|".join(v) if isinstance(v, list) else v)
                             for k, v in d.items()})
