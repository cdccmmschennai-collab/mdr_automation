#!/usr/bin/env python
"""Validate a phase against the reference data.

Phase 1 - latest/old decisions, against the workbook's own LATEST/NOT LATEST
column. Fails (exit 1) on a genuine conflict, which is what makes it a gate.

Phase 2A - DOC TYPE, against column AL of `QatarEnergy-TN WORKING` in the
reference working file. It reports rather than gates: column AL is manually
maintained and holds scope-of-work verdicts as well as document types, so a
threshold on it would encode the reference's own inconsistencies. See
`docs/business-rules/classification-rules.md`.

    python scripts/validate_phase.py                 # phase 1, configured workbook
    python scripts/validate_phase.py --phase 1 --workbook path/to.xlsx
    python scripts/validate_phase.py --phase 2       # DOC TYPE comparison
    python scripts/validate_phase.py --phase 2 --out data/output/latest
    python scripts/validate_phase.py --json          # machine-readable

Read-only unless `--out` is given, and never writes to a source workbook.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings                        # noqa: E402
from app.engine.validation.latest import validate_latest     # noqa: E402
from app.services.classification_service import validate_doc_types  # noqa: E402
from app.services.export_service import (                    # noqa: E402
    export_doc_type_report, export_validation_report,
)
from app.services.mdr_pipeline import MdrEngine              # noqa: E402

IMPLEMENTED_PHASES = {1, 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=int, default=1,
                        help="1 = latest/old revision, 2 = DOC TYPE (Phase 2A)")
    parser.add_argument("--workbook", type=Path, default=None)
    parser.add_argument("--reference", type=Path, default=None,
                        help="phase 2 only: the reference working file")
    parser.add_argument("--rules", type=Path, default=None,
                        help="phase 2 only: the keyword rules workbook")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the report to this directory")
    parser.add_argument("--json", action="store_true",
                        help="emit the report as JSON instead of text")
    args = parser.parse_args(argv)

    if args.phase not in IMPLEMENTED_PHASES:
        print(f"phase {args.phase} is not implemented; "
              f"implemented: {sorted(IMPLEMENTED_PHASES)}", file=sys.stderr)
        return 2

    if args.phase == 2:
        return _validate_doc_type(args)

    workbook = args.workbook or settings.default_workbook()
    if workbook is None:
        print(f"no workbook given and none found in {settings.input_current_dir}",
              file=sys.stderr)
        return 2

    result = MdrEngine(workbook).run()
    report = validate_latest(result)

    if args.json:
        print(json.dumps({
            "phase": args.phase,
            "workbook": workbook.name,
            "summary": result.summary(),
            "validation": report.to_dict(),
        }, indent=2, ensure_ascii=False))
    else:
        print(f"phase {args.phase}  |  {workbook.name}")
        print(f"  compared rows      : {report.compared}")
        print(f"  agreements         : {report.agreements}")
        print(f"  raw agreement      : {report.agreement_rate:.4%}")
        print(f"  adjusted agreement : {report.adjusted_agreement_rate:.4%}")
        print(f"  genuine conflicts  : {len(report.genuine_conflicts)}")
        for cause, n in sorted(report.cause_counts.items(), key=lambda kv: -kv[1]):
            print(f"      {n:>6}  {cause}")

    if args.out:
        export_validation_report(report, args.out)
        print(f"\nreport written to {args.out}")

    if report.genuine_conflicts:
        print(f"\nFAIL: {len(report.genuine_conflicts)} genuine conflict(s)",
              file=sys.stderr)
        return 1
    print("\nPASS: no genuine conflicts")
    return 0


def _validate_doc_type(args) -> int:
    """Phase 2A: DOC TYPE against column AL of QatarEnergy-TN WORKING."""
    try:
        report = validate_doc_types(args.reference, args.rules)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.out:
        export_doc_type_report(report, args.out)

    if args.json:
        print(json.dumps({"phase": "2A", "doc_type": report.to_dict()},
                         indent=2, ensure_ascii=False))
        return 0

    print("phase 2A - DOC TYPE vs 'QatarEnergy-TN WORKING' column AL")
    print(f"  rows evaluated            : {report.rows_evaluated}")
    print(f"  rows with reference type  : {report.rows_with_reference_doc_type}")
    print(f"  exact matches             : {report.exact_matches}")
    print(f"  mismatches                : {len(report.in_scope_mismatches)}")
    print(f"  match rate (comparable)   : {report.match_rate:.4%}")
    print(f"  blank reference rows      : {report.blank_reference_rows}")
    print(f"  non-doc-type reference    : {report.non_doc_type_reference_rows}")
    print("      (OLD REV NOT SOW / NOT SOW / OTHER / NO - scope-of-work and")
    print("       revision verdicts belonging to Phase 2B+, not document types)")
    print(f"  engine unclassified rows  : {report.unclassified_rows}")
    print(f"  rows where rules competed : {report.ambiguous_rows}")
    print("\n  mismatch root causes:")
    for cause, n in sorted(report.cause_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>6}  {cause}")
    print("\n  top reference -> engine label pairs:")
    for d in report.label_drift[:12]:
        print(f"    {d['rows']:>6}  {d['reference']!r} -> {d['engine']!r}")
    if args.out:
        print(f"\nreport written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
