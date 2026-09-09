# Data Flow

The conceptual end-to-end MDR flow. Every stage exists except **Received
Check**, which is a placeholder describing intent, not behaviour.

---

## The full flow

```
  Input Workbooks
        │
        ▼
  Ingestion            ✅ IMPLEMENTED   infrastructure/excel
        │
        ▼
  Identity             ✅ IMPLEMENTED   engine/identity
        │
        ▼
  Revision             ✅ IMPLEMENTED   engine/revision
        │
────────┼──────────────────────────────────────────── Phase 1 ends here
        ▼
  Classification       ✅ IMPLEMENTED   engine/classification   (Phase 2A)
        │              DOC TYPE only
────────┼──────────────────────────────────────────── Phase 2A ends here
        ▼
  SOW                  ✅ IMPLEMENTED   engine/sow              (Phase 2B)
        │
        ▼
  IDB                  ✅ IMPLEMENTED   engine/idb              (Phase 2C)
        │              requirement only; the check outcome is an input
        │
        ▼
  Received Check       ❌ NOT IMPLEMENTED  (Phase 4)  engine/received
        │
        ▼
  Validation           ⚠️  PARTIAL         engine/validation
        │
        ▼
  Output               ✅ IMPLEMENTED   services/export_service (Phase 2D)
        │              JSON + CSV, and the automated workbook
        ▼
  Automated .xlsx      ✅ IMPLEMENTED   infrastructure/excel/output_workbook
                       adds 'QatarEnergy-TN Automated'
```

---

## Implemented stages

### 1. Ingestion ✅

**Where:** `infrastructure/excel/workbook_reader.py`, `mdr_workbook.py`

Opens the workbook `read_only=True`. Locates sheets by fuzzy name and the header
row by scoring the first 15 rows against expected captions; resolves columns by
header text, never by position. A missing required column raises
`ColumnNotFoundError` rather than silently producing wrong output.

**In:** an `.xlsx` path
**Out:** `DocumentSourceRow[]`, `VendorSourceRow[]`, raw Status Codes rows, and
a `SheetDiscovery` record per sheet

Three sheets are consumed: `QatarEnergy-TN`, `TN FROM VENDORS`, `Status Codes`.
`VENDOR LIST` exists but is unused in Phase 1. A `VENDOR DETAILS` sheet is named
in the brief but **does not exist** in either workbook.

### 2. Identity ✅

**Where:** `engine/identity/`

- **Normalisation** — collapse case and separators to a canonical key
  (`VEN-4391/MTY 1` → `VEN4391MTY1`). Deliberately conservative: number
  segments are never dropped or invented, because that would merge genuinely
  distinct documents.
- **Matching** — a deterministic tier ladder resolving vendor rows against
  QatarEnergy documents: exact → normalised → VEN-prefix-tolerant. A tier
  yielding more than one candidate records `AMBIGUOUS` and matches **nothing**.
- **Grouping** — rows sharing a canonical identity form one document group.

**In:** source rows
**Out:** `DocumentRecord[]` carrying a canonical identity; `VendorRecord[]`
carrying a match status, method and reason

### 3. Revision ✅

**Where:** `engine/revision/`

- **Parsing** — REV → a banded, ordered `Revision`. Bands:
  `UNPARSEABLE < NUMERIC < ALPHABETIC < AS_BUILT`.
- **Status Code interpretation** — the Status Codes sheet is *loaded*, not
  hard-coded, so a revised sheet changes behaviour without a code change.
- **Eligibility** — withdrawn submissions leave latest candidacy; renumbering
  remarks are recorded but explicitly do **not**.
- **Ranking** — the eligible row with the highest `(band, ordinal)` in each
  group is `LATEST`. Ties produce an exception, never a guess.

**Out:** every row carries `revision_status` ∈ {`LATEST`, `OLD`, `AS_BUILT`,
`EXCEPTION`} plus a `reason` explaining the decision.

See [DECISION_LOG.md](DECISION_LOG.md) for the evidence behind each rule.

---

### 4. Classification ✅ — Phase 2A

**In:** `document_number` and `document_title` — nothing else.
**Rules:** `data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`, sheets
`REQUIRED-KEY DOC.WORDS` (82 rules) and `NOT REQUIRED-KEY DOC.WORDS` (100).
The `DOCUMENT TYPE` and `FOLDER-UPDATE` sheets are **not read** — they carry
SOW strings and folder notes, which are later phases.

Keywords match as substrings; `*` is a wildcard, ` or ` is alternation, and a
run of X's in a document-number keyword means digits. Required rules outrank
not-required ones, then workbook row order decides. Every matching rule is
retained, not just the winner.

**Out:** `doc_type` and `doc_type_rule` on every `DocumentRecord`, empty when
no rule covers the document. The classifier never guesses.

**Package:** `engine/classification/` — `rules.py`, `classifier.py`.
Rules and precedence: [../business-rules/classification-rules.md](../business-rules/classification-rules.md).

---

### 5. SOW ✅ — Phase 2B

`DOC IS REQUIRED SOW` from the DOC TYPE, using the rules workbook's
`DOCUMENT TYPE` sheet (22 DOKAR → SOW rows) plus the two self-stating
verdicts `OLD REV NOT SOW` and `NOT SOW`, which resolve to `NO`.

**Package:** `engine/sow/`. **Input:** a DOC TYPE, and nothing else.
Rules and precedence: [../business-rules/sow-rules.md](../business-rules/sow-rules.md).

### 6. IDB ✅ — Phase 2C

`DOC IDB COMPLETED STATUS` from the SOW verdict. Out of scope resolves to
`NO NEED TO CHECK`; in scope resolves to the outcome a completion source
states, or `TO BE CHECK` when none has. An unresolved SOW yields `UNMAPPED`.

**Package:** `engine/idb/`. **Input:** a `SowRequirement`, plus an optional
recorded check outcome. **Not implemented:** the completion source itself —
the IDB folder and the FMTL are not in the repository, so every in-scope
document currently resolves to `TO BE CHECK`.
Rules and evidence: [../business-rules/idb-rules.md](../business-rules/idb-rules.md).

---

## Not implemented

### 7. Received Check ❌ — Phase 3A/3B

Intended to reconcile against the received-document dump and derive
`CHECK STATUS`.

**Package:** `engine/received/` — empty. `data/received/` — empty.
There is no `check_status.py` in `domain/enums/`: writing one now would be
inventing a Phase 4 vocabulary with no evidence behind it.

### 8. Validation ⚠️ PARTIAL

Two things are validated, each against a manually maintained column:

| Module | Validates | Against |
|---|---|---|
| `engine/validation/latest.py` | latest-revision decision | `LATEST/ NOT LATEST` |
| `engine/validation/doc_type.py` | DOC TYPE | column AL of `QatarEnergy-TN WORKING` |
| `engine/validation/sow.py` | DOC IS REQUIRED SOW | column AM of the same sheet |
| `engine/validation/idb.py` | DOC IDB COMPLETED STATUS | column AN of the same sheet |

Validation of check status does not exist because that stage does not exist.

### 9. Output ✅

`services/export_service.py` writes the machine-readable result:

| Artefact | Contents |
|---|---|
| `mdr_phase1_result.json` | Full result + summary + discovery |
| `documents.csv` | One row per QatarEnergy-TN document row, `doc_type` included |
| `vendor_rows.csv` | Vendor rows with match status/method |
| `exceptions.csv` | Rows needing human review |
| `validation_report.json` | Comparison vs the workbook's own L/NL column |
| `doc_type_report.json` | Comparison vs column AL, with mismatch causes |
| `sow_report.json` | Comparison vs column AM, with mismatch causes |
| `idb_report.json` | Comparison vs column AN, with mismatch causes |

**Excel MDR output generation is Phase 2D and is implemented.** A run with
`--excel` writes `<source stem>_MDR_AUTOMATED.xlsx`: a copy of the uploaded
workbook carrying every sheet it arrived with, plus one added sheet named
`QatarEnergy-TN Automated`.

Of the five MDR columns at AK–AO of the reference workbook's
`QatarEnergy-TN WORKING` sheet, four are written — `DOC WITH REV`, `DOC TYPE`,
`DOC IS REQUIRED SOW` and `DOC IDB COMPLETED STATUS`. `CHECK STATUS` is
written as a caption with no values under it, because the stage that would
decide it does not exist. A blank there means *not evaluated*, never
`NOT RECEIVED`.

The writer is `infrastructure/excel/output_workbook.py`, the only module in the
backend that opens a workbook for writing. It inserts the five columns before
`QATARENERGY SIGNED / NOT SIGNED` rather than appending them, and carries the
column widths, merged ranges, conditional formats, data validations, auto-filter
and frozen pane across the insertion.

---

## What is never written

The source workbooks. Every read is `read_only=True`, and an integration test
asserts the source file's SHA-256 and mtime are unchanged by a full run.
Output goes only to `data/output/latest/`.
