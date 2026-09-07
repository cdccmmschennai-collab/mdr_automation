#!/usr/bin/env python
"""Inspect an MDR workbook without processing it.

Prints the sheets, their dimensions, and - for the sheets Phase 1 consumes -
the detected header row and column captions. Useful when a new workbook arrives
and you need to know whether the engine will recognise it.

    python scripts/inspect_workbook.py                     # configured workbook
    python scripts/inspect_workbook.py path/to.xlsx

Read-only: opens every workbook with read_only=True and writes nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings                       # noqa: E402
from app.infrastructure.excel.mdr_workbook import (        # noqa: E402
    QE_EXPECTED, QE_SHEET, STATUS_EXPECTED, STATUS_SHEET,
    VENDOR_EXPECTED, VENDOR_SHEET,
)
from app.infrastructure.excel.workbook_reader import (     # noqa: E402
    describe_workbook, read_table,
)

SHEETS = [
    ("QatarEnergy-TN", QE_SHEET, QE_EXPECTED),
    ("TN FROM VENDORS", VENDOR_SHEET, VENDOR_EXPECTED),
    ("Status Codes", STATUS_SHEET, STATUS_EXPECTED),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", nargs="?", type=Path, default=None)
    parser.add_argument("--headers", action="store_true",
                        help="list every detected column caption")
    args = parser.parse_args(argv)

    workbook = args.workbook or settings.default_workbook()
    if workbook is None:
        print(f"no workbook given and none found in {settings.input_current_dir}",
              file=sys.stderr)
        return 2
    if not workbook.is_file():
        print(f"not a file: {workbook}", file=sys.stderr)
        return 2

    info = describe_workbook(workbook)
    print(f"{workbook}\n")
    print(f"{'sheet':<34} {'state':<10} {'rows':>8} {'cols':>6}")
    print("-" * 62)
    for sheet in info["sheets"]:
        print(f"{sheet['name']:<34} {sheet['state']:<10} "
              f"{sheet['max_row']:>8} {sheet['max_column']:>6}")

    print("\nsheets Phase 1 consumes:")
    for label, candidates, expected in SHEETS:
        try:
            table = read_table(workbook, candidates, expected)
        except LookupError as exc:
            print(f"  {label:<20} NOT RESOLVED - {exc}")
            continue
        print(f"  {label:<20} -> {table.name!r} "
              f"header row {table.header_row}, {len(table.rows)} data rows")
        if args.headers:
            for caption in table.headers:
                if caption:
                    print(f"       {caption}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
