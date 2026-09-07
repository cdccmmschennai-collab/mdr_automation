# Revision Rules

**Status:** ✅ Implemented (Phase 1)
**Code:** `backend/app/engine/revision/`
**Evidence:** [MDR_BUSINESS_RULES.md](MDR_BUSINESS_RULES.md) §2, §3

---

## Where a revision comes from

The `REV` field, and nowhere else.

**Rule:** a digit or letter inside a document number is never a revision.
`4391-MTY-1-19-0051` parses as `UNPARSEABLE`, not as revision 51.

Excel may hand back `3` as `3.0`; a clean integral float is normalised.

---

## Ordering bands

Revisions sort by `(band, ordinal)`. Bands, lowest to highest:

| Band | Accepts | Ordinal | Eligible for latest? |
|---|---|---|---|
| `UNPARSEABLE` | anything else | 0 | ❌ |
| `NUMERIC` | `0`–`999` | the number | ✅ |
| `ALPHABETIC` | `A`–`Y` | `A`=0 … `Y`=24 | ✅ |
| `AS_BUILT` | `Z` | 0 | ❌ |

### Rule 1 — alphabetic ranks after numeric

`0 < 1 < 2 < … < A < B < C`

Banding, not lexical comparison: `10` outranks `9`, and `A` outranks `99`.

Verified against the workbook's own `LATEST/ NOT LATEST` column: **99.99 %**
agreement (7,653/7,654) versus **68.3 %** for the inverse ordering.

### Rule 2 — `Z` is an AS-BUILT marker, not the 26th letter

The Status Codes sheet defines the ASB sequence as
`AFC-GRASS FIELD / Z-BROWN FIELD`. All 68 `Z` rows carry issue code `ASB`, none
is ever marked `L`, and in all 68 a sibling revision holds the `L`.

`Z` is reported as `revision_status = AS_BUILT` — a known category, **not** an
exception needing review.

---

## Latest determination

Within each document identity group, the **eligible** row with the highest
`(band, ordinal)` is `LATEST`. Every other eligible row is `OLD`.

### Exclusions from candidacy

| Signal | Excluded? | Also an exception? |
|---|---|---|
| Unparseable revision | ✅ | ✅ |
| Revision `Z` (as-built) | ✅ | ❌ — reported as `AS_BUILT` |
| Status/remarks contain `WITHDRAW` | ✅ | ✅ |
| Cancellation (`CODE-11` / `CAN`) | ❌ **not excluded** | ❌ |
| Renumbering remark | ❌ **not excluded** | ❌ — noted only |

### Rule 3 — cancellation can still be latest

A cancelled document **is** the latest revision of itself. Issue code `CAN`:
339 rows, 326 marked `L` (96 %). Review `CODE-11`: 320 rows, 319 marked `L`
(99.7 %).

### Rule 4 — withdrawn submissions are excluded

Evidence base is **one row**: `4391-MTY-4-15-0004` rev `A`, status `WITHDRAWIN`.
It is the single genuine counter-example to Rule 1. Isolated in
`WITHDRAWN_MARKERS` so it is cheap to revise.

### Rule 5 ❌ REJECTED — renumbering remarks do **not** exclude a row

Tested and removed. The pattern matches 182 rows → 128 `NL` / 50 `L` against a
~64 % `NL` base rate: negligible signal. In all three conflicts it introduced,
the renumbered row was itself the `L`. Retained as an informational
`renumbering_note` flag only.

---

## Ambiguity

**Rule:** never guess.

- Two rows share the highest revision → **both** become `EXCEPTION`, neither is
  latest. (2 such groups in the workbook.)
- No row in a group is eligible → the **whole group** becomes `EXCEPTION`.

---

## Status Code interpretation

Review codes (`CODE-1`…`CODE-11`) and issue codes (`IFC`, `IFA`, `AFC`, `ASB`,
…) are **loaded from the workbook's own `Status Codes` sheet**, not hard-coded.
A revised sheet changes behaviour without a code change.

Casing and punctuation variants found in the data (`AfC`, `Re-AFC`, `RE--IFA` —
372 rows) collapse to one canonical code. `RE-` re-issues resolve via their base
code's definition. The `STATUS` column holds bare numbers (`2`, `10`) where the
sheet spells them `CODE-2`; both forms resolve.

Semantics carried on the codes:

- `requires_resubmission` — `CODE-1/2/3`
- `work_may_proceed` — `CODE-1/2/10`
- `is_cancellation` — `CODE-11`
- `is_as_built` — base code `ASB`
- `expected_revision_band` — derived from the sheet's revision-sequence text

---

## Every decision carries a reason

Each row emits a `reason` (and, for exceptions, an `exception_reason`) naming
why it got its status — e.g. `superseded by revision 'B' (band=ALPHABETIC)`.
Asserted for all 21,718 rows by
`tests/integration/test_phase1_workbook.py::TestScale`.

---

## Observed results

| Status | Rows |
|---|---|
| `LATEST` | 8,161 |
| `OLD` | 13,216 |
| `AS_BUILT` | 68 |
| `EXCEPTION` | 273 |
