# Data Flow

The conceptual end-to-end MDR flow. **Only the first four stages exist.**
Everything below the line marked NOT IMPLEMENTED is a placeholder describing
intent, not behaviour.

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
  Classification       ❌ NOT IMPLEMENTED  (Phase 2)  engine/classification
        │
        ▼
  SOW / IDB            ❌ NOT IMPLEMENTED  (Phase 3)  engine/sow, engine/idb
        │
        ▼
  Received Check       ❌ NOT IMPLEMENTED  (Phase 4)  engine/received
        │
        ▼
  Validation           ⚠️  PARTIAL         engine/validation
        │
        ▼
  Output               ⚠️  PARTIAL         services/export_service
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

## Not implemented

### 4. Classification ❌ — Phase 2

Intended to assign `DOC TYPE` from the rules workbook
(`data/rules/INPUT-KEYWORDS FOR MDR TOOL.xlsx`) against the document title.

Nothing reads that workbook today. It was profiled during Phase 1 and loads
cleanly: `REQUIRED-KEY DOC.WORDS` (83 rows), `DOCUMENT TYPE` (22 types with
DOKAR codes and SOW strings), `NOT REQUIRED-KEY DOC.WORDS` (101 rows),
`FOLDER-UPDATE` (6). Note it already uses glob syntax (`*P&ID*LEGEND*`) and an
inline `or` (`LIGHTING LAYOUT or LIGHTNING LAYOUT`) that a parser will need to
handle.

**Package:** `engine/classification/` — empty.

### 5. SOW / IDB ❌ — Phase 3

Intended to determine `DOC IS REQUIRED SOW` and `DOC IDB COMPLETED STATUS`.

**Packages:** `engine/sow/`, `engine/idb/` — empty.

### 6. Received Check ❌ — Phase 4

Intended to reconcile against the received-document dump and derive
`CHECK STATUS`.

**Package:** `engine/received/` — empty. `data/received/` — empty.
There is no `check_status.py` in `domain/enums/`: writing one now would be
inventing a Phase 4 vocabulary with no evidence behind it.

### 7. Validation ⚠️ PARTIAL

`engine/validation/latest.py` exists and validates **one thing**: the
latest-revision decision, against the workbook's own `LATEST/ NOT LATEST`
column. Validation of classification, SOW, IDB and check status does not exist
because those stages do not exist.

### 8. Output ⚠️ PARTIAL

`services/export_service.py` writes the Phase 1 machine-readable result:

| Artefact | Contents |
|---|---|
| `mdr_phase1_result.json` | Full result + summary + discovery |
| `documents.csv` | One row per QatarEnergy-TN document row |
| `vendor_rows.csv` | Vendor rows with match status/method |
| `exceptions.csv` | Rows needing human review |
| `validation_report.json` | Comparison vs the workbook's own L/NL column |

**Excel MDR output generation is Phase 5 and does not exist.** The five MDR
columns (`DOC WITH REV`, `DOC TYPE`, `DOC IS REQUIRED SOW`,
`DOC IDB COMPLETED STATUS`, `CHECK STATUS`) found at AK–AO of the reference
workbook's `QatarEnergy-TN WORKING` sheet are Phase 2+ outputs. Phase 1
populates none of them.

---

## What is never written

The source workbooks. Every read is `read_only=True`, and an integration test
asserts the source file's SHA-256 and mtime are unchanged by a full run.
Output goes only to `data/output/latest/`.
