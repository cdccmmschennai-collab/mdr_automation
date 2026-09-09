# MDR Automation Tool

Deterministic engine that reads the MDR workbooks, normalises document
identities, resolves `TN FROM VENDORS` rows against `QatarEnergy-TN`, interprets
Status Codes, sequences revisions, determines the latest revision, and assigns
each document its `DOC TYPE` from the keyword rules workbook, its
`DOC IS REQUIRED SOW` scope verdict and its `DOC IDB COMPLETED STATUS`.

**Phases 1, 2A (DOC TYPE), 2B (DOC IS REQUIRED SOW), 2C
(DOC IDB COMPLETED STATUS) and 2D (Excel output) are complete and validated.
Phases 3–7 are not implemented** — no CHECK STATUS, no received-document
processing, no persistence, no API, no MDR frontend.

A run with `--excel` writes a copy of the uploaded workbook carrying every
sheet it arrived with, plus one added sheet named
**`QatarEnergy-TN Automated`** holding
`DOC WITH REV`, `DOC TYPE`, `DOC IS REQUIRED SOW` and
`DOC IDB COMPLETED STATUS`. `CHECK STATUS` is present as a caption and is
deliberately left empty — see [Not implemented](#not-implemented).

The vendor sheet is **not** consolidated into the document universe; the
processing universe is `QatarEnergy-TN` only
(`settings.vendor_consolidation_enabled` is `False`).

**The source workbooks are never modified.** Every workbook is opened
read-only, and a test asserts the file hash and mtime are unchanged by a run.

---

## Layout

```
mdr-automation/
├── backend/          MDR engine, domain, infrastructure, API
│   ├── app/
│   │   ├── domain/          MDR concepts — no framework, no I/O
│   │   ├── engine/          every business rule
│   │   ├── infrastructure/  Excel, filesystem, storage
│   │   ├── services/        orchestration
│   │   ├── api/             HTTP boundary
│   │   ├── core/            config, logging
│   │   └── cli.py
│   └── tests/        unit · integration · regression
├── frontend/         Vite + React + TypeScript scaffold
├── data/             input · reference · rules · output · fixtures (git-ignored)
├── docs/             architecture · business rules · phases
└── scripts/          workbook inspection, phase validation
```

Dependencies point one way only:
`frontend → api → services → engine → domain`, with infrastructure supporting
from the side. See
[`docs/architecture/SYSTEM_ARCHITECTURE.md`](docs/architecture/SYSTEM_ARCHITECTURE.md).

---

## Getting started

### Backend

```bash
cd backend
pip install -r requirements.txt

# Put a workbook in data/input/current/, then:
python -m app.cli --validate
python -m app.cli --workbook path/to.xlsx --outdir some/dir
```

Output lands in `data/output/latest/`:

| File | Contents |
|---|---|
| `mdr_phase1_result.json` | Full machine-readable result + summary |
| `documents.csv` | One row per QatarEnergy-TN document row |
| `vendor_rows.csv` | Vendor rows with match status/method |
| `exceptions.csv` | Rows needing human review |
| `validation_report.json` | Comparison vs the workbook's own L/NL column |
| `doc_type_report.json` | DOC TYPE vs the reference column AL, by root cause |
| `sow_report.json` | DOC IS REQUIRED SOW vs the reference column AM, by root cause |
| `idb_report.json` | DOC IDB COMPLETED STATUS vs the reference column AN, by root cause |

Each document record carries `document_identity`, `qatarenergy_document_no`,
`revision`, `issue_code`, `review_code`, `revision_type`, `revision_rank`,
`is_latest_revision`, `revision_status`, `match_status`, `match_method`,
`doc_type`, `doc_type_rule` and a `reason` explaining the decision.

### Validating a phase

```bash
python scripts/validate_phase.py --phase 1               # latest revision
python scripts/validate_phase.py --phase 2 --out data/output/latest   # DOC TYPE
python scripts/validate_phase.py --phase 2b --out data/output/latest  # SOW
python scripts/validate_phase.py --phase 2c --out data/output/latest  # IDB
```

### API

```bash
cd backend
uvicorn app.main:app --reload      # http://127.0.0.1:8000/docs
```

`GET /api/health` and `GET /api/mdr/summary`. **Unauthenticated — local use
only.**

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to the backend
npm run build
```

### Tests

```bash
cd backend
python -m pytest tests            # 611 tests (Phases 1, 2A, 2B and 2C)
```

Integration and regression suites skip automatically when the workbooks are
absent.

### Configuration

All paths resolve through `backend/app/core/config.py`. Copy `.env.example` to
`.env` to override. No credentials, secrets or production paths are in source.

---

## Results

**Phase 1 — latest revision**

- **0 genuine conflicts** against the workbook's own `LATEST/ NOT LATEST` column
- 97.58 % raw agreement; every disagreement has an identified root cause
- 79 rows where the engine is right and the manual workbook is stale
- 262 unlabelled rows the engine resolves — the manual backlog

**Phase 2A — DOC TYPE**

- **76.40 %** exact agreement (2,564 of 3,356) with column AL of the reference
  `QatarEnergy-TN WORKING` sheet
- The other 18,016 rows of that column hold scope-of-work and revision verdicts
  (`OLD REV NOT SOW`, `NOT SOW`, `OTHER`), which no keyword rule can produce
- Every mismatch is grouped by root cause; **no special case was added per
  mismatch** — see
  [classification-rules.md](docs/business-rules/classification-rules.md)

**Phase 2B — DOC IS REQUIRED SOW**

- **93.92 %** exact agreement with column AM over the 15,977 rows where both
  the resolver and the reference state a value
- The rules workbook and the working sheet flatly disagree over whether five
  SOW strings contain `/HIERARCHY`; reported, never patched — see
  [sow-rules.md](docs/business-rules/sow-rules.md)

**Phase 2C — DOC IDB COMPLETED STATUS**

- **97.54 %** agreement on whether an IDB check is due — the half of column AN
  the phase decides (15,586 of 15,979 accountable rows)
- **85.67 %** exact agreement with column AN; the gap is 1,876 rows whose
  recorded check outcome comes from the IDB folder and the FMTL, which no
  workbook here holds
- Only **2 rows** question the rules themselves; the rest trace to a Phase 2B
  rule gap or to the reference contradicting itself — see
  [idb-rules.md](docs/business-rules/idb-rules.md)

---

## Documentation

| Document | Contents |
|---|---|
| [SYSTEM_ARCHITECTURE](docs/architecture/SYSTEM_ARCHITECTURE.md) | Layering, dependency rules, module map |
| [DATA_FLOW](docs/architecture/DATA_FLOW.md) | End-to-end flow, with unimplemented stages marked |
| [API_ARCHITECTURE](docs/architecture/API_ARCHITECTURE.md) | The API boundary and what it may not do |
| [DECISION_LOG](docs/architecture/DECISION_LOG.md) | Every decision, with its evidence |
| [MDR_BUSINESS_RULES](docs/business-rules/MDR_BUSINESS_RULES.md) | Full Phase 1 evidence base |
| [document-identity](docs/business-rules/document-identity.md) · [revision-rules](docs/business-rules/revision-rules.md) · [classification-rules](docs/business-rules/classification-rules.md) · [sow-rules](docs/business-rules/sow-rules.md) · [idb-rules](docs/business-rules/idb-rules.md) | The implemented rules |
| [docs/phases/](docs/phases/) | Per-phase status |

The decision log records one candidate rule that was **tested and rejected**,
the open questions for the business, and the known warts that were deliberately
left unchanged.

---

## Not implemented

CHECK STATUS / received-document dump, vendor consolidation, persistence, the
HTTP API, the MDR frontend, the employee workflow, authentication, job queue,
deployment.

The Excel MDR output **is** implemented (Phase 2D). `CHECK STATUS` appears on
the `QatarEnergy-TN Automated` sheet as a caption with no values under it:
deciding it
needs the received-document dump, and `data/received/` is empty. A blank there
means *not evaluated* and must never be read as `NOT RECEIVED`.

The IDB **completion source** is also not implemented: the engine decides
whether an IDB check is due, and states `TO BE CHECK` where the outcome of that
check would come from the IDB folder and the FMTL.

No AI/LLM is used anywhere — every decision is deterministic and explainable.
