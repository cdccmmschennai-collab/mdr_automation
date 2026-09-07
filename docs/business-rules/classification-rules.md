# Classification Rules (DOC TYPE)

**Status:** IMPLEMENTED - Phase 2A
**Code:** `backend/app/engine/classification/`
**Validation:** `backend/app/engine/validation/doc_type.py`,
`scripts/validate_phase.py --phase 2`

Phase 2A assigns **DOC TYPE** and nothing else. `DOC IS REQUIRED SOW`,
`DOC IDB COMPLETED STATUS` and `CHECK STATUS` are **not implemented** and are
not described here as though they were.

---

## 1. Classification inputs

The classifier receives exactly two fields:

| Field | Source column |
|---|---|
| `document_number` | `QatarEnergy-TN` column D, `DOCUMENT NO.` |
| `document_title` | `QatarEnergy-TN` column R, `DOCUMENT TITLE` |

Nothing else. Revision, `FINAL ISSUE CODES`, `AREA`, `DISCIPLINE` and
`ORGINATOR` are **not** consulted, because no rule in the keyword workbook
refers to them: its two keyword columns are literally headed
`DOC NUMBER- KEYWORD` and `DOC DESC- KEYWORDS`.

Cells that mean "no value" in this project's convention (`-`, `N/A`, `#N/A`,
`NONE`, `NIL`, blank) are treated as absent, so a placeholder dash cannot
satisfy a keyword.

The classifier never sees a worksheet, a row index or a column letter. The
Excel adapter (`infrastructure/excel/mdr_workbook.py`) has already turned the
row into named fields.

---

## 2. Rule sources

`data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`

| Sheet | Rows read | Use |
|---|---|---|
| `REQUIRED-KEY DOC.WORDS` | 82 | Rules, higher precedence |
| `NOT REQUIRED-KEY DOC.WORDS` | 100 | Rules, lower precedence |
| `DOCUMENT TYPE` | - | **Not read.** DOKAR codes and SOW strings; Phase 2B |
| `FOLDER-UPDATE` | - | **Not read.** Folder maintenance notes |

Each rule row is three cells:

| Column | Meaning |
|---|---|
| A `DOC NUMBER- KEYWORD` | pattern matched against the document number |
| B `DOC DESC- KEYWORDS` | pattern matched against the document title |
| C `DOC TYPE` | the answer both imply |

`KEYWORD NOT APPLICABLE` in A or B means that side of the rule is unused. A row
with both sides filled - there are four - fires when **either** side matches;
row 70 of the required sheet (`-MS-` / `*MATERIAL*SUBMITTAL*`) is the clearest
case, where the document number and the title are two routes to the same
answer.

Column C is taken literally as the DOC TYPE. It is not a clean DOKAR-code
vocabulary: rows 63-75 of the required sheet answer with descriptive names
(`MATERIAL SUBMITTAL`, `PROCESS FLOW DIAGRAM`, `ELECTRICAL LOAD LIST`) where
neighbouring rows answer with codes (`OREF`, `MXB`, `MDS`). That inconsistency
is the workbook's, and it is reproduced rather than silently normalised - see
the unresolved ambiguities in section 8.

---

## 3. Normalisation

Whitespace is collapsed and case is folded. **Nothing else.**

```
"  process   data\nsheet " -> "PROCESS DATA SHEET"
```

Punctuation is deliberately preserved. The workbook lists `HOOK-UP`, `HOOK UP`
and `HOOKUP` as three separate rules, and `P&ID`, `PIPING&INSTRUMENT` and
`PIPING INSTRUMENT` as three more. Collapsing hyphens or ampersands would merge
distinctions the business drew on purpose.

---

## 4. Matching semantics

### 4.1 Plain literals match as substrings

A keyword with no `*` matches anywhere in the text, without word boundaries.

**This is the authors' own convention, not a tuning choice.** The keywords are
written in the singular while the documents they are meant to catch are plural
or inflected:

| Keyword | Title it must catch |
|---|---|
| `TEST CERTIFICATE` | `TYPE TEST CERTIFICATES FOR LV POWER CABLES` |
| `BILL OF MATERIAL` | `BILL OF MATERIALS FOR NGL-1/2 LER-3404` |
| `LOOP DRAWING` | `F&G LOOP DRAWINGS NGL-3` |
| `CROSS SECTION` | `PUMP CROSS SECTIONAL DRAWING` |
| `PIPING AND INSTRUMENT` | `PIPING AND INSTRUMENTATION DIAGRAMS` |
| `ISOMETRIC` | `ISOMETRIC DRAWINGS OF NGL 3 & 4` |
| `O&M MANUAL` | `INSTALLATION, OPERATION AND MAINTENANCE MANUALS` |

Word-bounded matching was implemented and measured against the reference
workbook. It **loses 78 rows the reference gets right** - every one of them a
plural or inflection like the table above - and gains 4. Substring matching is
therefore the rule.

The cost is real and is accepted: `PLAN` matches inside `PLANNING`, and the
plant name `EFFLUENT WATER TREATMENT PLANT` contains `PLAN`. Precedence
(section 5) keeps that from dominating, and the four rows where it still
misfires are listed in section 7.

### 4.2 `*` is a wildcard

`*A*B*` requires `A`, then `B` somewhere after it. Order matters:
`*P&ID*LEGEND*` matches `UTILITY P&ID LEGEND SHEET 1` but not
`LEGEND SHEET FOR THE P&ID`.

Leading and trailing `*` are free: the pattern is searched, never anchored.
`*CV*` is written with stars precisely so it matches loosely.

### 4.3 ` or ` is alternation

`LIGHTING LAYOUT or LIGHTNING LAYOUT` is two alternatives; either one firing
fires the rule. The `or` must be surrounded by whitespace, so `ROUTING LAYOUT`
is not split. It is matched case-insensitively - the workbook writes it in
lower case.

An alternative may itself contain wildcards.

### 4.4 `XXXX` is a digit run - document numbers only

`-13-XXXX` means `-13-` followed by four digits, so it matches
`4391-MEWTP-2-13-0005` but not `4391-MEWTP-2-13-ABCD` and not
`VEN-MEWTP-5-43-11`.

This applies to `DOC NUMBER- KEYWORD` only. It is a document-number convention,
and no title keyword in the workbook contains a run of X's.

---

## 5. Precedence

A document may match several rules; 1,865 of the reference sheet's rows do.
Precedence decides which answer wins. **Every match is retained** on the result
(`competing_doc_types`, `matches`), so the competition stays visible to a human
and to Phase 2B.

### 5.1 Required beats not-required - DERIVED, strong evidence

Where rules from both sheets matched the same row, the reference workbook's own
answer agreed with:

| Sheet | Rows |
|---|---|
| `REQUIRED-KEY DOC.WORDS` | **84** |
| `NOT REQUIRED-KEY DOC.WORDS` | **0** |
| neither (a third label) | 31 |

84 to 0. The required sheet wins.

### 5.2 Then workbook row order - DERIVED, weak evidence

Within one sheet, the earlier row wins. So `*P&ID*LEGEND*` (required row 10)
outranks `P&ID` (required row 51), and a P&ID legend sheet classifies as `LGD`
rather than `MXB`.

The evidence is thin. Comparing row order against the alternative - letting a
document-number rule outrank an earlier title rule - over rows where the two
disagree:

| Tie-break | Rows the reference agrees with |
|---|---|
| Workbook row order | **22** |
| Document number first | 4 |

Row order wins 22 to 4, and it is the order the business authored the rules in,
so it is adopted. It is **not** a settled business rule: see section 8.

### 5.3 Within one rule

A rule that fires on both the document number and the title records the number
match first. This cannot change the answer - one rule has one DOC TYPE - it
only orders the audit trail.

### 5.4 What was NOT adopted

Longest-pattern-wins and not-required-first were both measured and rejected
(75.9 % and 73.4 % against 76.4 % for the adopted order).

---

## 6. Multiple-match and no-match behaviour

**Multiple matches:** the precedence winner becomes `doc_type`; every match is
kept in `matches`, and `competing_doc_types` lists the distinct answers in
precedence order. `is_ambiguous` is true when more than one DOC TYPE matched.

**No match:** `doc_type` is the empty string and `matches` is empty. The
classifier reports "no rule covers this document" - it never guesses, and it
never invents a catch-all bucket. 5,277 of the reference sheet's 21,372 rows
are unclassified on this basis.

---

## 7. Validation against the reference workbook

`20260516_184-Transmittal Log (8).xlsx`, sheet `QatarEnergy-TN WORKING`,
column AL `DOC TYPE`. Read-only; column AL is ground truth and is **never** an
input to the classifier.

```
python scripts/validate_phase.py --phase 2 --out data/output/latest
```

### 7.1 Headline

| Measure | Rows |
|---|---|
| Rows evaluated | 21,372 |
| Rows where column AL states a document type | 3,356 |
| Exact matches | **2,564** |
| Mismatches | 792 |
| **Match rate over comparable rows** | **76.40 %** |
| Blank reference rows | 0 |
| Rows where column AL is *not* a document type | 18,016 |
| Engine unclassified (whole sheet) | 5,277 |
| Rows where more than one rule matched | 1,865 |

### 7.2 Column AL is not a DOC TYPE column

This is the single most important finding of Phase 2A. Of 21,372 rows:

| Column AL value | Rows | What it actually is |
|---|---|---|
| `OLD REV NOT SOW` | 9,934 | a revision + scope-of-work verdict |
| `OTHER` | 4,411 | a residual scope-of-work bucket |
| `NOT SOW` | 3,648 | a scope-of-work verdict |
| `NO` | 23 | a scope-of-work verdict |
| a real document type | 3,356 | what Phase 2A produces |

None of those four verdicts appears in the DOC TYPE column of the rules
workbook, so no keyword rule can ever produce one. They belong to Phase 2B.
Quoting a match rate over all 21,372 rows would be meaningless; the 76.40 % is
quoted over the 3,356 rows the reference actually states a document type for.

### 7.3 Mismatch root causes

| Cause | Rows |
|---|---|
| `REFERENCE_NOT_A_DOC_TYPE` (out of scope, counted not listed) | 18,016 |
| `RULE_DISAGREES_WITH_REFERENCE` | 449 |
| `NO_RULE_MATCHED` | 338 |
| `COMPETING_RULES` | 5 |

Grouped by what actually causes them:

**A. Vocabulary drift - the reference and the rules workbook name the same
thing differently (~230 rows).** The clearest is `GAD`: the reference labels
127 general-arrangement drawings `GAD`, while required-sheet rows 56-59 map
`GENERAL ARRANGEMENT`, `GA DRAWING` and `GAD` to `MXS`. The workbook itself
states the equivalence in several other cases - `PFD` is the *keyword* whose
DOC TYPE is `PROCESS FLOW DIAGRAM`, `UFD` likewise for `UTILITY FLOW DIAGRAM`.

| Reference | Engine | Rows |
|---|---|---|
| `GAD` | `MXS` | 127 |
| `MS` | `MATERIAL SUBMITTAL` | 38 |
| `UFD` | `UTILITY FLOW DIAGRAM` | 16 |
| `PFD` | `PROCESS FLOW DIAGRAM` | 11 |
| `LEGENDS AND SYMBOLS` | `LGD` | 8 |
| `MWD` | `WIRING DIAGRAM` | 7 |
| `SCHEMATIC` | `SCHEMATIC DIAGRAM` | 5 |
| `LOAD LIST` | `ELECTRICAL LOAD LIST` | 5 |

No equivalence table has been encoded, in either the classifier or the report.
Which vocabulary is authoritative is a business question (section 8.1).

**B. The rules workbook is newer than the reference (16 rows).** The reference
labels manufacturer record books `MVD`; required-sheet row 37 maps
`MANUFACTURER RECORD BOOK` to `MMD`. The `FOLDER-UPDATE` sheet confirms a
migration is under way: *"MVD - Valve Drawings | CHANGE THE FOLDER NAME TO
MVD-VENDOR DOCUMENTS"*.

**C. Compound labels the rule set cannot express (42 rows).** The reference
writes `MXB-DEM` for demolition P&IDs - a document type with a demolition
marker appended. The rules workbook has a `DEM` keyword answering `DEM`, but
nothing that says "append `-DEM` to another answer". Not implemented; see 8.2.

**D. Rules that do not exist yet (338 rows).** Led by `GAD` (102 -
`GA AND DETAILS FOR NEW HOLDING SUMP`), `MLD` (70 - `FIRE & GAS LAYOUT`,
`PROPOSED LAYOUT OF TEMPORARY FACILITIES`; the required sheet lists seven
specific `... LAYOUT` phrases and these are not among them), `MXS` (38 -
`TANK ROOF NOZZLE DETAILS`, and the misspelling `GENRAL ARRANGEMENT`), `MVD`
(31) and `SOW` (12 - `SCOPE OF WORK FOR SAMPLING CAMPAIGN`, which has no rule
at all). These are gaps in the rule set, not wrong rules. Adding a keyword for
each would be inventing business rules from the reference's answers.

**E. Manual classification in the reference (~150 rows).** 58 rows titled
`MATERIAL SUBMITTAL FOR ...` are labelled `MOM` by hand. The reference is also
internally inconsistent: `PUMP NAME PLATE DRAWING - API PUMPS, TAG P-8956 A/B`
is `MNP` while `PUMP NAME PLATE DRAWING - API PUMPS, TAG P-13108 A/B` is `MMD`.
Identical titles, different answers. No rule can reproduce both.

**F. Precedence (5 rows).** Four CV rows and one material submittal. This is
the entire cost of the precedence question - see 8.4.

### 7.4 `LATEST/ NOT LATEST` interaction - recorded, NOT implemented

`OLD REV NOT SOW` tracks the revision flag almost perfectly:

| `LATEST/ NOT LATEST` | Rows labelled `OLD REV NOT SOW` |
|---|---|
| `NL` | 9,831 |
| blank | 91 |
| `-` | 8 |
| `L` | **4** |

This confirms `OLD REV NOT SOW` is a revision + scope-of-work verdict, not a
document type: it says "this row is an old revision, so it is not in scope",
which is a Phase 2B statement about a document Phase 1 has already ranked.

**Phase 2A does not implement it.** The classifier emits DOC TYPE only, and
Phase 1's latest-revision engine is untouched. The finding is recorded because
Phase 2B will need it.

---

## 8. Unresolved ambiguities

These are reported, not guessed. Each needs a business answer.

### 8.1 Which vocabulary is authoritative?

For the same document the rules workbook says `MXS` and the reference says
`GAD`; the workbook says `MATERIAL SUBMITTAL` and the reference says both
`MATERIAL SUBMITTAL` (271 rows) and `MS` (38 rows). Phase 2A emits the rules
workbook's label, because the rules workbook is the stated rule source. If the
DOKAR codes in the `DOCUMENT TYPE` sheet are the required output vocabulary,
a mapping is needed - and `MS`, `GAD`, `MWD`, `UFD`, `PFD`, `LOAD LIST`,
`SCHEMATIC` and `LEGENDS AND SYMBOLS` have no DOKAR code in that sheet.

### 8.2 Compound and multi-valued labels

The reference records `MXB-DEM` (42 rows), and also `GAD/MWD` (7),
`SCHEMATIC/MWD` (5), `GAD/MMC/MWD` (2), `MHR/MSI`, `MOM/MLP`, `MMC/SCHEMATIC`,
`GAD/ISOMETRIC`, `MWD/SCHEMATIC`. The rules workbook has no construct for a
suffix or for more than one type per document. Phase 2A returns a single DOC
TYPE and lists the others in `competing_doc_types`.

### 8.3 Should a "not required" document get a DOC TYPE at all?

The not-required sheet supplies DOC TYPE labels (`PLAN`, `CV`,
`TECHNICAL QUERY`, ...), and Phase 2A emits them. Whether those rows should
carry a document type, or only a scope-of-work verdict, is Phase 2B's question.

### 8.4 Within-sheet precedence

Section 5.2 adopts workbook row order on 22-to-4 evidence. The alternative -
a document-number keyword outranking an earlier title keyword - would fix the
four `CV OF ... PLANNING ENGINEER` rows, where `-CV-` in the document number is
better evidence than `PLAN` inside the word `PLANNING`, and break 22 demolition
isometrics, where `DEM` in the document number would beat `ISOMETRIC` in the
title. Both readings are defensible. The measured cost of the choice is 5 rows
out of 3,356.

### 8.5 Do not chase the remaining 23.6 %

Most of it is categories A, B, C and E above: label drift, a stale reference,
constructs the rule set cannot express, and manual answers that contradict each
other. Adding a special-case rule per mismatch would encode the reference's
inconsistencies as business rules. Accuracy against a defensible rule set is
worth more than a higher number.

---

## 9. What is NOT implemented

| Capability | Status |
|---|---|
| `DOC TYPE` | IMPLEMENTED |
| `DOC IS REQUIRED SOW` (column AM) | NOT IMPLEMENTED |
| `DOC IDB COMPLETED STATUS` (column AN) | NOT IMPLEMENTED |
| `CHECK STATUS` (column AO) | NOT IMPLEMENTED |
| Received-document dump / index | NOT IMPLEMENTED |
| Vendor consolidation (`TN FROM VENDORS`) | NOT IMPLEMENTED, disabled |
| Excel output / `MDR AUTOMATION` sheet | NOT IMPLEMENTED |
| Frontend MDR processing | NOT IMPLEMENTED |

Columns AM, AN and AO of the reference sheet are not read by any code.

`TN FROM VENDORS` is **not** merged into the classification universe. The
processing universe is `QatarEnergy-TN` only. `settings.vendor_consolidation_enabled`
is `False` and nothing reads it as `True`; no consolidation code exists.
