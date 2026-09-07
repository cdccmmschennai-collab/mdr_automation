# Phase 2A - DOC TYPE Classification

**Status:** IMPLEMENTED.

## Scope delivered

`DOC TYPE` is assigned from the document number and title using the keyword
rules in `data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`
(`REQUIRED-KEY DOC.WORDS` and `NOT REQUIRED-KEY DOC.WORDS`).

The rules, their matching semantics, the derived precedence and the full
mismatch analysis are in
[`../business-rules/classification-rules.md`](../business-rules/classification-rules.md).

## Where the code lives

```
backend/app/engine/classification/rules.py       keyword syntax + precedence
backend/app/engine/classification/classifier.py  the verdict
backend/app/domain/models/classification.py      the result
backend/app/infrastructure/excel/rules_workbook.py       rules adapter
backend/app/infrastructure/excel/reference_workbook.py   ground-truth adapter
backend/app/engine/validation/doc_type.py        reference comparison
backend/app/services/classification_service.py   wiring
```

## Validation

```
python scripts/validate_phase.py --phase 2 --out data/output/latest
```

2,564 exact matches over the 3,356 rows where `QatarEnergy-TN WORKING`
column AL states a document type - **76.40 %**. The other 18,016 rows hold
scope-of-work or revision verdicts (`OLD REV NOT SOW`, `NOT SOW`, `OTHER`,
`NO`), which no keyword rule can produce and which belong to Phase 2B.

Unlike Phase 1's check this **reports rather than gates**: column AL is
manually maintained and internally inconsistent, so a threshold on it would
encode its own errors.

## Deliberately NOT in this phase

`DOC IS REQUIRED SOW`, `DOC IDB COMPLETED STATUS`, `CHECK STATUS`,
received-document processing, vendor consolidation, Excel output and the
frontend MDR UI. See the phase documents for those.

## Open questions carried forward

1. **Which DOC TYPE vocabulary is authoritative** - the rules workbook's
   labels or the reference's? The two disagree on `GAD`/`MXS`,
   `MS`/`MATERIAL SUBMITTAL`, `UFD`/`UTILITY FLOW DIAGRAM` and others.
2. **Compound and multi-valued labels** - `MXB-DEM`, `GAD/MWD`. No rule
   construct expresses them.
3. **Should a "not required" document carry a DOC TYPE at all**, or only a
   scope-of-work verdict?
4. **338 documents no rule covers**, led by general-arrangement drawings and
   layout variants the required sheet does not list.

Phase 1's open question - what `NL` on a whole document group means - remains
open, and did **not** block this phase: DOC TYPE turned out not to depend on it.
