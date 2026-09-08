#!/usr/bin/env python
"""Validate a phase against the reference data.

Phase 1 - latest/old decisions, against the workbook's own LATEST/NOT LATEST
column. Fails (exit 1) on a genuine conflict, which is what makes it a gate.

Phase 2A - DOC TYPE, against column AL of `QatarEnergy-TN WORKING` in the
reference working file. It reports rather than gates: column AL is manually
maintained and holds scope-of-work verdicts as well as document types, so a
threshold on it would encode the reference's own inconsistencies. See
`docs/business-rules/classification-rules.md`.

Phase 2B - DOC IS REQUIRED SOW, against column AM of the same sheet. Reports
rather than gates for the same reason, and for one more: the rules workbook's
`DOCUMENT TYPE` sheet and column AM genuinely disagree on several rules. See
`docs/business-rules/sow-rules.md`.

    python scripts/validate_phase.py                 # phase 1, configured workbook
    python scripts/validate_phase.py --phase 1 --workbook path/to.xlsx
    python scripts/validate_phase.py --phase 2       # DOC TYPE comparison
    python scripts/validate_phase.py --phase 2 --out data/output/latest
    python scripts/validate_phase.py --phase 2b      # DOC IS REQUIRED SOW
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
    export_doc_type_report, export_sow_report, export_validation_report,
)
from app.services.mdr_pipeline import MdrEngine              # noqa: E402
from app.services.sow_service import validate_sow            # noqa: E402

#: Accepted `--phase` values, normalised to lower case. '2' is Phase 2A.
IMPLEMENTED_PHASES = ("1", "2", "2a", "2b")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="1",
                        help="1 = latest/old revision, 2/2a = DOC TYPE, "
                             "2b = DOC IS REQUIRED SOW")
    parser.add_argument("--workbook", type=Path, default=None)
    parser.add_argument("--reference", type=Path, default=None,
                        help="phase 2/2b only: the reference working file")
    parser.add_argument("--rules", type=Path, default=None,
                        help="phase 2/2b only: the rules workbook")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the report to this directory")
    parser.add_argument("--json", action="store_true",
                        help="emit the report as JSON instead of text")
    args = parser.parse_args(argv)
    phase = str(args.phase).strip().lower()

    if phase not in IMPLEMENTED_PHASES:
        print(f"phase {args.phase} is not implemented; "
              f"implemented: {list(IMPLEMENTED_PHASES)}", file=sys.stderr)
        return 2

    if phase in ("2", "2a"):
        return _validate_doc_type(args)
    if phase == "2b":
        return _validate_sow(args)

    workbook = args.workbook or settings.default_workbook()
    if workbook is None:
        print(f"no workbook given and none found in {settings.input_current_dir}",
              file=sys.stderr)
        return 2

    result = MdrEngine(workbook).run()
    report = validate_latest(result)

    if args.json:
        print(json.dumps({
            "phase": phase,
            "workbook": workbook.name,
            "summary": result.summary(),
            "validation": report.to_dict(),
        }, indent=2, ensure_ascii=False))
    else:
        print(f"phase {phase}  |  {workbook.name}")
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


def _validate_sow(args) -> int:
    """Phase 2B: DOC IS REQUIRED SOW against column AM of the working sheet."""
    try:
        report = validate_sow(args.reference, args.rules)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.out:
        export_sow_report(report, args.out)

    if args.json:
        print(json.dumps({"phase": "2B", "sow": report.to_dict()},
                         indent=2, ensure_ascii=False))
        return 0

    print("phase 2B - DOC IS REQUIRED SOW vs 'QatarEnergy-TN WORKING' column AM")
    print(f"  rows evaluated            : {report.rows_evaluated}")
    print(f"  rows with DOC TYPE (AL)   : {report.rows_with_doc_type}")
    print(f"  rows with reference SOW   : {report.rows_with_reference_sow}")
    print(f"  accountable rows          : {report.accountable_rows}")
    print("      (both a resolvable DOC TYPE and a reference SOW value)")
    print(f"  exact SOW matches         : {report.exact_matches}")
    print(f"  SOW mismatches            : {len(report.in_scope_mismatches)}")
    print(f"  match rate (accountable)  : {report.match_rate:.4%}")
    print(f"  blank reference SOW       : {report.blank_reference_sow}")
    print(f"  blank calculated SOW      : {report.blank_calculated_sow}")
    print(f"  unknown DOC TYPE rows     : {report.unknown_doc_type_rows}")
    print(f"  DOC TYPE absent rows      : {report.doc_type_absent_rows}")
    print(f"  non-SOW reference values  : {report.non_sow_reference_rows}")
    print("\n  mismatch root causes:")
    for cause, n in sorted(report.cause_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>6}  {cause}")
    print("\n  per DOC TYPE (accountable rows):")
    for d in report.per_doc_type:
        print(f"    {d['doc_type']:<20} rows={d['rows']:<6} "
              f"matches={d['matches']:<6} mismatches={d['mismatches']}")
    print("\n  top reference -> calculated drift:")
    for d in report.value_drift[:15]:
        print(f"    {d['rows']:>6}  {d['doc_type']:<8} "
              f"{d['reference']!r} != {d['calculated']!r}")
    print("\n  DOC TYPEs the DOCUMENT TYPE sheet does not cover:")
    for d in report.unmapped_doc_types[:15]:
        print(f"    {d['rows']:>6}  {d['doc_type']!r} "
              f"(reference says {d['reference_sow']!r})")
    if args.out:
        print(f"\nreport written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
