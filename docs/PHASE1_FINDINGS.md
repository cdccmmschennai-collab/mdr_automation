# MDR Engine — Phase 1 Findings

Every rule below was derived from the supplied workbooks, not assumed. Where a
candidate rule was tested and **rejected**, that is recorded too, because the
rejection is as important as the rule.

Source workbook: `input/new/_20260720-184-Transmittal Log (9) MDR.xlsx`
Reference workbook: `input/reference/20260516_184-Transmittal Log (8).xlsx`
Rules workbook: `input/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`

---

## 1. Discovered structure

### New MDR workbook (9)

| Sheet | Size | Role |
|---|---|---|
| `QatarEnergy-TN` | 22,009 × 39 | Primary document/transmittal log. Header on **row 5**. |
| `TN FROM VENDORS` | 605 × 16 | Vendor submissions. Header on **row 5**. |
| `Status Codes` | 14 × 6 | Review codes (col A/B) + issue codes (col D/E/F). |
| `VENDOR LIST` | 36 × 3 | Vendor → responsible engineer. |

**A `VENDOR DETAILS` sheet does not exist** in either workbook — only
`VENDOR LIST`. The brief names it; the data does not have it. Nothing in
Phase 1 depends on it.

### Reference workbook (8)

Contains the same four sheets **plus `QatarEnergy-TN WORKING`** (21,377 × 46) —
the manually prepared working file. It is the log sheet with five MDR columns
inserted at **AK–AO**, which pushes the original last three columns to AR–AT:

| Col | Header |
|---|---|
| AK | `DOC WITH REV` |
| AL | `DOC TYPE` |
| AM | `DOC IS REQUIRED SOW` |
| AN | `DOC IDB COMPLETED STATUS` |
| AO | `CHECK STATUS` |

These are the Phase 2+ outputs. Phase 1 does not populate them.

### Key discovery: built-in ground truth

`QatarEnergy-TN` column **X — `LATEST/ NOT LATEST`** already holds the manual
`L` / `NL` determination for 21,274 rows. This is exactly what the revision
engine computes, so it serves as ground truth for validation. It is *not* used
as an input to any decision.

---

## 2. Established rules

### RULE 1 — Alphabetic revisions rank later than numeric ✅ CONFIRMED

Tested both orderings against the `L`/`NL` column, over document groups where
every row is labelled:

| Ordering | Agree | Disagree | Rate |
|---|---|---|---|
| **Alphabetic later** | **7,653** | **1** | **99.99%** |
| Numeric later | 5,231 | 2,423 | 68.3% |

The business rule as stated in the brief is strongly supported.
Implemented as ordering *bands*, not lexical or `max()` comparison, so `10`
correctly outranks `9` and `A` outranks `5`.

### RULE 2 — `Z` is an as-built marker, not the 26th letter ✅ CONFIRMED

The `Status Codes` sheet defines the ASB sequence as
`AFC-GRASS FIELD / Z-BROWN FIELD`. In the data:

- 68 rows carry revision `Z`
- **68 of 68** have issue code `ASB`
- **0 of 68** are ever marked `L`
- in **all 68**, a sibling revision holds the `L`

Treating `Z` as a normal letter would wrongly hand it the latest flag in all 68
groups. It is given its own band and excluded from latest candidacy
(`revision_status = AS_BUILT`).

### RULE 3 — Cancellation does *not* exclude a row from latest ✅ CONFIRMED

Counter-intuitive but unambiguous:

| Signal | Rows | Marked `L` |
|---|---|---|
| Issue code `CAN` | 339 | 326 (96%) |
| Review `CODE-11` | 320 | 319 (99.7%) |

A cancelled document **is** the latest revision of itself. The engine does not
exclude it.

### RULE 4 — Withdrawn submissions are excluded ✅ CONFIRMED (n=1)

`4391-MTY-4-15-0004` is the **single** genuine counter-example to Rule 1:
revision `A` exists but revision `1` is marked `L`. Its status column reads
`WITHDRAWIN` and its remarks `WITHDRAWN EMAIL … RETURNED TO TECHNIP`.

Implemented as an exclusion **and** flagged as an exception, so a human still
sees it. Note the low evidence base (one row); it is isolated in
`WITHDRAWN_MARKERS` for easy revision.

---

## 3. Rejected rule — document renumbering ❌ TESTED AND REJECTED

431 document groups have **no `L` at all** — every row is `NL`. Their profile
differs sharply from normal groups:

| Signal | All-NL groups | Groups with an `L` |
|---|---|---|
| Issue code `IFC` | 89.2% | 32.4% |
| Review `CODE-2` | 88.5% | 38.8% |
| Single-row group | 403 / 431 | — |

Where remarks exist they read *"DOC NO. UPDATED REF DOC NO. X"*,
*"DOC NO. CHANGED TO NON-DELIVERABLE"*, *"DOC REF NO HAS BEEN CHANGED FROM …"*
— the document continued life under a **different number**.

A rule excluding rows with such remarks was implemented and then **removed**,
because the evidence does not support it:

- the remark pattern matches 182 rows → **128 `NL` / 50 `L`**
- the overall base rate is already ~64% `NL`, so the signal is negligible
- in all three conflicts it introduced, the renumbered row was itself the `L`

Worse, **387 of the 480 all-NL rows carry no remark at all**, so no
deterministic signal exists for the majority.

**Conclusion:** `NL`-with-no-latest encodes *"not an active deliverable"*, a
different meaning from *"not the newest revision"*. It is not derivable from
the available columns and is **out of Phase 1 scope**. The pattern is retained
as an informational `renumbering_note` flag only. This is the largest open
question for Phase 2 and needs a business answer, not a guess.

---

## 4. Validation results

Engine vs. the workbook's own `LATEST/ NOT LATEST` column:

```
compared rows           21,115
agreements              20,605
raw agreement rate      97.58%
adjusted agreement rate 100.00%
genuine conflicts       0
```

Every one of the 510 disagreements has an identified root cause:

| Cause | Rows | Who is right |
|---|---|---|
| `WORKBOOK_MARKS_GROUP_INACTIVE` | 431 | Out of scope — not modelled (§3) |
| `STALE_HIGHER_REVISION_UNPROCESSED` | 77 | **Engine** — workbook backlog |
| `STALE_DUPLICATE_LATEST_FLAG` | 2 | **Engine** — stale flag |
| `GENUINE_CONFLICT` | **0** | — |

### On the "adjusted 100%"

This figure measures agreement over rows the engine is accountable for. It
**excludes** the 431 inactive-group rows, where the engine is *not validated* —
not proven correct. Read it alongside the cause table, never alone.

### The workbook is stale, and that is the point

79 rows prove the manual process lags: a newer revision arrives and the old row
keeps its `L`. Two documents even carry **two** `L` rows
(`VEN-4391-M4TY-2-80-0003`, `4391-5-MS-0043`) — both from rows dated
2026-07-16, the newest in the file. A further **262 rows are entirely
unlabelled**. That backlog is precisely the work this tool removes.

---

## 5. Matching results

Only **18.5%** of vendor rows (111/600) resolve to a QatarEnergy document.
This is a genuine business fact, not a defect: the identifier columns are
mostly empty or hold vendor-internal numbers.

| Vendor column | Populated |
|---|---|
| `Vendor Document No.` | 524 / 600 |
| `PROJECT DOCUMENT/ DRAWING NO.` | 143 / 600 |
| `PROJECT DOC NO.` | 52 / 600 |

Most unmatched rows carry vendor-internal identifiers (`DEW-5718-*`,
`BQ/IMS/QT-169/*`) that were never issued to QatarEnergy under a project
document number. The engine reports `NOT_MATCHED` honestly rather than forcing
a match.

Ambiguity is effectively nil: exactly **one** canonical key maps to more than
one document (`4391-0-CV-00XX` vs `4391-0-CV-00xx`, a case-only difference).

---

## 6. Data quality observations

| Observation | Count |
|---|---|
| Issue-code casing variants (`AfC`, `Re-AFC`, `RE--IFA`) | 372 rows — normalised |
| Rows with `-` or blank `DOCUMENT NO.` | 286 — skipped, not documents |
| Distinct `REV` values | 38 (incl. `-`, `Z`, multi-digit to `18`) |
| Duplicate top revision within a group | 2 groups — raised as exceptions |

---

## 7. Scope boundaries honoured

Not implemented in Phase 1, per the brief: DOC TYPE classification, SOW, IDB,
received-document dump / CHECK STATUS, Excel output, frontend, deployment.
No AI/LLM is used anywhere — every decision is deterministic and explainable.

The rules workbook was profiled but not wired in, since Phase 1 needs no
classification. It loads cleanly when Phase 2 begins:
`REQUIRED-KEY DOC.WORDS` (83 rows), `DOCUMENT TYPE` (22 types with DOKAR codes
and SOW strings), `NOT REQUIRED-KEY DOC.WORDS` (101 rows), `FOLDER-UPDATE` (6).
Note it already uses glob syntax (`*P&ID*LEGEND*`) and an inline `or`
(`LIGHTING LAYOUT or LIGHTNING LAYOUT`) that Phase 2 will need to parse.

---

## 8. Open questions for the business

1. **What does `NL` on a whole document group mean?** (431 groups) Renumbered,
   superseded, non-deliverable — or simply never reviewed? This is the single
   largest unmodelled behaviour.
2. **Should a renumbered document link to its successor?** The remarks name the
   new number; a successor relationship could be modelled explicitly.
3. **Is `WITHDRAWN` a recognised lifecycle state?** Only one row uses it, with
   no dedicated column.
4. **Should the 262 unlabelled rows be written back?** Phase 1 deliberately
   does not modify the workbook.
