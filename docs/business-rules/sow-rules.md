# SOW Rules (DOC IS REQUIRED SOW)

**Status:** IMPLEMENTED - Phase 2B
**Code:** `backend/app/engine/sow/`
**Validation:** `scripts/validate_phase.py --phase 2b`

Phase 2B takes the DOC TYPE that Phase 2A decided and returns the string the
business writes into `DOC IS REQUIRED SOW`. It classifies nothing, it reads no
document number or title, and it does not interpret the `DOC IDB` text inside
a SOW value - that is Phase 2C.

```text
document -> Phase 2A -> DOC TYPE -> Phase 2B -> DOC IS REQUIRED SOW
```

---

## 1. The rule

### 1.1 The `DOCUMENT TYPE` sheet

`INPUT-KEYWORDS  FOR MDR TOOL.xlsx`, sheet `DOCUMENT TYPE`, rows 3-24. Each
row names a document type, its DOKAR code and its SOW string. All 22:

| Row | DOCUMENT TYPE | DOKAR | DOCUMENT SOW |
|----|----|----|----|
| 3  | EQPT DATA SHEET | MDS | `YES-MTL/DOC IDB` |
| 4  | SPIR | MIR | `YES-FMTL/MTL/BOM/DOC IDB` |
| 5  | LAYOUT DIAGRAM | MLD | `YES-FMTL/MTL/DOC IDB` |
| 6  | LOOP DIAGRAM | MLP | `YES-FMTL/MTL/HIERARCHY/DOC IDB` |
| 7  | EQPT BOM (MFR'S PARTS LIST) | MMC | `YES-MTL/BOM/DOC IDB` |
| 8  | MANUFACTURER DRGS | MMD | `YES-MTL/DOC IDB` |
| 9  | OPERATION & MAINT MANUAL | MOM | `YES-PM IDB/DOC IDB` |
| 10 | SINGLE LINE DRGS | MSL | `YES-FMTL/MTL/HIERARCHY/DOC IDB` |
| 11 | VENDOR DRGS | MVD | `YES-MTL/DOC IDB` |
| 12 | P & I DRGS | MXB | `YES-FMTL/MTL/HIERARCHY/DOC IDB` |
| 13 | CROSS SECTIONAL DRGS | MXS | `YES-MTL/DOC IDB` |
| 14 | SPECIFICATION SHEET | MSS | `YES-MTL/DOC IDB` |
| 15 | TEST CERTIFICATE | MTC | `YES-MTL/DOC IDB` |
| 16 | NAME PLATE PHOTOGRAPHY | MNP | `YES-MTL/DOC IDB` |
| 17 | SPADE DRAWING | MXX | `YES-DOC IDB` |
| 18 | CAUSE & EFFECT | MCE | `YES-DOC IDB` |
| 19 | SIL STUDY REPORT | MSI | `YES-DOC IDB` |
| 20 | HAZOP STUDY REPORT | MHR | `YES-DOC IDB` |
| 21 | ISOMETRIC DRAWING | MPI | `YES-MTL/DOC IDB` |
| 22 | PIPING SPECIFICATION | MPS | `YES-MTL/DOC IDB` |
| 23 | BLOCK DIAGRAM | MBD | `YES-FMTL/MTL/HIERARCHY/DOC IDB` |
| 24 | SCHEMATIC DIAGRAM | MSD | `YES-FMTL/MTL/HIERARCHY/DOC IDB` |

Twenty-two document types, seven distinct SOW strings. Because each row names
the type *and* its code, the lookup accepts either: Phase 2A emits DOKAR codes
for most documents but spells a few out (`SCHEMATIC DIAGRAM`), and both forms
are the workbook's own vocabulary.

The SOW string is carried **verbatim**. It is one opaque business value; its
separators carry meaning (`YES-MTL/DOC IDB` is not `YES-MTL/BOM/DOC IDB`), so
nothing normalises it.

### 1.2 The two self-stating verdicts

Two values that arrive as a DOC TYPE are not document types at all but scope
verdicts that state their own answer:

| DOC TYPE | DOC IS REQUIRED SOW | Evidence |
|----|----|----|
| `OLD REV NOT SOW` | `NO` | 9,934 of 9,934 reference rows |
| `NOT SOW` | `NO` | 3,648 of 3,648 reference rows |

Both are exceptionless in column AM. `OLD REV NOT SOW` originates in Phase 1's
revision verdict and reaches Phase 2B through Phase 2A; **Phase 2B contains no
old-revision logic of its own** - it consumes the verdict, it does not
recompute it.

`OTHER` is deliberately **not** in this set. It reads `NO` in 4,237 of its
4,411 reference rows and `YES-...` in the other 174, so it states no rule.

### 1.3 Unknown DOC TYPE

A DOC TYPE the sheet does not cover produces an **unresolved** requirement
with an empty SOW value - never a guess, and in particular never `NO`. `NO` is
a business statement that a document is out of scope; a missing rule is not
the same fact. `SowRequirement.is_required` is three-valued for that reason:
`True`, `False`, or `None` when nothing was resolved.

---

## 2. Validation against the reference workbook

`20260516_184-Transmittal Log (8).xlsx`, sheet `QatarEnergy-TN WORKING`.
Column AL supplies the DOC TYPE; column AM is the expected answer. **Column AM
is never an input** - `SowResolver.resolve()` takes a DOC TYPE and nothing
else, and columns AN and AO are not read at all.

```text
rows evaluated              21,372
rows with a DOC TYPE (AL)   21,372
rows with a reference SOW   21,372
accountable rows            15,977      both sides state a value
exact SOW matches           15,005
SOW mismatches                 972
match rate                  93.92%      over accountable rows
blank reference SOW              0
blank calculated SOW         5,388
unknown DOC TYPE rows        5,386
non-SOW reference values         9
```

Per DOKAR, over accountable rows:

| DOC TYPE | rows | matches | mismatches |
|----|----|----|----|
| OLD REV NOT SOW | 9,934 | 9,934 | 0 |
| NOT SOW | 3,648 | 3,648 | 0 |
| MPI | 716 | 664 | 52 |
| MDS | 364 | 332 | 32 |
| MLD | 334 | 133 | 201 |
| MIR | 247 | 160 | 87 |
| MXS | 129 | 17 | 112 |
| MOM | 103 | 0 | 103 |
| MXB | 80 | 0 | 80 |
| MSL | 79 | 0 | 79 |
| MSS | 66 | 28 | 38 |
| MMD | 63 | 9 | 54 |
| MVD | 55 | 8 | 47 |
| MTC | 35 | 23 | 12 |
| MNP | 29 | 26 | 3 |
| MMC | 27 | 2 | 25 |
| MBD | 17 | 0 | 17 |
| MCE | 16 | 9 | 7 |
| MLP | 14 | 0 | 14 |
| MHR | 10 | 7 | 3 |
| MSI | 5 | 3 | 2 |
| MSD | 4 | 0 | 4 |
| MXX | 2 | 2 | 0 |

---

## 3. Mismatch categories

### 3.1 `RULE_STATES_HIERARCHY` - 166 rows

**Systematic, and the clearest discrepancy in the data.** Every rule whose SOW
string contains `/HIERARCHY` (MLP, MSL, MXB, MBD, MSD) is written into column
AM *without* it:

| DOKAR | rule | reference | rows |
|----|----|----|----|
| MXB | `YES-FMTL/MTL/HIERARCHY/DOC IDB` | `YES-FMTL/MTL/DOC IDB` | 73 |
| MSL | `YES-FMTL/MTL/HIERARCHY/DOC IDB` | `YES-FMTL/MTL/DOC IDB` | 71 |
| MBD | `YES-FMTL/MTL/HIERARCHY/DOC IDB` | `YES-FMTL/MTL/DOC IDB` | 17 |
| MSD | `YES-FMTL/MTL/HIERARCHY/DOC IDB` | `YES-FMTL/MTL/DOC IDB` | 4 |
| MLP | `YES-FMTL/MTL/HIERARCHY/DOC IDB` | `YES-FMTL/MTL/DOC IDB` | 1 |

Those five DOKARs agree with the rule on **zero** rows out of 197, and the
word `HIERARCHY` appears in column AM only 31 times, always in some other
combination (`YES-HIERARCHY`, `YES-MTL/HIERARCHY/DOC IDB`,
`YES-HIERARCHY/DOC IDB`) and never for one of these five.

**Unresolved.** Either the rules workbook added `HIERARCHY` after the working
sheet was filled in, or the working sheet is behind. Both sources are supplied
as authoritative, so the engine follows the rules workbook (the authored rule)
and this file reports the divergence. **This needs a business decision before
Phase 2D writes SOW values into a deliverable workbook.**

### 3.2 `REFERENCE_OVERRIDES_TO_NO` - 391 rows

The rule says the document is in scope; column AM says `NO`.

| DOKAR | rows | | DOKAR | rows |
|----|----|----|----|----|
| MLD | 177 | | MDS | 21 |
| MIR | 44 | | MXS | 13 |
| MMD | 39 | | MSL | 4 |
| MOM | 32 | | MXB, MTC | 3 each |
| MSS | 28 | | MSI | 2 |
| MVD | 22 | | MNP, MCE, MPI | 1 each |

**DOC TYPE does not predict which rows get this.** The MLD group is the
clearest: 176 of the 177 are `LATEST` rows, and the split is semantic, not
structural -

```text
CABLE ROUTING LAYOUT ...          -> NO
CIVIL LAYOUT FOR NGL-4            -> NO
EQUIPMENT LAYOUT DRAWING ...      -> YES-FMTL/MTL/DOC IDB
EARTHING LAYOUT-LER 25A           -> YES-FMTL/MTL/DOC IDB
F&G DEVICES LOCATION LAYOUT ...   -> YES-FMTL/MTL/DOC IDB
```

The distinction is whether the layout carries material, which is a judgement
about the document's content, not about its type. **Unresolved.** No rule is
derivable from the columns available, and no per-document exception has been
hard-coded to close the gap.

### 3.3 `RULE_DISAGREES_WITH_REFERENCE` - 401 rows

Both sides state a SOW value and they name different components. The larger
groups, each of which is a standing disagreement between the two workbooks:

| DOKAR | reference | rule | rows |
|----|----|----|----|
| MXS | `YES-MTL/BOM/DOC IDB` | `YES-MTL/DOC IDB` | 66 |
| MIR | `YES-BOM/DOC IDB` | `YES-FMTL/MTL/BOM/DOC IDB` | 43 |
| MOM | `YES-COMMON` | `YES-PM IDB/DOC IDB` | 31 |
| MOM | `YES-DOC IDB` | `YES-PM IDB/DOC IDB` | 26 |
| MPI | `YES-DEMOLITION` | `YES-MTL/DOC IDB` | 21 |
| MLD | `YES-FMTL/DOC IDB` | `YES-FMTL/MTL/DOC IDB` | 21 |
| MMC | `YES-BOM/DOC IDB` | `YES-MTL/BOM/DOC IDB` | 17 |
| MVD | `YES-COMMON` | `YES-MTL/DOC IDB` | 17 |

Two sub-cases stand out:

* **MOM never matches.** The rule's `YES-PM IDB/DOC IDB` does not occur
  anywhere in column AM - not once in 21,372 rows.
* **Column AM uses SOW values the `DOCUMENT TYPE` sheet does not define** -
  `YES-COMMON` (167 rows), `YES-DEMOLITION` (66), `YES-FMTL` (73), `YES-MTL`
  (59), `YES-BOM/DOC IDB` (61), `YES-HIERARCHY` (19). The rules workbook has
  no rule that can produce any of them.

**Unresolved.** The rules workbook is followed; the divergence is reported.

### 3.4 `REFERENCE_SPELLING_VARIANT` - 14 rows

Column AM is hand-typed. These name the same components as the rule and differ
only in punctuation or spelling: `YES/MTL/DOC IDB` (9), `YES-FMTL/MTL-DOC IDB`,
`YES MTL/DOC IDB`, `YEE-MTL/DOC IDB`, `YES/DOC IDB`, `YES- DOC IDB`.

They are **counted as mismatches, not as matches.** The canonicalisation in
`engine/validation/sow.py` exists only to sort a mismatch into this bucket; it
never touches the value Phase 2B computes and never converts a mismatch into a
match.

### 3.5 `DOC_TYPE_NOT_IN_SOW_TABLE` - 5,386 rows (out of scope)

Column AL names something the `DOCUMENT TYPE` sheet does not cover, so the
resolver produces nothing and there is no rule to grade. This is a **rule gap
in the rules workbook**, not an engine defect. The full list:

| rows | DOC TYPE | | rows | DOC TYPE |
|----|----|----|----|----|
| 4,411 | OTHER | | 16 | UFD |
| 276 | MATERIAL SUBMITTAL | | 13 | SOW |
| 229 | GAD | | 12 | PFD |
| 131 | TNR | | 11 | MWD |
| 70 | CV | | 8 | LEGENDS AND SYMBOLS, SCHEMATIC |
| 54 | VDR | | 7 | GAD/MWD |
| 45 | MXB-DEM | | 5 | MDR, SCHEMATIC/MWD, LOAD LIST |
| 39 | MS | | 2 | GAD/MMC/MWD, VENDOR LIST, EQUIPMENT LIST |
| 23 | NO | | 1 | 11 further labels |

Several are compound (`GAD/MWD`, `MHR/MSI`, `MOM/MLP`, `MMC/SCHEMATIC`) - a
manual convention for a document that is two things at once. The rules
workbook has no equivalent, and none was invented.

### 3.6 `REFERENCE_NOT_A_SOW_VALUE` - 9 rows (out of scope)

Column AM holds something that is not a scope verdict: `CANCELLED` (3),
`MTL/DOC IDB` (3), `0` (2), `COMMON` (1). Workbook data-entry states, not
rules.

---

## 4. Summary of unresolved questions

Ordered by how much they would change a Phase 2D deliverable:

1. **HIERARCHY** (166 rows) - does the SOW string for MLP/MSL/MXB/MBD/MSD
   include `/HIERARCHY` or not? The two source workbooks disagree flatly.
2. **The `NO` override** (391 rows) - what makes an in-scope document type out
   of scope on a particular row? Not derivable from any available column.
3. **MOM** (103 rows) - the rule's `YES-PM IDB/DOC IDB` is never used in
   practice. Which value is current?
4. **MXS / MMC / MIR component drift** (126 rows) - the rules workbook and the
   working sheet disagree on which of MTL / FMTL / BOM belong in the value.
5. **SOW values with no rule** - `YES-COMMON`, `YES-DEMOLITION`, `YES-FMTL`,
   `YES-MTL`, `YES-BOM/DOC IDB`, `YES-HIERARCHY` are used in column AM and are
   producible by no rule in the workbook.
6. **DOC TYPEs with no SOW rule** (5,386 rows) - chiefly `OTHER`, plus `GAD`,
   `TNR`, `MATERIAL SUBMITTAL`, `VDR`, `MXB-DEM` and the compound labels.

None has been closed by a hard-coded exception. The engine implements the
rules the workbook states and reports everything else.

---

## 5. Not in Phase 2B

* **DOC IDB COMPLETED STATUS** (Phase 2C). The `DOC IDB` text inside a SOW
  value is part of that value. Nothing here turns it into `COMPLETED`,
  `PENDING` or `NO NEED TO CHECK`.
* **CHECK STATUS** (Phase 3B) and the received-document dump (Phase 3A).
* **Excel output** (Phase 2D). Phase 2B writes no workbook; the source files
  are opened read-only and verified byte-for-byte unchanged.
