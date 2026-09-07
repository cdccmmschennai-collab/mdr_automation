# Classification Rules (DOC TYPE)

**Status:** ❌ NOT IMPLEMENTED — Phase 2
**Reserved code location:** `backend/app/engine/classification/` (empty)

No classification rule has been derived, and none is stated here. Writing one
now would be inventing business logic. This file records only what Phase 1
observed while profiling the inputs.

---

## What exists as input

`data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx` — profiled during Phase 1 but
**not read by any code**. It loads cleanly and contains:

| Sheet | Rows | Contents |
|---|---|---|
| `REQUIRED-KEY DOC.WORDS` | 83 | Keywords marking a document as required |
| `DOCUMENT TYPE` | 22 | Document types with DOKAR codes and SOW strings |
| `NOT REQUIRED-KEY DOC.WORDS` | 101 | Keywords marking a document as not required |
| `FOLDER-UPDATE` | 6 | — |

## Known parsing problems to solve first

The keyword sheets are not plain literals. Phase 2 will need to handle:

- **glob syntax** — e.g. `*P&ID*LEGEND*`
- **inline alternation** — e.g. `LIGHTING LAYOUT or LIGHTNING LAYOUT`

Whether matching is case-insensitive, whether it applies to `DOCUMENT TITLE`
alone or also to `DISCIPLINE`, and how conflicting keyword hits are resolved
are all **unanswered**.

## Target output column

`DOC TYPE` — column AL of the `QatarEnergy-TN WORKING` sheet in the reference
workbook. Phase 1 does not populate it.
