# API Contract — `/api/v1/mdr`

**Status.** Delivery Phase 2 established this contract and the persistence
behind it. **Delivery Phase 3 implements `upload`, `extract`, `automate` and
`summary`.** `download` still returns `501 Not Implemented`; it is Delivery
Phase 4.

The response fields are not aspirational. Each one is a column that already
exists — see `backend/app/infrastructure/persistence/models.py` and
`DATABASE_SCHEMA.md`. Nothing here is a field the next phase would have to
invent or break. Phase 3 added three optional fields to the summary
(`plant_code`, `extracted_at`, `failure_reason`); every Phase 2 field is
unchanged.

**Processing is synchronous.** `extract` and `automate` run the engine inside
the request and answer with the outcome; there is no job to poll. The real
~22k-row workbook takes seconds. The services are shaped so a job queue can be
put in front of them later if measurements ever call for one; nothing has.

---

## Namespace

```
/api/health                          operational, unversioned, forever
/api/v1/mdr/...                      the product API
```

**Why `/api/health` is not `/api/v1/health`.** Health is for a load balancer, a
deploy script and a monitor. Those consumers are not product clients, and making
them follow the product API's version when it moves would break monitoring for a
reason that has nothing to do with monitoring.

---

## Versioning policy

`v1` is the initial stable public API contract.

* **Do not create `v2` now.** Only a genuinely backward-incompatible change
  justifies one.
* Backward-compatible additions stay in v1 — a new endpoint, a new optional
  request field, a new response field.
* Breaking changes are a new major version — removing or renaming a response
  field, changing a field's type or meaning, making an optional request field
  required.
* **Versioning applies only at the public API boundary.** There is no
  `services/v1`, `domain/v1`, `engine/v1` or `repositories/v1`, and there will
  not be. `tests/integration/test_api_contract.py` asserts this.

---

## The workflow

```
   MDR workbook
        │
        ▼
   POST /api/v1/mdr/upload                    → mdr_id     [UPLOADED]
        │
        ▼
   POST /api/v1/mdr/{mdr_id}/extract                       [EXTRACTED]
        │
        ▼
   POST /api/v1/mdr/{mdr_id}/automate                      [AUTOMATED]
        │
        ├──▶ GET /api/v1/mdr/{mdr_id}/summary
        │
        └──▶ GET /api/v1/mdr/{mdr_id}/download → automated .xlsx
```

The endpoints are named after the five things the product does, so the workflow
is legible from the route table alone. They are action endpoints rather than
nested resources (`/mdr-submissions/{id}/processing-jobs`) because the workflow
is genuinely procedural. If extract and automate ever become long-running
background work, the job resource that follows will be added then, on evidence.

### Lifecycle

`domain.enums.lifecycle.SubmissionStatus`, unchanged since Phase 2:

```
UPLOADED ──extract──▶ EXTRACTED ──automate──▶ AUTOMATED
    │                     │
    └──────── FAILED ◀────┘        (failure_reason says which step, and why)
```

* Each step is accepted **only from the status directly before it**. Calling
  it from any other status — including calling it a second time — is refused
  with `409 Conflict` and changes nothing. This is what keeps
  `unique(submission_id, source_row)` and the one-summary-per-submission
  constraint from ever being tested by a repeat call.
* A step's writes happen in **one transaction**. If the workbook, the engine
  or PostgreSQL fails part-way, the transaction rolls back — no rows, no
  summary, no status change survive — and `FAILED` plus the reason are then
  written in a second, separate transaction. A submission is never `AUTOMATED`
  with a summary missing, or `EXTRACTED` with rows missing.
* **`FAILED` is terminal** in this phase. The uploaded file is kept, and the
  workbook is re-uploaded as a new submission, which leaves the failed one on
  record.
* There are no `EXTRACTING`/`AUTOMATING` states because nothing is ever
  observable in flight: processing is synchronous and completes inside the
  request.

### Plants

Every submission belongs to a plant, and `upload` takes the plant's `id`
explicitly. **Nothing creates a plant implicitly** — an upload naming an
unknown plant is a `404`, and the API does not assume QatarEnergy-TN or any
other plant is "the" plant.

A fresh database has no plants. Register one before the first upload, from
`backend/` with `MDR_DATABASE_URL` set (in the compose stack, prefix with
`docker compose exec backend`):

```bash
python - <<'PY'
from app.infrastructure.persistence.database import session_scope
from app.services.submission_service import register_plant
with session_scope() as session:
    print(register_plant(session, "QATARENERGY-TN", "QatarEnergy TN").id)
PY
```

The printed UUID is the `plant_id` for `upload`. `register_plant` is
idempotent by `code`. A plants endpoint is not part of v1 yet; adding one would
be a backward-compatible addition when a frontend needs it.

### Rule set

`automate` records **which rules produced the result**. Before running, it
locates the rules workbook exactly as the engine does (`MDR_RULES_WORKBOOK`,
else the first `.xlsx` in `data/rules/`), fingerprints it through
`services.rule_set_service`, and finds-or-creates the `rule_sets` row by
SHA-256 in the same transaction as the summary that points at it. Two
submissions automated under the same workbook share one `rule_sets` row; an
edited workbook produces a new one. See `RULE_VERSIONING.md`. With no rules
workbook present, `automate` answers `422` and leaves the submission
`EXTRACTED` — that is a deployment gap, not a fact about the submission.

### File storage

The uploaded bytes are kept on the local filesystem under
`settings.uploads_dir` — `MDR_UPLOADS_DIR`, else `<MDR_DATA_DIR>/uploads`,
which the compose stack mounts writable at `/data/uploads`:

```
<uploads_dir>/<mdr_id>/<original filename>
```

`mdr_submissions.stored_path` holds the key `<mdr_id>/<filename>`, never an
absolute path. The adapter (`infrastructure/storage/local.py`) never
overwrites — a key exists once — and never writes anywhere but under its root,
so an upload cannot land on a source workbook in `data/input/`, which stays
mounted read-only. The four calls it exposes (`put`, `resolve`, `exists`,
`delete`) are the surface an object store offers, which is what would replace
it; PostgreSQL stores metadata and the key only, never the bytes.

---

## `POST /api/v1/mdr/upload`

Create an MDR submission from an uploaded workbook.

**Request** — `multipart/form-data`

| Field | Type | Notes |
|---|---|---|
| `plant_id` | UUID | Which plant this submission belongs to. |
| `mdr_file` | file | The `.xlsx` MDR workbook. |

**Response** — `201 Created`

```json
{
  "mdr_id": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
  "submission_no": 9,
  "plant_id": "11111111-2222-3333-4444-555555555555",
  "status": "UPLOADED",
  "source_filename": "20260720-184-Transmittal Log (9) MDR.xlsx",
  "source_sha256": "e3b0c44298fc1c149afbf4c8996fb924…",
  "source_byte_size": 12345678,
  "uploaded_at": "2026-09-09T10:14:03.221Z"
}
```

`submission_no` is the business's `MDR #9` — the plant's ninth submission,
assigned server-side. `source_sha256` is the digest of the uploaded bytes, and
is what later makes it possible to say whether two submissions were the same
file.

**Lifecycle:** creates the submission at `UPLOADED`. Nothing has read the
workbook yet.

**Errors**

| Status | When |
|---|---|
| `400` | Empty, not `.xlsx`/`.xlsm`, not a workbook openpyxl can open, or no `QatarEnergy-TN` sheet with a recognisable header. Checked before anything is stored or recorded. |
| `404` | `plant_id` does not exist. Nothing is stored. |
| `413` | Larger than `MDR_MAX_UPLOAD_BYTES` (default 100 MiB). |
| `422` | A required form field is missing or malformed. |

---

## `POST /api/v1/mdr/{mdr_id}/extract`

Read the submission's workbook and persist its normalised rows.

The stored workbook is run through `MdrEngine.run()` — the existing Phase 1 +
2A pipeline, exactly as the CLI runs it — and every `DocumentRecord` it
produces becomes one `mdr_document_rows` row keyed by `source_row`, the Excel
row number. Identity, revision, latest-revision status and the `DOC TYPE`
verdict the engine already makes are stored; `DOC WITH REV`, `SOW` and
`DOC IDB COMPLETED STATUS` are left empty for `automate`; `CHECK STATUS` is
empty and stays so. A row without a `DOCUMENT NO.` produces no record, as in
the CLI. The workbook is opened read-only and is not modified.

**Request:** no body.

**Response** — `200 OK`

```json
{
  "mdr_id": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
  "status": "EXTRACTED",
  "source_sheet_name": "QatarEnergy-TN",
  "source_header_row": 5,
  "source_row_count": 21718,
  "extracted_at": "2026-09-09T10:15:40.118Z"
}
```

The three `source_*` fields are what the workbook turned out to contain — the
engine's own discovery, persisted. They are the operator's evidence that the
right sheet was read.

**Lifecycle:** `UPLOADED` → `EXTRACTED`, or → `FAILED` with a reason.

**Errors**

| Status | When |
|---|---|
| `404` | No submission with that id. |
| `409` | The submission is not `UPLOADED` — already extracted, automated, or `FAILED`. Nothing changes. |
| `422` | The reader cannot process the workbook (a required sheet or column is missing). **The submission is now `FAILED`** with the reader's reason; the uploaded file is kept. |
| `500` | A server-side failure — the stored file is missing, or PostgreSQL refused the write. **The submission is now `FAILED`** with the reason. |

---

## `POST /api/v1/mdr/{mdr_id}/automate`

Run the existing MDR automation engine over the submission.

Resolves `DOC WITH REV`, `DOC TYPE`, `DOC IS REQUIRED SOW` and
`DOC IDB COMPLETED STATUS`. `CHECK STATUS` is not evaluated — see below.

The stored workbook is run through `run_automation()` — the Phase 2D entry
point the CLI's `--excel` uses — and each `AutomationRow` is written onto the
row extraction stored for the same `source_row`, together with its provenance
(`doc_type_rule`, `sow_source`, `idb_source`). Before anything is written the
engine's rows are matched against the stored rows by `source_row`; a mismatch
fails the step rather than writing verdicts onto the wrong rows. The database
values are the engine's values verbatim — an empty SOW or an `UNMAPPED` IDB
status is stored as such, never repaired into a business value. The rule set
is registered and the processing summary written in the same transaction.

**Request:** no body.

**Response** — `200 OK`

```json
{
  "mdr_id": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
  "status": "AUTOMATED",
  "row_count": 21718,
  "rule_set": {
    "rule_set_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "version_label": "INPUT-KEYWORDS--FOR-MDR-TOOL-9f2c1a4b7e08",
    "source_filename": "INPUT-KEYWORDS  FOR MDR TOOL.xlsx",
    "content_sha256": "9f2c1a4b7e08…"
  },
  "automated_at": "2026-09-09T10:17:02.904Z"
}
```

**`rule_set` is not decoration.** It records which rules were in force when this
result was produced, so the result stays explainable after the rules workbook
changes. See `RULE_VERSIONING.md`.

**Lifecycle:** `EXTRACTED` → `AUTOMATED`, or → `FAILED` with a reason.

**Errors**

| Status | When |
|---|---|
| `404` | No submission with that id. |
| `409` | The submission is not `EXTRACTED` — not yet extracted, already automated, or `FAILED`. Nothing changes. |
| `422` | No rules workbook is available to fingerprint. The submission stays `EXTRACTED`. Or: the workbook cannot be read on re-open — **the submission is now `FAILED`**. |
| `500` | The engine raised, its rows did not match the extracted rows by `source_row`, or PostgreSQL refused the write. **The submission is now `FAILED`** with the reason; no verdict is written to any row. |

---

## `GET /api/v1/mdr/{mdr_id}/summary`

Return the processing summary for one submission.

**A read, and nothing else.** It opens no workbook and runs no engine; every
value is what `extract` and `automate` persisted. Asking twice returns the
same body and changes nothing. It answers for a submission in **any** status:
before `AUTOMATED` the counters are `0`, `rule_set` is `null` and `counts` is
`{}`; for a `FAILED` submission, `failure_reason` says which step stopped and
why.

**Response** — `200 OK`

```json
{
  "mdr_id": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
  "submission_no": 9,
  "plant_id": "11111111-2222-3333-4444-555555555555",
  "plant_code": "QATARENERGY-TN",
  "status": "AUTOMATED",
  "failure_reason": "",
  "source_filename": "20260720-184-Transmittal Log (9) MDR.xlsx",
  "uploaded_at": "2026-09-09T10:14:03.221Z",
  "extracted_at": "2026-09-09T10:15:40.118Z",
  "automated_at": "2026-09-09T10:17:02.904Z",

  "rule_set": { "…": "as above" },
  "engine_version": "0.2.0",

  "row_count": 21718,
  "doc_with_rev_populated": 21718,
  "doc_type_populated": 20004,
  "sow_populated": 19500,
  "sow_unresolved": 2218,
  "idb_populated": 8000,
  "idb_unmapped": 1714,
  "idb_manual_check_required": 11500,
  "check_status_populated": 0,

  "counts": {
    "doc_type_counts": { "P&ID": 900, "DATASHEET": 400 },
    "sow_counts":      { "YES": 19000, "NO": 500 },
    "idb_counts":      { "NO NEED TO CHECK": 8000 },
    "discovery":       { "qe_sheet": "QatarEnergy-TN", "qe_header_row": 5 }
  }
}
```

These are `AutomationRun.summary()` — the same numbers the CLI already prints,
persisted rather than recomputed.

Two counters need reading carefully:

* **`idb_manual_check_required`** counts required documents whose
  `DOC IDB COMPLETED STATUS` was deliberately left blank. Blank means *a person
  must still check this*, not *the automation failed*. It is counted separately
  so the blanks are visible as a decision.
* **`check_status_populated` is always `0`** and is returned anyway. `CHECK
  STATUS` cannot be evaluated until the received-document dump exists, and a
  consumer that can see the zero cannot mistake blank cells for a broken run.

**Errors**

| Status | When |
|---|---|
| `404` | No submission with that id. |

---

## `GET /api/v1/mdr/{mdr_id}/download`

Download the generated automated Excel workbook.

**Response** — `200 OK`,
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, as a
`Content-Disposition: attachment` byte stream. Not JSON, so no `response_model`.

The workbook is a copy of the uploaded file carrying every sheet it arrived
with, plus one added sheet named **`QatarEnergy-TN Automated`**. The writer
already exists (`infrastructure/excel/output_workbook.py`); serving it over HTTP
is Delivery Phase 4.

**Errors**

| Status | When |
|---|---|
| `404` | No submission with that id, or no generated workbook for it. |
| `409` | The submission has not been automated. |
| `501` | Delivery Phase 2 — not implemented. |

---

## `GET /api/health`

Operational. Unversioned. Proves the boundary works end to end without
involving MDR logic or the database.

```json
{ "status": "ok", "phase": "1" }
```

---

## Removed in Delivery Phase 2

**`GET /api/mdr/summary`** — the Phase 1 development convenience that ran the
engine over whichever workbook was configured and returned its summary.

Removed rather than kept alongside the versioned routes. It was an unversioned
product endpoint, which the versioning policy above does not allow; it had no
submission to belong to, since a summary is now a property of a submission; and
no client called it — the frontend calls only `/api/health`. The same capability
is still available locally through the CLI:

```bash
cd backend && python -m app.cli            # or: mdr-engine
```

Its eventual replacement is `GET /api/v1/mdr/{mdr_id}/summary`.

---

## What a route may and may not do

A route may resolve configuration, call a service, translate a domain error
into an HTTP status, and serialise a result.

A route may **not** contain SQL, parse a spreadsheet, decide a `DOC TYPE`, a
SOW or an IDB status, or hold a processing algorithm. Database access lives
behind the repository boundary; MDR rules live in `engine/`.
`tests/integration/test_api_contract.py` asserts both by inspecting the route
modules' imports and source.
