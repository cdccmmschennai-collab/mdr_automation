"""Phase 1 command line entry point.

    python -m mdr_engine.cli --workbook <path> --outdir output [--validate]

Reads only; the source workbook is never modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import MdrEngine, write_csv, write_json
from .validate import validate_latest

DEFAULT_WORKBOOK = (Path(__file__).resolve().parents[2] / "input" / "new"
                    / "_20260720-184-Transmittal Log (9) MDR.xlsx")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mdr-engine",
                                description="MDR Automation Tool - Phase 1 engine")
    p.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK,
                   help="path to the MDR workbook to process")
    p.add_argument("--outdir", type=Path,
                   default=Path(__file__).resolve().parents[2] / "output",
                   help="directory for the machine-readable result")
    p.add_argument("--validate", action="store_true",
                   help="compare against the workbook's own LATEST/NOT LATEST column")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    engine = MdrEngine(args.workbook)
    result = engine.run()

    outdir: Path = args.outdir
    write_json(result, outdir / "mdr_phase1_result.json")
    write_csv(result.documents, outdir / "documents.csv")
    write_csv(result.vendor_rows, outdir / "vendor_rows.csv")
    write_csv(result.exceptions, outdir / "exceptions.csv")

    summary = result.summary()
    if not args.quiet:
        print("=" * 72)
        print("MDR ENGINE - PHASE 1")
        print("=" * 72)
        print(f"workbook      : {args.workbook.name}")
        print(f"QE sheet      : {result.discovery['qe_sheet']!r} "
              f"(header row {result.discovery['qe_header_row']})")
        print(f"vendor sheet  : {result.discovery['vendor_sheet']!r} "
              f"(header row {result.discovery['vendor_header_row']})")
        print()
        for k, v in summary.items():
            print(f"  {k:<24}: {v}")

    if args.validate:
        report = validate_latest(result)
        (outdir / "validation_report.json").write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8")
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

    if not args.quiet:
        print(f"\nwritten to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
