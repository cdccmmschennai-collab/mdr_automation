# Phase 3 - SOW and IDB

**Status:** SOW IMPLEMENTED (as Phase 2B); IDB NOT IMPLEMENTED.

## Scope

| Output | Column | Status |
|---|---|---|
| `DOC IS REQUIRED SOW` | AM of `QatarEnergy-TN WORKING` | **Implemented** - Phase 2B |
| `DOC IDB COMPLETED STATUS` | AN | Not implemented - Phase 2C |

## DOC IS REQUIRED SOW

Implemented in `backend/app/engine/sow/`, driven by the `DOCUMENT TYPE` sheet
of the rules workbook (22 DOKAR -> SOW mappings) plus the two self-stating
verdicts `OLD REV NOT SOW` and `NOT SOW`, both of which resolve to `NO`.

```bash
python scripts/validate_phase.py --phase 2b --out data/output/latest
```

93.92% agreement with column AM over the 15,977 rows where both the resolver
and the reference state a value. The remaining 972 are grouped by root cause
in [`../business-rules/sow-rules.md`](../business-rules/sow-rules.md), which
also lists the six open questions - chief among them a flat contradiction
between the rules workbook and the working sheet over whether five SOW strings
contain `/HIERARCHY`.

The resolver takes a DOC TYPE and nothing else. It does not classify, does not
re-derive old revisions, and does not interpret the `DOC IDB` text inside a
SOW value.

## DOC IDB COMPLETED STATUS

Not implemented. The input that determines IDB completion has **not been
identified** in any Phase 1 sheet. A SOW value such as `YES-MTL/DOC IDB` says
a DOC IDB is required; it says nothing about whether one was completed.

## Locations

`backend/app/engine/sow/`, `backend/app/engine/idb/` (empty),
[`../business-rules/sow-rules.md`](../business-rules/sow-rules.md),
[`../business-rules/idb-rules.md`](../business-rules/idb-rules.md)
