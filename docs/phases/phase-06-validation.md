# Phase 6 — Validation

**Status:** ⚠️ PARTIAL — Phase 1 validation exists; later-phase validation does not.

## What exists

`backend/app/engine/validation/latest.py` validates exactly one thing: the
latest-revision decision, against the workbook''s own `LATEST/ NOT LATEST`
column (21,274 labelled rows serving as ground truth).

Disagreements are classified by root cause rather than reported as a single
percentage, because some of the workbook''s own labels are stale:

| Cause | Rows | Who is right |
|---|---|---|
| `WORKBOOK_MARKS_GROUP_INACTIVE` | 431 | Out of scope — not modelled |
| `STALE_HIGHER_REVISION_UNPROCESSED` | 77 | **Engine** — workbook backlog |
| `STALE_DUPLICATE_LATEST_FLAG` | 2 | **Engine** — stale flag |
| `GENUINE_CONFLICT` | **0** | — |

### On the "adjusted 100 %"

The adjusted rate measures agreement over rows the engine is accountable for.
It **excludes** the 431 inactive-group rows, where the engine is *not
validated* — not proven correct. Read it alongside the cause table, never alone.

## What does not exist

Validation of classification, SOW, IDB and check status — those stages are not
implemented. When they are, each needs its own cause-classified comparison
rather than a bare accuracy figure.

## Regression coverage

`backend/tests/regression/test_ground_truth_agreement.py` fails if a genuine
conflict ever reappears.
