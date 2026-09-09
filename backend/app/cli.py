"""Command line entry point.

    python -m app.cli --workbook <path> --outdir <dir> [--validate] [--excel]

`--excel` is Phase 2D: it writes a copy of the input workbook carrying the
five automation columns, and prints the source workbook's SHA-256 before and
after so the run can be seen not to have touched it.

Reads only; the source workbook is never modified. Paths default to the
configured data directories (see `core.config`), so nothing production-specific
is hard-coded here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core.config import settings
from .domain.models.automation import AUTOMATION_COLUMNS, CHECK_STATUS
from .engine.validation.latest import validate_latest
from .infrastructure.filesystem.artifact_writer import sha256_file
from .services.automation_service import AutomationRun, build_automation_rows
from .services.export_service import (
    export_automated_workbook, export_automation_rows, export_result,
    export_validation_report,
)
from .services.idb_service import build_resolvers
from .services.mdr_pipeline import MdrEngine


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mdr-engine",
                                description="MDR Automation Tool - Phase 1 engine")
    p.add_argument("--workbook", type=Path, default=None,
                   help="path to the MDR workbook to process "
                        "(default: the workbook in data/input/current)")
    p.add_argument("--outdir", type=Path, default=None,
                   help="directory for the machine-readable result "
                        "(default: data/output/latest)")
    p.add_argument("--validate", action="store_true",
                   help="compare against the workbook's own LATEST/NOT LATEST column")
    p.add_argument("--excel", action="store_true",
                   help="Phase 2D: write a copy of the workbook carrying the "
                        "five automation columns")
    p.add_argument("--quiet", action="store_true")
    return p


def _run_excel(workbook: Path, result, rules_workbook, outdir: Path,
               quiet: bool) -> None:
    """Phase 2D: resolve the five columns and write the employee's workbook."""
    before = sha256_file(workbook)

    sow_resolver, idb_resolver = build_resolvers(rules_workbook)
    run = AutomationRun(result=result,
                        rows=build_automation_rows(result.documents,
                                                   sow_resolver, idb_resolver))
    report = export_automated_workbook(workbook, run.rows, outdir)
    export_automation_rows(run.rows, outdir)

    after = sha256_file(workbook)
    summary = run.summary()

    if quiet:
        return
    print("\n" + "-" * 72)
    print("PHASE 2D - FIVE-COLUMN EXCEL OUTPUT")
    print("-" * 72)
    print(f"  output workbook : {report.destination}")
    print(f"  source sheet    : {report.source_sheet!r} "
          f"(header row {report.header_row})")
    print(f"  automated sheet : {report.automated_sheet!r}")
    print(f"  sheets in output: {', '.join(report.sheet_names)}")
    print(f"  rows written    : {report.rows_written} of {report.data_rows} "
          f"data rows")
    print("\n  columns:")
    for caption in AUTOMATION_COLUMNS:
        letter = report.columns[caption]
        note = ("intentionally blank - no received-document dump (Phase 3A)"
                if caption == CHECK_STATUS else "populated")
        print(f"    {letter:>3}  {caption:<26} {note}")
    print("\n  populated cells:")
    for key in ("doc_with_rev_populated", "doc_type_populated",
                "sow_populated", "idb_populated", "check_status_populated"):
        print(f"    {key:<26}: {summary[key]}")
    print("\n  DOC IDB COMPLETED STATUS:")
    for value, n in sorted(summary["idb_counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {n:>6}  {value or '(blank)'}")
    print("\n  source workbook SHA-256:")
    print(f"    before: {before}")
    print(f"    after : {after}")
    print(f"    {'UNCHANGED' if before == after else 'CHANGED - THIS IS A BUG'}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    workbook = args.workbook or settings.default_workbook()
    if workbook is None:
        print(f"no workbook given and none found in {settings.input_current_dir}",
              file=sys.stderr)
        return 2
    outdir: Path = args.outdir or settings.output_latest_dir

    engine = MdrEngine(workbook)
    result = engine.run()

    export_result(result, outdir)

    summary = result.summary()
    if not args.quiet:
        print("=" * 72)
        print("MDR ENGINE - PHASE 1")
        print("=" * 72)
        print(f"workbook      : {workbook.name}")
        print(f"QE sheet      : {result.discovery['qe_sheet']!r} "
              f"(header row {result.discovery['qe_header_row']})")
        print(f"vendor sheet  : {result.discovery['vendor_sheet']!r} "
              f"(header row {result.discovery['vendor_header_row']})")
        print()
        for k, v in summary.items():
            print(f"  {k:<24}: {v}")

    if args.validate:
        report = validate_latest(result)
        export_validation_report(report, outdir)
        if not args.quiet:
            print("\n" + "-" * 72)
            print("VALIDATION vs workbook LATEST/NOT LATEST column")
            print("-" * 72)
            print(f"  compared rows          : {report.compared}")
            print(f"  agreements             : {report.agreements}")
            print(f"  disagreements          : {len(report.disagreements)}")
            print(f"  raw agreement rate     : {report.agreement_rate:.4%}")
            print(f"  adjusted agreement rate: {report.adjusted_agreement_rate:.4%}")
            print("      (over rows the engine is accountable for; excludes")
            print("       provably-stale workbook labels and rows whose group")
            print("       the workbook marks inactive - NOT a correctness claim")
            print("       on those excluded rows)")
            print(f"  unlabelled (backlog)   : {report.unlabelled_rows}")
            print(f"  as-built / exceptions  : {report.exception_rows}")
            print("\n  disagreement root causes:")
            for cause, n in sorted(report.cause_counts.items(),
                                   key=lambda kv: -kv[1]):
                print(f"    {n:>6}  {cause}")
            if report.genuine_conflicts:
                print("\n  GENUINE CONFLICTS (engine defects):")
                for d in report.genuine_conflicts[:10]:
                    print(f"    row{d.source_row} {d.document} rev={d.revision!r} "
                          f"engine={d.engine_status} workbook={d.workbook_flag}")
                    print(f"       group: {d.group}")
            else:
                print("\n  GENUINE CONFLICTS: none")

    if args.excel:
        _run_excel(workbook, result, engine.rules_workbook, outdir, args.quiet)

    if not args.quiet:
        print(f"\nwritten to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
