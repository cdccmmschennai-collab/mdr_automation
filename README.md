# MDR Automation Tool

Deterministic engine that reads the MDR workbooks, normalises document
identities, resolves `TN FROM VENDORS` rows against `QatarEnergy-TN`, interprets
Status Codes, sequences revisions, determines the latest revision, and assigns
each document its `DOC TYPE` from the keyword rules workbook.

**Phase 1 and Phase 2A (DOC TYPE) are complete and validated. Phases 2B–7 are
not implemented** — no SOW, no IDB, no CHECK STATUS, no received-document
processing, no Excel output, no MDR frontend.

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

Each document record carries `document_identity`, `qatarenergy_document_no`,
`revision`, `issue_code`, `review_code`, `revision_type`, `revision_rank`,
`is_latest_revision`, `revision_status`, `match_status`, `match_method`,
`doc_type`, `doc_type_rule` and a `reason` explaining the decision.

### Validating a phase

```bash
python scripts/validate_phase.py --phase 1               # latest revision
python scripts/validate_phase.py --phase 2 --out data/output/latest   # DOC TYPE
python scripts/validate_phase.py --phase 2b --out data/output/latest  # SOW
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
python -m pytest tests            # 240 tests (120 Phase 1 + 120 Phase 2A)
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

---

## Documentation

| Document | Contents |
|---|---|
| [SYSTEM_ARCHITECTURE](docs/architecture/SYSTEM_ARCHITECTURE.md) | Layering, dependency rules, module map |
| [DATA_FLOW](docs/architecture/DATA_FLOW.md) | End-to-end flow, with unimplemented stages marked |
| [API_ARCHITECTURE](docs/architecture/API_ARCHITECTURE.md) | The API boundary and what it may not do |
| [DECISION_LOG](docs/architecture/DECISION_LOG.md) | Every decision, with its evidence |
| [MDR_BUSINESS_RULES](docs/business-rules/MDR_BUSINESS_RULES.md) | Full Phase 1 evidence base |
| [document-identity](docs/business-rules/document-identity.md) · [revision-rules](docs/business-rules/revision-rules.md) · [classification-rules](docs/business-rules/classification-rules.md) | The implemented rules |
| [docs/phases/](docs/phases/) | Per-phase status |

The decision log records one candidate rule that was **tested and rejected**,
the open questions for the business, and the known warts that were deliberately
left unchanged.

---

## Not implemented

SOW, IDB, CHECK STATUS / received-document dump, vendor consolidation, Excel
MDR output, the MDR frontend, the employee workflow, authentication, job queue,
deployment.

No AI/LLM is used anywhere — every decision is deterministic and explainable.
