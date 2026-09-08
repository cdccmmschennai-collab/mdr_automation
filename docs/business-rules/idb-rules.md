# IDB Rules (DOC IDB COMPLETED STATUS)

**Status:** IMPLEMENTED - Phase 2C
**Code:** `backend/app/engine/idb/`, `backend/app/domain/models/idb.py`,
`backend/app/engine/validation/idb.py`, `backend/app/services/idb_service.py`

```bash
python scripts/validate_phase.py --phase 2c --out data/output/latest
```

---

## 1. Target output column

`DOC IDB COMPLETED STATUS` - column AN of the `QatarEnergy-TN WORKING` sheet in
`data/reference/working/20260516_184-Transmittal Log (8).xlsx`, 21,372 data
rows under a header on row 5.

Column AN is the **expected** value. It is read only by
`engine/validation/idb.py` and never reaches a resolver. See section 9.

## 2. Where the rules come from

There is no IDB sheet in the rules workbook. All four of its sheets were
inspected:

| Sheet | States | Used by |
|---|---|---|
| `REQUIRED-KEY DOC.WORDS` | DOC TYPE keywords | Phase 2A |
| `NOT REQUIRED-KEY DOC.WORDS` | DOC TYPE keywords | Phase 2A |
| `DOCUMENT TYPE` | DOKAR -> `DOCUMENT SOW` (22 rows) | Phase 2B |
| `FOLDER-UPDATE` | five notes about folder names ("FOLDER NEEDS TO BE ADDED") | nothing |

`Status Codes` (in the MDR and reference workbooks) describes QatarEnergy
review codes and issue codes; Phase 1 already consumes it for revision
eligibility. **None of these states an IDB status.**

The authority for Phase 2C is therefore the observed behaviour of column AN
itself, read as evidence and reduced to two rules. The reduction is recorded
here and asserted in `backend/tests/`; the reference values themselves are
never copied into the engine.

## 3. The two authoritative rules

| Rule/Input | Result | Source | Notes |
|---|---|---|---|
| DOC IS REQUIRED SOW resolves to `NO` (out of scope) | `NO NEED TO CHECK` | column AN, 18,704 of 18,706 rows | The two exceptions carry the literal `0`, which column AM carries on the same rows. Holds through every other column. |
| DOC IS REQUIRED SOW resolves to `YES...` (in scope) **and** a completion source states the outcome | that outcome | the completion source | No such source exists in this project; see section 5. |
| DOC IS REQUIRED SOW resolves to `YES...` and no completion source has spoken | `TO BE CHECK` | column AN's own usage for an unchecked in-scope document | States the requirement, not an outcome. |
| Phase 2B states no SOW verdict for the DOC TYPE | `UNMAPPED` | - | An upstream rule gap. Never `NO NEED TO CHECK`. |
| A SOW value arrives that is neither `NO` nor `YES...` | `UNMAPPED` | - | Column AM carries `CANCELLED`, `0`, `COMMON`, `MTL/DOC IDB`. None states a scope verdict. |
| A completion source states an outcome outside the vocabulary | `UNMAPPED` | - | `COMPLETE` and `REF` are reported as unknown, never repaired to `COMPLETED`/`REFERENCE`. |

Rule 1 is exact and unconditional. It is true of all 300 rows whose submission
was cancelled, of latest and old revisions alike, and of every issue and review
code in the sheet.

## 4. Resolver inputs

`IdbResolver.resolve(requirement, recorded_outcome="")`

| Input | Type | Origin |
|---|---|---|
| `requirement` | `SowRequirement` | Phase 2B's verdict for the document |
| `recorded_outcome` | `str` | a completion source; **always empty today** |

That is the whole signature. The resolver receives no document number, no
title, no revision, no status code, no worksheet, no row or column, and no
reference value. It does not classify and it does not re-derive scope.

## 5. Why the outcome is an input and not a derivation

`COMPLETED`, `PENDING`, `TO BE CHECK` and the rarer values record the outcome
of a check performed against the **IDB folder** and the **FMTL**. Neither is in
any workbook this project reads. The measured evidence that no column in the
transmittal log predicts them:

* **No column separates `COMPLETED` from `PENDING`.** Cross-tabulated against
  the final issue code, the QatarEnergy review code, the discipline, the
  originator, the latest flag and the presence of remarks, every bucket is
  mixed. The strongest single split, "originator is TEN", still reads 1,178
  `COMPLETED` against 25 `TO BE CHECK` and 23 `PENDING`.
* **The values track sheet position, not document properties.** Of the 114
  `TO BE CHECK` rows, 91 fall in the last 372 rows of the sheet - the newest
  transmittals - while rows 3,000-20,000 are almost entirely `COMPLETED`. That
  is a record of how far the checker has got.
* **`TAG NOT IN FMTL` needs the FMTL**, which the project does not hold.
* **`GENERAL SPECIFICATION` and `REFERENCE` are human judgements.**
  "TECHNICAL SPECIFICATION FOR VERTICAL CENTRIFUGAL PUMPS" reads `GENERAL
  SPECIFICATION`; "TECHNICAL SPECIFICATION FOR NON-API VERTICAL CENTRIFUGAL
  PUMP" reads `COMPLETED`. No title or number rule separates them.

So the engine states the requirement and reports the gap. It never guesses
`COMPLETED`.

## 6. Result vocabulary

Every value below is observed in column AN. Counts are over the sheet's 21,372
data rows.

| Value | Rows | Meaning | Required inputs | Deterministic | Engine can emit | Reference contradictions |
|---|---|---|---|---|---|---|
| `NO NEED TO CHECK` | 18,706 | The document is out of scope, so no IDB check is due | DOC IS REQUIRED SOW | Yes | Yes, by rule 1 | 2 in-scope rows carry it (section 8) |
| `COMPLETED` | 2,364 | The check was done and the IDB is complete | completion source | No | Only from a stated outcome | - |
| `PENDING` | 142 | The check was done and the IDB is not complete | completion source | No | Only from a stated outcome | - |
| `TO BE CHECK` | 114 | In scope, not yet checked | DOC IS REQUIRED SOW | Yes | Yes, by rule 2 | - |
| `GENERAL SPECIFICATION` | 14 | A general specification, not tied to a tag | human judgement | No | Only from a stated outcome | identically shaped titles read `COMPLETED` |
| `COMPLETED (REV UPDATED)` | 9 | Complete, but a newer revision has since arrived | completion source | No | Only from a stated outcome | all 9 rows are the latest revision, not old ones |
| `0` | 7 | Not a status. A data-entry artefact; column AM carries `0` on the same rows | - | - | No | - |
| `CANCELLED` | 6 | The submission was cancelled, so the check will not complete | completion source | No | Only from a stated outcome | cancellation does not predict it (section 8) |
| `TAG NOT IN FMTL` | 3 | The document's tag is absent from the FMTL | the FMTL | No | Only from a stated outcome | - |
| `REFERENCE` | 2 | A typical/reference drawing, not a tagged deliverable | human judgement | No | Only from a stated outcome | - |
| `COMPLETE` | 2 | Spelling variant of `COMPLETED` | - | - | No - rejected, not repaired | - |
| *(blank)* | 2 | No value | - | - | No | - |
| `REF` | 1 | Spelling variant of `REFERENCE` | - | - | No - rejected, not repaired | - |
| `UNMAPPED` | - | **Engine only.** No rule and no completion source states a value | - | - | Yes | not a column AN value |

`UNMAPPED` is deliberately not a business value and is never written as `NO`,
`NO NEED TO CHECK` or blank.

## 7. Revision, cancellation and withdrawal

**Revision reaches IDB only through Phase 2A and Phase 2B, and by no other
route.** Phase 1 decides latest/old, Phase 2A turns an old revision into the
DOC TYPE `OLD REV NOT SOW`, Phase 2B turns that into `NO`, and rule 1 turns
that into `NO NEED TO CHECK`. All 9,934 `OLD REV NOT SOW` rows carry it.

The resolver has **no revision input**, and a direct latest/old test would be
wrong as well as redundant: of the 127 rows that are not the latest revision
yet still in scope, 107 read `COMPLETED` and 18 `PENDING`. An old revision that
is in scope keeps its in-scope status.

Phase 1's revision behaviour is untouched by this phase. Its findings still
hold and are not re-derived here: cancellation does not imply "not latest",
withdrawn submissions are excluded from latest determination, Z/as-built is
never latest, alphabetic revisions rank after numeric.

**Cancellation does not determine the IDB status.** Of the 310 rows whose PDMS
issued status is `CAN`, 300 are out of scope and read `NO NEED TO CHECK` (rule
1 wins). The remaining 7 are in scope and read `CANCELLED` 3 times, `COMPLETED`
3 times and `PENDING` once. A `CAN` branch would therefore be wrong 4 times in
7, and none exists.

`COMPLETED (REV UPDATED)` is **not** an old-revision state: all 9 rows are the
latest revision, and all 9 carry a "CODE-3 FROM TECHNIP/TEBODIN" remark. It is
the checker noting that a completed IDB has been overtaken by a resubmission.

## 8. SOW dependency

IDB depends on the **calculated** SOW requirement:

```
DOC TYPE -> SOW -> IDB
```

`sow_service.build_resolver` supplies the `SowRequirement`; column AM is never
read as an input. A SOW the rules do not resolve produces `UNMAPPED`, not
`NO NEED TO CHECK`.

## 9. No leakage of column AN

* `IdbResolver.resolve` takes a `SowRequirement` and an outcome string. There
  is no parameter through which column AN could arrive.
  (`test_idb_resolver.py::TestScopeBoundary`)
* `compare_idb` reads column AN into a local, compares it, and passes it to
  nothing. (`engine/validation/idb.py`)
* Over the whole sheet the engine emits exactly three values -
  `NO NEED TO CHECK`, `TO BE CHECK`, `UNMAPPED` - so no reference value can
  have been copied through. (`test_idb_agreement.py::TestScopeBoundary`)

## 10. Reference validation

Measured over `QatarEnergy-TN WORKING`, all 21,372 rows:

| Metric | Value |
|---|---|
| rows evaluated | 21,372 |
| rows with a DOC TYPE (AL) | 21,372 |
| rows with a reference IDB (AN) | 21,370 |
| accountable rows | 15,979 |
| exact matches | 13,689 |
| mismatches | 2,290 |
| **exact match rate** | **85.67%** |
| **"is a check due?" agreement** | **97.54%** (15,586 / 15,979) |
| UNMAPPED calculated results | 5,388 |
| blank calculated results | 0 |

Two rates are reported because column AN answers two questions. Phase 2C
decides only the first - whether an IDB check is due - and it decides it for
97.54% of accountable rows. The exact rate is lower because the remaining rows
record a check outcome that no workbook here holds.

### Mismatch taxonomy

| Cause | Rows | Root cause |
|---|---|---|
| `UPSTREAM_SOW_UNRESOLVED` | 5,384 | The DOC TYPE is not in the `DOCUMENT TYPE` sheet (`OTHER`, `GAD`, `TNR`, `MATERIAL SUBMITTAL`, ...), so Phase 2B states no scope verdict and Phase 2C cannot start. A **Phase 2B** rule gap. |
| `COMPLETION_EVIDENCE_NOT_AVAILABLE` | 1,876 | The document is in scope, the reference records the outcome of a check somebody performed, and no completion source told the engine. A **missing input**. |
| `UPSTREAM_SOW_OVERRIDDEN` | 391 | The `DOCUMENT TYPE` sheet puts the DOC TYPE in scope; the working sheet's own column AM overrides it to `NO` and column AN follows. Phase 2B already records this as `REFERENCE_OVERRIDES_TO_NO`. A **Phase 2B** contradiction. |
| `REFERENCE_VALUE_NOT_GENERATABLE` | 19 | `GENERAL SPECIFICATION` (14), `TAG NOT IN FMTL` (3), `REFERENCE` (2). Human judgement, or needs the FMTL. |
| `REFERENCE_NOT_AN_IDB_VALUE` | 7 | Column AN holds `0`. Nothing to compare against. |
| `REFERENCE_SPELLING_VARIANT` | 2 | Column AN holds `COMPLETE`. |
| `REFERENCE_BLANK` | 2 | No ground truth for the row. |
| `RULE_DISAGREES_WITH_REFERENCE` | **2** | The only rows that question the Phase 2C rules; see below. |

The spelling canonicalisation in `engine/validation/idb.py` sorts mismatches
into causes. It never converts a mismatch into a match, and the resolver never
calls it.

## 11. Reference contradictions

**Two rows contradict the sheet's own columns.** Rows 21,273
(`MIR`, "SPIR NORMAL: PUMPS - DOSING") and 21,337 (`MXB`, "PIPING GAD FOR SEA
WATER SUMP") carry a `YES-...` value in column AM - so the sheet itself says a
check is due - and `NO NEED TO CHECK` in column AN. Reported, never patched
into a rule.

**Column AN follows column AM, not the rules workbook.** The 391
`UPSTREAM_SOW_OVERRIDDEN` rows all resolve to a `YES-...` SOW from the
`DOCUMENT TYPE` sheet, are overridden to `NO` by hand in column AM, and then
read `NO NEED TO CHECK` in column AN. Whether the rules sheet or the working
sheet is right is a **Phase 2B** question and is listed in
[`sow-rules.md`](sow-rules.md); Phase 2C did not touch it.

**The `/HIERARCHY` divergence documented in Phase 2B has no effect here.** IDB
reads a SOW value only for its `YES`/`NO` verdict, never for its components, so
whether a SOW string contains `/HIERARCHY` cannot change an IDB status.

## 12. Open business questions

**Implemented and confirmed by the reference**

1. Out of scope means `NO NEED TO CHECK` - 18,704 of 18,706 rows.
2. Old revisions reach `NO NEED TO CHECK` through DOC TYPE, not through a
   revision test - 9,934 of 9,934 rows.
3. In-scope documents need a check regardless of revision, issue code or
   review code.

**Needs a business decision**

4. **Where does the completion outcome come from?** The engine needs a
   completion source stating `COMPLETED` / `PENDING` / `CANCELLED` /
   `COMPLETED (REV UPDATED)` per document. Is it the IDB folder listing, an
   export from another system, or a column that would have to be added?
   Until one exists, 2,364 `COMPLETED` and 142 `PENDING` rows cannot be
   reproduced. **This is the single largest open item in Phase 2C.**
5. **Is `CHECK STATUS` (column AO) the completion source?** Within in-scope
   rows, `AO != #N/A` coincides with `COMPLETED` on 1,538 of 1,557 rows
   (98.8%). But AO is Phase 3B's own output and is itself derived from the
   received-document dump, so using it here would make Phase 2C depend on a
   later phase. Deliberately **not** used. Revisit when Phase 3B exists.
6. **Where does `TAG NOT IN FMTL` come from?** The FMTL is not in the
   repository. Should the tool read it, and where is it held?
7. **Are `GENERAL SPECIFICATION` and `REFERENCE` meant to be automated?** Both
   are currently human judgements about the document, with no rule the titles
   support. If they are to be automated they need a keyword rule of their own,
   most naturally in the rules workbook.
8. **Should an in-scope document with no completion record read `TO BE CHECK`
   or stay blank?** The engine writes `TO BE CHECK`, which is what the working
   sheet does for the newest unchecked rows. Confirm this is the wanted
   default before Phase 2D writes it into a workbook.
9. **`COMPLETE` (2 rows) and `REF` (1 row)** - confirm these are typos of
   `COMPLETED` and `REFERENCE`. The engine rejects them rather than guessing.
10. **`0` in column AN (7 rows)** - a data-entry artefact, or does it mean
    something? Column AM carries `0` on the same rows.

## 13. Not in this phase

Phase 2D (four-column Excel output), Phase 3A (received-document dump), Phase
3B (`CHECK STATUS`, column AO), Phase 3C and Phase 4A are not implemented, and
nothing here writes an `.xlsx` file.
