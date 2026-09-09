# Phase 5 — Excel MDR Output

**Status:** ✅ IMPLEMENTED.

> **Numbering.** This file is `phase-05`, but the code, the CLI banner and the
> test suites call the same work **Phase 2D**. The two schemes are described in
> [phase numbering](README.md); nothing below depends on which name is used.

## Delivered scope

A copy of the uploaded workbook, saved under a new name, carrying every sheet
it arrived with plus exactly one added sheet:

```
QatarEnergy-TN            unchanged
QatarEnergy-TN Automated  the same rows, plus the five automation columns
TN FROM VENDORS           unchanged
Status Codes              unchanged
VENDOR LIST               unchanged
QatarEnergy-TN WORKING    unchanged, if the employee had already made one
```

`QatarEnergy-TN Automated` is the sheet name the product contract fixes, and it
is the only sheet the writer creates or modifies. It is named after the sheet
it mirrors, so an employee can see at a glance which source sheet it belongs
to. A test pins the literal string, so a rename has to be made deliberately.

The five columns are **inserted** immediately before
`QATARENERGY SIGNED / NOT SIGNED` — the position `QatarEnergy-TN WORKING` uses
— not appended. Over the real workbook that places them at AK–AO. The trailing
columns shift right and take their widths, merged ranges, conditional formats
and data validations with them.

| Col | Header | Produced by | Written |
|---|---|---|---|
| AK | `DOC WITH REV` | Phase 1 | yes |
| AL | `DOC TYPE` | Phase 2A | yes, where a keyword rule matches |
| AM | `DOC IS REQUIRED SOW` | Phase 2B | yes, where the rules workbook states a scope |
| AN | `DOC IDB COMPLETED STATUS` | Phase 2C | `NO NEED TO CHECK` / `UNMAPPED` / blank |
| AO | `CHECK STATUS` | Phase 4 (3A/3B) | **never** — caption only |

`CHECK STATUS` is styled like its neighbours and left empty on every row.
`AutomationRow` raises `CheckStatusNotEvaluated` if anything tries to give it a
value, so the column cannot start filling by accident. A blank there means
*not evaluated*; it must never be read as `NOT RECEIVED`.

A blank `DOC IDB COMPLETED STATUS` is likewise a decision, not a gap: the
document is in scope, a check is due, and no completion source exists to say
how it went. `AutomationRow.idb_source` records `NO_COMPLETION_SOURCE`, so a
blank is never mistaken for an unresolved row.

## Where it lives

| Module | Role |
|---|---|
| `infrastructure/excel/output_workbook.py` | The only module that opens a workbook for writing. Sheet names, column letters, styles and openpyxl live here and nowhere else. |
| `services/automation_service.py` | Runs Phases 1–2C and collects one `AutomationRow` per source row. Holds no rule and imports no openpyxl. |
| `services/export_service.py` | Chooses the destination filename and refuses one that resolves to the source. |
| `domain/models/automation.py` | The five captions and the `CHECK STATUS` guard. |

Run it with `mdr-engine --excel` (or `python -m app.cli --excel`). The output
is `<source stem>_MDR_AUTOMATED.xlsx` in `--outdir`, which is deterministic:
a re-run replaces its own output rather than leaving a second copy beside it.

## Non-negotiable constraint — held

The source workbook is never modified. It is opened, copied in memory and
saved elsewhere; a destination that resolves to the source raises
`OutputWouldOverwriteSource` in both the writer and the export service. Tests
assert the source's SHA-256, size and mtime are unchanged by a full run.

An input that already carries a hand-worked `QatarEnergy-TN WORKING` is treated
no differently: that sheet is never read for its answers, never used as the
output and never touched. Its `DOC IDB COMPLETED STATUS` and `CHECK STATUS`
values are somebody's manual work, and no run may repeat them as if the
automation had derived them.

## Tests

| Suite | Covers |
|---|---|
| `tests/integration/test_automated_workbook.py` | The generated file, over a synthetic workbook: sheet preservation, column insertion, merges/filters/validations shifting, the download contract, determinism, source integrity. |
| `tests/integration/test_phase2d_pipeline.py` | The same exporter over the real 22,009-row workbook, end to end. Skips when the workbook is absent. |
| `tests/unit/test_automation_row.py`, `tests/unit/test_automation_service.py` | The row model and the phase chaining. |
