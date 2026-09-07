# Document Identity Rules

**Status:** ✅ Implemented (Phase 1)
**Code:** `backend/app/engine/identity/`
**Evidence:** [MDR_BUSINESS_RULES.md](MDR_BUSINESS_RULES.md) §1, §5, §6

---

## The anchor

The QatarEnergy `DOCUMENT NO.` on the `QatarEnergy-TN` sheet is the anchor
identity. Everything else resolves against it.

Vendor rows on `TN FROM VENDORS` carry up to three candidate identifiers,
tried in this priority order:

1. `PROJECT DOCUMENT/ DRAWING NO.`
2. `PROJECT DOC NO.`
3. `Vendor Document No.`

The project-level identifiers are tried first because they are the fields that
actually carry the QatarEnergy document number; the vendor-internal number
usually does not.

---

## Normalisation

**Rule:** collapse case and separators. Nothing else.

```
'VEN-4391/MTY 1'  →  'VEN4391MTY1'
'4391 mty 1 g 0071'  →  '4391MTY1G0071'
```

**Rule:** never drop or invent a number segment.

`MEWTP-8-83-0001` and `MEWTP-8-83-0001-001` are **different documents**.
Dropping the trailing segment would merge them. Protected by
`tests/regression/test_revision_anomalies.py::TestSeparateDocumentsNotMerged`.

**Rule:** these cell values mean "no value" —
`""`, `-`, `--`, `N/A`, `NA`, `#N/A`, `NONE`, `NIL`.

A row with no document number is not a document row and is skipped (286 such
rows in the source workbook).

---

## The VEN- prefix

The workbooks write the same document as both `VEN-4391-MTY-…` and
`4391-MTY-…`. A canonical key with the leading `VEN` stripped (`alt_key`) is
kept alongside the full one, used only in the last matching tier.

---

## Matching tiers

A deterministic ladder. The first tier producing **exactly one** QatarEnergy
identity wins.

| Tier | Status | Basis |
|---|---|---|
| 1 | `EXACT` | byte-exact on the raw document number |
| 2 | `NORMALIZED_EXACT` | case/separator-insensitive canonical key |
| 3 | `ALTERNATIVE_IDENTIFIER` | VEN-prefix-tolerant key |
| — | `AMBIGUOUS` | a tier produced >1 candidate → **matches nothing** |
| — | `NOT_MATCHED` | no tier produced a candidate |
| — | `NO_IDENTIFIER` | the row carries no usable identifier |

**Rule:** uncertain matches are never made. There is no fuzzy matching, no
partial matching and no prefix matching. `4391-MTY-1` does **not** match
`4391-MTY-1-G-0071`.

**Rule:** ambiguity lists its candidates and matches nothing, so a human can
resolve it.

---

## Grouping

Rows sharing a canonical identity form one document group. Grouping is a single
function (`engine/identity/grouping.py`) used by both the ranking engine and the
validation layer, so the two group rows identically by construction.

---

## Observed results

| Measure | Value |
|---|---|
| Document rows processed | 21,718 |
| Distinct documents | 8,284 |
| Vendor rows | 596 |
| Vendor rows matched | 111 (18.5 %) |
| Ambiguous canonical keys | 1 (`4391-0-CV-00XX` vs `…00xx`) |

The low match rate is a business fact, not a defect — most vendor rows carry
vendor-internal identifiers that were never issued to QatarEnergy under a
project document number. See [DECISION_LOG.md](../architecture/DECISION_LOG.md)
D-06.
