# System Architecture

**Status:** Phases 1, 2A (DOC TYPE), 2B (DOC IS REQUIRED SOW), 2C
(DOC IDB COMPLETED STATUS) and 2D (the automated Excel output) are
implemented. Phase 3A/3B (received dump, CHECK STATUS) and the web application
are not; the packages reserved for them are empty.

Phase numbers here follow the engine scheme — see
[phase numbering](../phases/README.md) for the map to the other two.

---

## 1. The shape of the system

Four separable pieces, each independently useful:

| Piece | Location | Owns |
|---|---|---|
| **Frontend** | `frontend/` | Presentation, navigation, forms, upload UI, result display |
| **Backend API** | `backend/app/api/`, `backend/app/main.py` | HTTP boundary. Adapters only |
| **MDR engine** | `backend/app/engine/` | Every MDR business rule |
| **Infrastructure** | `backend/app/infrastructure/` | Excel, filesystem, storage |

The MDR engine is usable with nothing but a workbook path. The API and the
frontend are optional consumers of it, not prerequisites:

```python
from app.services.mdr_pipeline import MdrEngine
result = MdrEngine("data/input/current/log.xlsx").run()
```

---

## 2. Dependency direction

Dependencies point downward only. No arrow ever runs back up.

```
        Frontend  (React / TypeScript)
            │  HTTP + JSON
            ▼
        API  (FastAPI routers)                  backend/app/api/
            │
            ▼
        Services  (orchestration)               backend/app/services/
            │                    ╲
            ▼                     ╲
        MDR Engine  (rules)        ╲            backend/app/engine/
            │                       ▼
            ▼                    Infrastructure backend/app/infrastructure/
        Domain  (models, enums)                 backend/app/domain/
```

Enforced constraints:

| Rule | How it holds |
|---|---|
| The domain must not depend on FastAPI | `domain/` imports only the standard library |
| The domain must not depend on React | Nothing in `backend/` imports frontend code |
| The engine must not import frontend code | Same |
| Business logic must not depend on openpyxl | `openpyxl` is imported in exactly one module: `infrastructure/excel/workbook_reader.py` |
| Identity/revision logic must not depend on Excel cell coordinates | `engine/` receives named records (`DocumentSourceRow`), never row/column indices |
| The frontend must not implement MDR business rules | `frontend/src/services/` calls the API; it computes nothing |

There is one deliberate upward-looking import: `infrastructure/excel` imports
`clean` from `engine.identity.normalisation`. That function defines what a
workbook cell *means* as text (`"-"`, `"N/A"` and friends mean "no value"), and
that convention is a business fact, not a spreadsheet mechanic. The alternative
— a second copy in infrastructure — would let the two drift.

`domain/models/mdr_result.py` references `StatusCodeBook` (an engine type) for
typing only, under `TYPE_CHECKING`, so there is no runtime domain → engine
dependency.

---

## 3. Layer by layer

### Domain — `backend/app/domain/`

MDR concepts, not spreadsheet structures. Pure Python: no framework, no I/O.

```
domain/
├── models/
│   ├── document.py     DocumentIdentity, DocumentRecord, VendorRecord
│   ├── revision.py     Revision, RevisionBand, compare()
│   └── mdr_result.py   EngineResult (the aggregate one run produces)
└── enums/
    └── status_codes.py RevisionStatus, MatchStatus, ReviewCode, IssueCode
```

`ReviewCode` and `IssueCode` are *loaded from the workbook's own Status Codes
sheet*, never hard-coded. The domain owns their semantics
(`requires_resubmission`, `is_cancellation`, `is_as_built`); the engine owns
their loading.

### Engine — `backend/app/engine/`

Every MDR business rule. Phase 1 keeps identity and revision as separate
capabilities, deliberately not merged:

```
engine/
├── identity/          normalisation · matching · grouping
│   ├── normalisation.py   canonical keys; conservative — never drops segments
│   ├── matching.py        QE ↔ vendor tier ladder; ambiguity matches nothing
│   └── grouping.py        group rows by canonical identity
├── revision/          parsing · ranking · candidacy · status codes
│   ├── parsing.py         REV → banded, ordered Revision
│   ├── eligibility.py     what removes a row from latest candidacy
│   ├── ranking.py         latest determination within a group
│   └── status_codes.py    Status Codes sheet → ReviewCode / IssueCode
├── classification/    DOC TYPE from the keyword rules      (Phase 2A)
│   ├── rules.py           keyword syntax, rule model, precedence
│   └── classifier.py      number + title → DocumentClassification
├── validation/
│   ├── latest.py          comparison against the workbook's L/NL column
│   ├── doc_type.py        comparison against column AL, by root cause
│   ├── sow.py             comparison against column AM, by root cause
│   └── idb.py             comparison against column AN, by root cause
├── sow/               DOC IS REQUIRED SOW from the DOCUMENT TYPE sheet (Phase 2B)
│   ├── rules.py           the DOKAR → SOW table
│   └── resolver.py        DOC TYPE → SowRequirement
├── idb/               DOC IDB COMPLETED STATUS                      (Phase 2C)
│   ├── rules.py           the two rules column AN evidences
│   └── resolver.py        SowRequirement → IdbStatus
└── received/          (Phase 4 — empty)
```

There is no `utils.py`, `helpers.py`, `common.py` or `misc.py`, by design.

### Infrastructure — `backend/app/infrastructure/`

```
infrastructure/
├── excel/
│   ├── workbook_reader.py  generic read-only sheet/column discovery by header
│   ├── mdr_workbook.py     the MDR adapter: sheet names, header captions,
│   │                       named source rows
│   ├── rules_workbook.py   the keyword-rules adapter          (Phase 2A)
│   └── reference_workbook.py  the ground-truth working sheet  (Phase 2A)
├── filesystem/
│   └── artifact_writer.py  JSON/CSV serialisation mechanics
└── storage/                (Phase 7 — empty)
```

`mdr_workbook.py` is where the boundary actually sits. Everything the backend
knows about *where* MDR data lives in a spreadsheet — sheet names, the header
caption `LATEST/ NOT LATEST`, the workbook's own misspelling `ORGINATOR` — is
confined to that one file. It hands out `DocumentSourceRow` and
`VendorSourceRow`: plain records addressed by meaning.

Sheets are found by fuzzy name and columns by header text, never by position, so
a shifted column raises rather than silently corrupting the result.

### Services — `backend/app/services/`

Orchestration between the entry points and the engine. Holds no rule of its own
beyond assembly order.

- `mdr_pipeline.py` — `MdrEngine`: load → normalise → sequence → classify → emit
- `classification_service.py` — builds the DOC TYPE classifier from the rules
  workbook, and runs it against the reference sheet for validation
- `export_service.py` — which artefacts are published, and under what name

### API — `backend/app/api/`

Thin adapters. Two prefixes: `/api` for operational endpoints, `/api/v1` for
the product API.

| Endpoint | Purpose | Status |
|---|---|---|
| `GET /api/health` | Proves the boundary without touching MDR logic | works |
| `POST /api/v1/mdr/upload` | Create a submission from a workbook | works — Delivery Phase 3 |
| `POST /api/v1/mdr/{mdr_id}/extract` | Read and normalise it | works — Delivery Phase 3 |
| `POST /api/v1/mdr/{mdr_id}/automate` | Resolve the automation columns | works — Delivery Phase 3 |
| `GET /api/v1/mdr/{mdr_id}/summary` | What the run produced | works — Delivery Phase 3 |
| `GET /api/v1/mdr/{mdr_id}/download` | The automated workbook | works — Delivery Phase 4 |

Delivery Phase 2 fixed the paths, methods and response shapes; Delivery Phases
3 and 4 supplied the behaviour through `services/workflow_service.py`. No
handler touches the database, runs the engine or returns a fabricated result:
each calls one service function. `download` reuses the Phase 1 writer
(`export_service` → `infrastructure/excel/output_workbook.py`) over the
persisted rows. `GET /api/mdr/summary` was removed with the move to `/api/v1`.
See [API_ARCHITECTURE.md](API_ARCHITECTURE.md) and
[API_CONTRACT.md](API_CONTRACT.md).

### Persistence — `backend/app/infrastructure/persistence/`

The only code that knows SQL exists. PostgreSQL 16, SQLAlchemy 2.0, psycopg 3,
Alembic; five tables; one repository per aggregate; explicit transactions owned
by the caller. The engine and domain packages are forbidden from importing
SQLAlchemy by an architecture test — PostgreSQL was added *around* the MDR
processing, not into it. See [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) and
[RULE_VERSIONING.md](RULE_VERSIONING.md).

### Frontend — `frontend/`

A Vite + React + TypeScript scaffold that establishes the separation and
nothing more. It calls `/api/health`, renders the result, and implements no MDR
rule. There is no dashboard and no processing screen: those are Phase 7.

---

## 4. Data flow (implemented portion)

```
data/input/current/*.xlsx
        │
        ▼  MdrWorkbookReader            infrastructure/excel
   DocumentSourceRow[] · VendorSourceRow[] · status-code rows
        │
        ▼  MdrEngine._build_documents   services
   normalise_identity ─┐
   parse_revision      ├─ per row       engine/identity, engine/revision
   is_withdrawn        ┘
        │
        ▼  determine_latest             engine/revision/ranking
   LATEST · OLD · AS_BUILT · EXCEPTION
        │
        ▼  match_vendor_row             engine/identity/matching
   EngineResult
        │
        ├─▶ export_service ─▶ data/output/latest/*.json, *.csv
        ├─▶ validate_latest ─▶ validation_report.json
        └─▶ submission_service ─▶ repositories ─▶ PostgreSQL
```

The PostgreSQL branch is Delivery Phase 2: given an `AutomationRun` the engine
produced, `submission_service` stores the submission, its rows, its summary and
the rule set that produced them. No API endpoint drives it yet.

The conceptual end-to-end flow, including the unimplemented phases, is in
[DATA_FLOW.md](DATA_FLOW.md).

---

## 5. Configuration

Everything path- or environment-shaped resolves through
`backend/app/core/config.py`. Defaults are repository-relative; a deployment
supplies its own values via environment variables (see `.env.example`). No
credentials, secrets or production paths are in source.

| Variable | Default | Meaning |
|---|---|---|
| `MDR_DATA_DIR` | `<repo>/data` | Root of all data directories |
| `MDR_INPUT_WORKBOOK` | first `.xlsx` in `data/input/current` | Workbook to process |
| `MDR_LOG_LEVEL` | `INFO` | Root log level |
| `MDR_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `MDR_UPLOADS_DIR` | `<MDR_DATA_DIR>/uploads` | Where uploaded MDR workbooks are stored, one directory per submission (Delivery Phase 3) |
| `MDR_MAX_UPLOAD_BYTES` | `104857600` (100 MiB) | Largest upload the API accepts |

---

## 6. Source workbook safety

Every workbook is opened `read_only=True`. Nothing in the backend writes to a
source file. `tests/integration/test_phase1_workbook.py` asserts the SHA-256 and
mtime of the source workbook are unchanged by a full run.

---

## 7. Testing

```
backend/tests/
├── unit/         rules in isolation, no I/O
├── integration/  full pipeline over the real workbook (skips if absent)
├── regression/   specific real-world cases that must not regress
└── support/      shared builders; contains no tests
```

Run with `cd backend && python -m pytest tests`.
