# API Architecture

**Status:** the boundary is established. Two endpoints exist. The rest of this
document describes *intent* — endpoints listed as future are deliberately not
built.

---

## 1. What the API is for

The API exists so the frontend can reach the MDR engine without containing any
MDR business rule. It is a boundary, not a layer of logic.

A route may:

- resolve configuration (which workbook?)
- call a service
- translate a domain error into an HTTP status
- serialise a result

A route may **not**:

- decide what the latest revision is
- normalise an identity
- interpret a status code
- read a spreadsheet directly

If a route ever needs to do one of those, the logic belongs in
`engine/` and the route calls it.

---

## 2. Shape

```
frontend  ──HTTP/JSON──▶  FastAPI app        backend/app/main.py
                              │
                              ├── /api/health          api/routes/health.py
                              └── /api/mdr/*           api/routes/mdr.py
                                      │
                                      ▼
                                  services              services/mdr_pipeline.py
                                      │
                                      ▼
                                  engine  ──▶  domain
```

All routes are mounted under `/api`. CORS origins come from `MDR_CORS_ORIGINS`
(default `http://localhost:5173`, the Vite dev server).

---

## 3. Implemented endpoints

### `GET /api/health`

Proves the boundary end to end without involving MDR logic at all.

```json
{ "status": "ok", "phase": "1" }
```

### `GET /api/mdr/summary`

Runs the Phase 1 pipeline over the configured workbook and returns its summary.
This adds no capability the CLI did not already have.

```json
{
  "workbook": "_20260720-184-Transmittal Log (9) MDR.xlsx",
  "discovery": { "qe_sheet": "QatarEnergy-TN", "qe_header_row": 5, "...": "..." },
  "summary":   { "document_rows": 21718, "latest_rows": 8161, "...": "..." }
}
```

`404` when no workbook is present in `data/input/current` and
`MDR_INPUT_WORKBOOK` is unset.

Synchronous by design. Phase 1 has no job queue; adding one before it is needed
would be building Phase 7 infrastructure speculatively. The run takes seconds on
the 22k-row workbook, which is acceptable for a single-user tool and is not
acceptable for the eventual multi-user one — see §5.

---

## 4. Future endpoints — NOT IMPLEMENTED

Listed so the boundary is understood, **not** as a build list. None of these
exists, and none should be created until its phase begins.

| Endpoint | Phase | Would need |
|---|---|---|
| `POST /api/mdr/upload` | 7 | Storage adapter, size/type limits |
| `POST /api/mdr/runs` | 7 | Job queue, run persistence |
| `GET /api/mdr/runs/{id}` | 7 | Run persistence |
| `GET /api/mdr/documents` | 7 | Pagination, filtering |
| `GET /api/mdr/exceptions` | 7 | Pagination |
| `GET /api/mdr/export/xlsx` | 5 | Excel writer (`engine`/`infrastructure`) |
| `POST /api/mdr/classify` | 2 | `engine/classification` |
| `GET /api/mdr/check-status` | 4 | `engine/received` |
| `POST /api/auth/*` | 7 | Authentication — none exists today |

**There is no authentication.** The API is unauthenticated and is suitable only
for local use. Authentication is Phase 7.

---

## 5. Decisions deferred

Recorded so they are made deliberately when the time comes, rather than by
accident:

1. **Long runs.** A 22k-row workbook takes seconds; a multi-user deployment
   will need a job queue rather than a synchronous request. Phase 7.
2. **Result size.** `mdr_phase1_result.json` is ~20 MB. A future
   `GET /api/mdr/documents` must paginate; it must not return the full result.
3. **Uploads.** Where an uploaded workbook is stored, and how it is validated
   before the engine touches it, is unresolved. `infrastructure/storage/` is
   the reserved home.
4. **Versioning.** No `/v1` prefix yet. Adding one is cheap now and expensive
   after the frontend ships.

---

## 6. Running it

```bash
cd backend
uvicorn app.main:app --reload      # http://127.0.0.1:8000
                                   # docs at /docs
```
