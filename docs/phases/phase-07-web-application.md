# Phase 7 — Web Application

**Status:** ❌ NOT IMPLEMENTED — scaffold only.

## What exists

An architectural scaffold establishing frontend/backend separation, and nothing
more:

- `backend/app/main.py` — FastAPI app, CORS, two routers
- `GET /api/health` — proves the boundary; no MDR logic involved
- `GET /api/mdr/summary` — Phase 1 summary; adds no capability the CLI lacked
- `frontend/` — Vite + React + TypeScript, one page that calls `/api/health`

## What does not exist

- Authentication — **the API is unauthenticated and is local-use only**
- File upload
- Job queue / background runs
- Run persistence
- The employee workflow
- Result browsing, filtering, exception triage
- Production deployment

There is no dashboard and no processing screen. Building them before Phases 2–5
exist would mean building a UI for capabilities that do not exist.

## Deferred decisions

Recorded in [API_ARCHITECTURE.md](../architecture/API_ARCHITECTURE.md) §5:
long-running requests, result pagination (`mdr_phase1_result.json` is ~20 MB),
upload storage, and API versioning.

## Reserved locations

`backend/app/infrastructure/storage/` (empty), `frontend/src/features/` (empty),
`frontend/src/pages/`.
