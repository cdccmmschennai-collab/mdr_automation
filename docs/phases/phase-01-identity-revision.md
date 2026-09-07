# Phase 1 — Document Identity, Matching and Revision

**Status:** ✅ COMPLETE and validated.

## Scope

- Workbook / sheet / column discovery by text, never by position
- Document identity normalisation and canonical keys
- `QatarEnergy-TN` ↔ `TN FROM VENDORS` matching
- Status Code interpretation, loaded from the workbook
- Revision parsing, banding and sequencing
- Latest-revision determination
- Machine-readable JSON/CSV output
- Validation against the workbook''s own `LATEST/ NOT LATEST` column

## Results

| Measure | Value |
|---|---|
| Document rows | 21,718 |
| Distinct documents | 8,284 |
| `LATEST` / `OLD` / `AS_BUILT` / `EXCEPTION` | 8,161 / 13,216 / 68 / 273 |
| Vendor rows matched | 111 / 596 (18.5 %) |
| Raw agreement vs ground truth | 97.58 % |
| **Genuine conflicts** | **0** |
| Tests | 120 passing |

## Where the rules live

- [`../business-rules/document-identity.md`](../business-rules/document-identity.md)
- [`../business-rules/revision-rules.md`](../business-rules/revision-rules.md)
- [`../business-rules/MDR_BUSINESS_RULES.md`](../business-rules/MDR_BUSINESS_RULES.md) — full evidence
- [`../architecture/DECISION_LOG.md`](../architecture/DECISION_LOG.md) — decisions D-01…D-12

## Where the code lives

`backend/app/engine/identity/`, `backend/app/engine/revision/`,
`backend/app/engine/validation/`, `backend/app/services/mdr_pipeline.py`

## Deliberately out of scope

DOC TYPE, SOW, IDB, CHECK STATUS, Excel output, frontend UI, deployment. No
AI/LLM is used — every decision is deterministic and explainable.
