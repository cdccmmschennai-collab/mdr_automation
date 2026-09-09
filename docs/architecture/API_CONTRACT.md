# API Contract — `/api/v1/mdr`

**Status.** Delivery Phase 2 establishes this contract and the persistence
behind it. **Every product endpoint below returns `501 Not Implemented` today.**
The paths, methods and response shapes are fixed and tested; the behaviour is
Delivery Phase 3 (upload, extract, automate, summary) and Delivery Phase 4
(download).

The response fields are not aspirational. Each one is a column that already
exists — see `backend/app/infrastructure/persistence/models.py` and
`DATABASE_SCHEMA.md`. Nothing here is a field the next phase would have to
invent or break.

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
| `400` | The file is not a readable `.xlsx`. |
| `404` | `plant_id` does not exist. |
| `413` | The upload exceeds the configured size limit. |
| `422` | A required form field is missing or malformed. |
| `501` | Delivery Phase 2 — not implemented. |

---

## `POST /api/v1/mdr/{mdr_id}/extract`

Read the submission's workbook and persist its normalised rows.

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
| `409` | The submission is not in a state that can be extracted. |
| `422` | The workbook has no recognisable `QatarEnergy-TN` sheet. |
| `501` | Delivery Phase 2 — not implemented. |

---

## `POST /api/v1/mdr/{mdr_id}/automate`

Run the existing MDR automation engine over the submission.

Resolves `DOC WITH REV`, `DOC TYPE`, `DOC IS REQUIRED SOW` and
`DOC IDB COMPLETED STATUS`. `CHECK STATUS` is not evaluated — see below.

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
| `409` | The submission has not been extracted. |
| `422` | No rules workbook is available to fingerprint. |
| `501` | Delivery Phase 2 — not implemented. |

---

## `GET /api/v1/mdr/{mdr_id}/summary`

Return the processing summary for one submission.

**Response** — `200 OK`

```json
{
  "mdr_id": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
  "submission_no": 9,
  "plant_id": "11111111-2222-3333-4444-555555555555",
  "status": "AUTOMATED",
  "source_filename": "20260720-184-Transmittal Log (9) MDR.xlsx",
  "uploaded_at": "2026-09-09T10:14:03.221Z",
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
| `409` | The submission has not been automated, so there is no summary. |
| `501` | Delivery Phase 2 — not implemented. |

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
