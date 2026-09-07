# Phase 5 — Excel MDR Output

**Status:** ❌ NOT IMPLEMENTED.

## Intended scope

Generate the MDR workbook: the source log plus the five computed columns
inserted at AK–AO, matching the reference workbook''s `QatarEnergy-TN WORKING`
sheet.

| Col | Header | Produced by |
|---|---|---|
| AK | `DOC WITH REV` | Phase 1 data, not yet emitted to Excel |
| AL | `DOC TYPE` | Phase 2 |
| AM | `DOC IS REQUIRED SOW` | Phase 3 |
| AN | `DOC IDB COMPLETED STATUS` | Phase 3 |
| AO | `CHECK STATUS` | Phase 4 |

## What exists today

Phase 1 emits JSON and CSV only, via `services/export_service.py`. There is no
Excel **writer** anywhere in the backend — `openpyxl` is used for reading only,
always with `read_only=True`.

## Non-negotiable constraint

The source workbooks must remain untouched. Output goes to a new file under
`data/output/`, never over an input.

## Reserved location

`backend/app/infrastructure/excel/` — a writer module alongside the existing
readers.
