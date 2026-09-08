# Phase 3 - SOW and IDB

**Status:** SOW IMPLEMENTED (as Phase 2B); IDB IMPLEMENTED (as Phase 2C).

## Scope

| Output | Column | Status |
|---|---|---|
| `DOC IS REQUIRED SOW` | AM of `QatarEnergy-TN WORKING` | **Implemented** - Phase 2B |
| `DOC IDB COMPLETED STATUS` | AN | **Implemented** - Phase 2C |

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

Implemented in `backend/app/engine/idb/`. No sheet of the rules workbook states
an IDB status, so the rules were reverse-engineered from column AN itself and
reduced to two:

1. **Out of scope means no check is due.** A `NO` from Phase 2B resolves to
   `NO NEED TO CHECK` - 18,704 of the 18,706 reference rows, exceptionless
   through every other column.
2. **In scope means a check is due, and its outcome is recorded elsewhere.**
   `COMPLETED` / `PENDING` / `CANCELLED` and the rest come from the IDB folder
   and the FMTL, which no workbook here holds. The resolver accepts such an
   outcome as an input and states `TO BE CHECK` when none has been supplied.

A DOC TYPE whose SOW Phase 2B cannot resolve produces `UNMAPPED`, never
`NO NEED TO CHECK`.

```bash
python scripts/validate_phase.py --phase 2c --out data/output/latest
```

**97.54%** agreement on whether a check is due - the half of column AN this
phase decides - and 85.67% exact agreement with the column. Only 2 rows
question the rules themselves; 5,384 trace to a Phase 2B rule gap, 1,876 to the
missing completion source and 391 to Phase 2B's already-documented column AM
override. The full evidence, the value-by-value table and the ten open business
questions are in
[`../business-rules/idb-rules.md`](../business-rules/idb-rules.md).

The resolver takes a `SowRequirement` and an optional recorded outcome. It sees
no document number, title, revision, status code, worksheet or column, and
column AN never reaches it.

## Locations

`backend/app/engine/sow/`, `backend/app/engine/idb/`,
`backend/app/domain/models/sow.py`, `backend/app/domain/models/idb.py`,
`backend/app/engine/validation/sow.py`, `backend/app/engine/validation/idb.py`,
[`../business-rules/sow-rules.md`](../business-rules/sow-rules.md),
[`../business-rules/idb-rules.md`](../business-rules/idb-rules.md)
