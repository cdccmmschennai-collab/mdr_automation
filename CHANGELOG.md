# Changelog

All notable changes to this project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed — architecture refactor

Restructured the flat `src/mdr_engine/` package into a layered full-stack
project. **No Phase 1 business behaviour was changed**: the engine produces
byte-identical output on the reference workbook (21,718 document records and
596 vendor rows compare equal; the only difference in
`mdr_phase1_result.json` is the workbook's own absolute path, which moved).

- Split the flat engine package across `domain` / `engine` / `infrastructure` /
  `services` / `api` layers with a one-way dependency direction.
- Moved all Excel knowledge — sheet names, header captions, the workbook's own
  misspelling `ORGINATOR` — into `infrastructure/excel/mdr_workbook.py`. The
  engine now receives named `DocumentSourceRow` records instead of column
  indices. `openpyxl` is imported in exactly one module.
- Kept identity and revision as separate engine capabilities, each split into
  named modules (`normalisation`, `matching`, `grouping`; `parsing`,
  `eligibility`, `ranking`, `status_codes`). No `utils.py`/`helpers.py`.
- Centralised configuration in `core/config.py`; added `.env.example`. The
  production workbook filename is no longer hard-coded — it resolves from
  `MDR_INPUT_WORKBOOK` or by discovery in `data/input/current`.
- Reorganised data into `data/input|reference|rules|received|output|fixtures`
  and git-ignored production workbooks.
- Reorganised the 120 tests into `unit` / `integration` / `regression`, with
  real-world anomaly cases (numeric→alphabetic, Z/AS-BUILT, withdrawn,
  duplicate latest, stale workbook, no-LATEST groups) classified as regression
  coverage. Test count and assertions unchanged.

### Added

- FastAPI scaffold: `GET /api/health`, `GET /api/mdr/summary`. Unauthenticated,
  local use only.
- Vite + React + TypeScript frontend scaffold. One page, which checks the API is
  reachable. No MDR business logic, no dashboard.
- `docs/architecture/` — SYSTEM_ARCHITECTURE, DATA_FLOW, API_ARCHITECTURE,
  DECISION_LOG.
- `docs/business-rules/` — per-topic rule documents; future-phase files record
  only what is evidenced.
- `docs/phases/` — per-phase status, 01 through 07.
- `scripts/inspect_workbook.py`, `scripts/validate_phase.py`.
- CI workflows for backend tests and the frontend build.

### Not changed

Phases 2–7 remain unimplemented. No DOC TYPE, SOW, IDB, received-check, CHECK
STATUS, Excel output, employee workflow, authentication, job queue or
deployment code was introduced.

Two known warts were **documented rather than fixed**, because fixing them
risks changing validated Phase 1 behaviour — see DECISION_LOG A-05 and A-06.

---

## [0.1.0] — Phase 1

### Added

- Workbook/sheet/column discovery by header text, never by position.
- Document identity normalisation with conservative canonical keys.
- QatarEnergy-TN ↔ TN FROM VENDORS matching via a deterministic tier ladder;
  ambiguity matches nothing.
- Status Code interpretation loaded from the workbook's own sheet.
- Revision parsing, banding and sequencing; latest-revision determination.
- Validation against the workbook's own `LATEST/ NOT LATEST` column, with
  disagreements classified by root cause.
- JSON/CSV machine-readable output.
- 120 tests. 0 genuine conflicts against ground truth.
