# API Architecture

**Status:** the boundary is established and versioned. `GET /api/health` works;
the five `/api/v1/mdr` product endpoints are registered with their full
contracts and return `501 Not Implemented` until Delivery Phase 3 and 4.

The endpoint-by-endpoint contract lives in **[API_CONTRACT.md](API_CONTRACT.md)**.
This document is the shape and the rules; that one is the request/response
detail.

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
                              │      (operational, unversioned)
                              │
                              └── /api/v1/mdr/*        api/routes/mdr_v1.py
                                      │                api/schemas/mdr.py
                                      ▼
                                  services              services/*.py
                                   ╱      ╲
                                  ▼        ▼
                              engine    repositories   infrastructure/persistence
                                 │           │
                                 ▼           ▼
                              domain     PostgreSQL
```

Two prefixes, and the difference is deliberate:

* **`/api`** — operational. `/api/health` is for a load balancer, a deploy
  script and a monitor. Those consumers are not product clients and must not be
  made to follow the product API's version when it moves.
* **`/api/v1`** — the product API.

CORS origins come from `MDR_CORS_ORIGINS` (default `http://localhost:5173`, the
Vite dev server).

---

## 3. The route table

```
GET  /api/health                          works
POST /api/v1/mdr/upload                   501 — Delivery Phase 3
POST /api/v1/mdr/{mdr_id}/extract         501 — Delivery Phase 3
POST /api/v1/mdr/{mdr_id}/automate        501 — Delivery Phase 3
GET  /api/v1/mdr/{mdr_id}/summary         501 — Delivery Phase 3
GET  /api/v1/mdr/{mdr_id}/download        501 — Delivery Phase 4
```

That is the whole surface;
`tests/integration/test_api_contract.py` asserts the live application serves
exactly these and nothing else.

The five are named after the five things the product does — upload, extract,
automate, summary, download — so the workflow is legible from the route table
alone. They are action endpoints rather than nested resources
(`/mdr-submissions/{id}/processing-jobs`) because the workflow is genuinely
procedural. If extract and automate become long-running background work, the
job resource that follows will be added then, on evidence.

**The 501s are honest, not placeholders that pretend.** No handler touches the
database, runs the engine, or returns a fabricated result. Their response
schemas are declared and appear in `/docs`, so the contract is fixed now; the
behaviour is not claimed.

### Removed in Delivery Phase 2

`GET /api/mdr/summary` — an unversioned product endpoint with no submission to
belong to, called by nothing. See API_CONTRACT.md for the full reasoning. The
capability remains in the CLI (`python -m app.cli`).

---

## 4. Versioning policy

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
  not be — the internal architecture is version-independent, and a test asserts
  it.
* Operational endpoints are never versioned.

**There is no authentication.** The API is unauthenticated and is suitable only
for local use. Authentication is a later delivery phase.

---

## 5. Decisions deferred

Recorded so they are made deliberately when the time comes, rather than by
accident:

1. **Long runs.** A 22k-row workbook takes seconds; a multi-user deployment
   will need a job queue rather than a synchronous request. `POST
   /api/v1/mdr/{id}/automate` is the endpoint this will hit first.
2. **Result size.** A submission holds ~22k rows. Any future endpoint returning
   them must paginate; `DocumentRowRepository.for_submission` already takes
   `limit`/`offset` so the eventual endpoint has no excuse not to.
3. **Uploads.** Where an uploaded workbook is stored, and how it is validated
   before the engine touches it, is unresolved. `infrastructure/storage/` is
   the reserved home, and `mdr_submissions.stored_path` is the column waiting
   for the answer.
4. ~~**Versioning.**~~ **Resolved in Delivery Phase 2** — see §4. The product
   API is `/api/v1`; health stays unversioned.
5. **Re-running a submission.** `mdr_processing_summaries` is unique on
   `submission_id`, so a submission has one run. Re-running under a new rule
   set means dropping that one constraint; the table is already shaped as the
   run history that would become. Not decided, because nothing needs it yet.

---

## 6. Running it

```bash
cd backend
uvicorn app.main:app --reload      # http://127.0.0.1:8000
                                   # docs at /docs
```

The API starts with no database configured — the engine, the CLI and the Excel
writer need none. To use persistence, set `MDR_DATABASE_URL` (see
`.env.example`) and apply the migrations:

```bash
cd backend
alembic upgrade head
```
