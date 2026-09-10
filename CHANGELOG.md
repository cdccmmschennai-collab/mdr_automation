# Changelog

All notable changes to this project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — Delivery Phase 3: upload → extract → automate → summary

The `/api/v1/mdr` workflow now works end to end against PostgreSQL, running
the existing engine unchanged. `download` remains Delivery Phase 4 (`501`).

- `services/workflow_service.py` — the one module the routes call. One
  function per step, each owning one transaction: `upload_workbook`,
  `extract_submission`, `automate_submission`, `summarise_submission`.
  Extraction is `MdrEngine.run()`; automation is `run_automation()`; the rows
  stored are the engine's `DocumentRecord`s and `AutomationRow`s, matched by
  `source_row`, never by position. No MDR rule lives in it.
- `infrastructure/storage/local.py` — uploaded workbooks under
  `MDR_UPLOADS_DIR` (default `<data>/uploads`; `/data/uploads` in compose) as
  `<mdr_id>/<filename>`; the key, not the path, is what `stored_path` holds.
  Never overwrites; never writes outside its root; four calls (`put`,
  `resolve`, `exists`, `delete`) so an object store can replace it.
- Upload validation before anything is stored or recorded: empty, extension,
  size (`MDR_MAX_UPLOAD_BYTES`, 100 MiB), openable, and a `QatarEnergy-TN`
  sheet with a recognisable header — via the reader's own discovery
  (`probe_document_sheet`), so what upload accepts is what extract can read.
- Lifecycle is the Phase 2 enum unchanged: `UPLOADED → EXTRACTED → AUTOMATED`,
  `FAILED` from either step with `failure_reason`. Each step is accepted only
  from the status before it (`409` otherwise), a step's writes are one
  transaction, and `FAILED` is recorded in a second transaction after the
  first has rolled back. `FAILED` is terminal: re-upload.
- Plants are explicit: `upload` takes `plant_id`; an unknown plant is `404`
  and nothing creates one implicitly. API_CONTRACT.md documents registering
  the first plant.
- `automate` fingerprints the rules workbook and finds-or-creates the
  `rule_sets` row by digest in the same transaction as the summary.
- `SummaryResponse` gains `plant_code`, `extracted_at`, `failure_reason`
  (all optional/defaulted); `summary` answers in any status and runs nothing.
- `DocumentRowRepository.update_automation` / `source_rows_for`;
  `SubmissionRepository.add` accepts a caller-supplied id.
- Tests: `tests/api/` (workflow over HTTP on the nine-row fixture, and the
  real ~22k-row workbook end to end against `run_automation`), storage and
  settings unit tests. The four Phase 2 "returns 501" assertions for the now
  implemented endpoints were replaced by their Phase 3 behaviour; every other
  existing test is unchanged.

### Changed

- `fastapi>=0.110,<0.137`: from 0.137 `include_router` registers a nested
  `_IncludedRouter` instead of flattening routes into `app.routes`, which the
  route-introspection tests read.
- `docker-compose.yml`: project name `mdr-automation`; containers
  `mdr-automation-{frontend,backend,postgres}`; ports `3200:3000` and
  `8200:8000`; PostgreSQL internal only; `./data/uploads` mounted writable.

### Added — Delivery Phase 2: PostgreSQL persistence and the `/api/v1` contract

*Delivery* Phase 2 — the PostgreSQL row in `docs/phases/README.md`. Not the
document phase of the same number, which is DOC TYPE classification and was
finished long ago.

Results now survive the run that produced them, and stay explainable after the
rules change.

**Persistence.** PostgreSQL 16, SQLAlchemy 2.0, psycopg 3, Alembic. Five
tables: `plants`, `rule_sets`, `mdr_submissions`, `mdr_document_rows`,
`mdr_processing_summaries` — see `docs/architecture/DATABASE_SCHEMA.md`. Small
on purpose: the workbook has ~70 columns and remains the authority for the ones
the product does not query.

- `infrastructure/persistence/` — the only code in the backend that knows SQL
  exists. `models.py`, `database.py` (engine, sessions, explicit transactions),
  and one repository per aggregate. No repository commits and none swallows a
  database error; the caller owns the transaction, so a submission's rows and
  its summary are written atomically or not at all.
- `services/submission_service.py` — composes those repositories into one unit
  of work. It persists an `AutomationRun` the existing engine produced; it does
  not upload, extract, automate or download anything.
- `alembic/` — the schema's only source. There is no `create_all` anywhere,
  including in the tests, which build their throwaway database by running the
  migrations. A test asserts autogenerate finds no difference between the
  migrated database and the models.

**Rule-set versioning.** `services/rule_set_service.py` fingerprints the rules
workbook — SHA-256 of its bytes, plus the rule counts each sheet yields, read
through the existing `RulesWorkbookReader`. `mdr_processing_summaries.rule_set_id`
is `NOT NULL` with `ON DELETE RESTRICT`: a result that cannot name its rules
cannot be stored, and rules a result points at cannot be deleted. Introducing
Rule Set B therefore cannot make MDR #6 appear to have been processed under it.

The rule *content* is not copied into PostgreSQL — that would make the database
a second home for rules the business maintains in Excel, and the copy could go
stale without anything failing. The limit is stated in
`docs/architecture/RULE_VERSIONING.md`: the database says *which* workbook, by
digest; it cannot reconstruct one nobody kept. Keep the old rules workbooks.

**Historical submissions are independent by construction.** `submission_no` is
unique per plant (`MDR #6` is *this plant's* sixth), no repository has a
`get_latest()`, no row is updated when a newer submission arrives, and every
query into `mdr_document_rows` is scoped by `submission_id`.

**API structure.** The product API is now `/api/v1/mdr`:

    POST /api/v1/mdr/upload
    POST /api/v1/mdr/{mdr_id}/extract
    POST /api/v1/mdr/{mdr_id}/automate
    GET  /api/v1/mdr/{mdr_id}/summary
    GET  /api/v1/mdr/{mdr_id}/download

**All five return `501 Not Implemented`.** Delivery Phase 2 fixes the paths,
methods and response shapes; the behaviour is Delivery Phase 3 and 4. No handler
touches the database, runs the engine or returns a fabricated result. Response
schemas are declared and appear in `/docs`, so the contract is real —
`docs/architecture/API_CONTRACT.md`.

`GET /api/health` stays unversioned and always will: it is for a load balancer
and a monitor, which are not product clients and must not follow the product
API's version. Versioning applies only at the boundary — there is no
`services/v1`, `domain/v1` or `engine/v1`, and a test asserts it.

**The engine is untouched.** PostgreSQL was added *around* the existing MDR
processing, not into it. The engine and domain packages are forbidden from
importing SQLAlchemy by an architecture test, the Excel writer is unchanged, the
CLI works as before, and the 803 existing tests are green. An end-to-end test
runs the real 21,718-row workbook through the real engine into PostgreSQL and
checks the stored rows against what the engine said — including that the source
workbook's digest is unchanged afterwards.

### Removed

- **`GET /api/mdr/summary`.** An unversioned product endpoint that ran the
  engine over whichever workbook was configured. It had no submission to belong
  to — a summary is now a property of a submission — and no client called it;
  the frontend calls only `/api/health`. The same capability remains in the CLI
  (`python -m app.cli`), and its replacement is
  `GET /api/v1/mdr/{mdr_id}/summary`. `backend/app/api/routes/mdr.py` is gone
  with it.

### Added — Phase 2D: the automated Excel output

A run now produces the employee-facing workbook: a copy of the uploaded file
carrying every sheet it arrived with, plus one added sheet named
**`QatarEnergy-TN Automated`**. This supersedes the "nothing writes an `.xlsx`"
note in the Phase 2C entry below.

- `infrastructure/excel/output_workbook.py` — `AutomatedWorkbookWriter`, the
  only module in the backend that opens a workbook for writing. The five
  columns are *inserted* before `QATARENERGY SIGNED / NOT SIGNED` (AK–AO on the
  real workbook), carrying column widths, merged ranges, conditional formats,
  data validations, the auto-filter and the frozen pane across the insertion —
  none of which `Worksheet.insert_cols` moves on its own.
- `services/automation_service.py` — chains Phases 1, 2A, 2B and 2C into one
  `AutomationRow` per source row. Holds no rule and imports no openpyxl.
- `domain/models/automation.py` — the five captions, and a
  `CheckStatusNotEvaluated` guard so `CHECK STATUS` cannot start being filled
  by accident.
- `export_automated_workbook`, `export_automation_rows` and `mdr-engine --excel`.

`DOC WITH REV`, `DOC TYPE`, `DOC IS REQUIRED SOW` and
`DOC IDB COMPLETED STATUS` are written. `CHECK STATUS` is a caption with no
values under it: the received-document dump does not exist, so a blank there
means *not evaluated* and never `NOT RECEIVED`.

The source workbook is never modified — it is copied in memory and saved
elsewhere, a destination resolving to the source is refused by both the writer
and the export service, and tests assert its SHA-256, size and mtime are
unchanged by a full run.

### Changed

- The automated sheet name `QatarEnergy-TN Automated` is now pinned by a test
  as a literal, rather than only being asserted through the constant that
  defines it. It is the product's download contract: the Phase 4 export
  endpoint, the frontend and the employee all find the results under it.
- `docs/phases/README.md` — new: the map between the three phase-numbering
  schemes in use (engine, document filenames, delivery plan), which collide on
  "Phase 4" and "Phase 5".

### Added — Phase 2C: DOC IDB COMPLETED STATUS

The scope verdict decided by Phase 2B now resolves to an IDB status.
**IDB only** — CHECK STATUS and the received dump are unimplemented. (At the
time of this change nothing wrote an `.xlsx`; Phase 2D above now does.)

- `engine/idb/` — `rules.py` (the two rules reverse-engineered from column AN,
  plus the scope and outcome readers) and `resolver.py` (`IdbResolver`).
  Neither opens a file: no sheet of the rules workbook states an IDB status,
  so the rules are stated in code with their evidence cited.
- `domain/models/idb.py` — `IdbStatus`. `check_required` is three-valued, so
  an unresolved document cannot read as one needing no check. The vocabulary
  is the nine values column AN actually carries, plus `UNMAPPED`.
- `engine/validation/idb.py` — comparison against column AN of
  `QatarEnergy-TN WORKING`, with an eight-way mismatch taxonomy and two rates:
  exact agreement and "is a check due?" agreement.
- `services/idb_service.py`, `export_idb_report`, and
  `scripts/validate_phase.py --phase 2c`.
- `ReferenceRow.reference_idb` — column AN, read as the expected value only.

**Out of scope means no check is due** — `NO NEED TO CHECK` on 18,704 of the
18,706 rows whose SOW reads `NO`, exceptionless through every other column,
including all 300 cancelled submissions. All 9,934 `OLD REV NOT SOW` rows are
covered by it, which is the only route by which revision affects IDB: the
resolver has no revision, latest or cancellation input, and adding one would be
wrong — 107 of the 127 rows that are in scope but not the latest revision read
`COMPLETED`.

**In scope means a check is due, and its outcome is an input.** `COMPLETED`,
`PENDING` and the rest record a check performed against the IDB folder and the
FMTL; no column in the transmittal log predicts them, and the values track
sheet position rather than any document property. The resolver accepts a
recorded outcome and states `TO BE CHECK` when none is supplied — never a
guessed `COMPLETED`.

97.54% agreement on whether a check is due (15,586 of 15,979 accountable rows);
85.67% exact agreement with column AN. Only **2** rows question the rules
themselves — both are rows where the working sheet contradicts its own column
AM. 5,384 mismatches trace to the Phase 2B rule gap, 1,876 to the missing
completion source, and 391 to Phase 2B's already-documented column AM override.
No per-row exception was added. See
`docs/business-rules/idb-rules.md` for the value-by-value table and the ten
open questions — chief among them where the completion outcome should come
from.

### Added — Phase 2B: DOC IS REQUIRED SOW

The DOC TYPE decided by Phase 2A now resolves to a scope-of-work value.
**SOW only** — IDB, CHECK STATUS and the received dump remain unimplemented,
and nothing writes an Excel file.

- `engine/sow/` — `rules.py` (the `DOCUMENT TYPE` sheet's 22 DOKAR → SOW
  mappings, keyed on either the DOKAR or the document-type name the same row
  states) and `resolver.py` (the verdict). The resolver's entire input is a
  DOC TYPE: it never sees a document number, a title, or column AM/AN/AO.
- `domain/models/sow.py` — `SowRequirement`. `is_required` is three-valued, so
  an uncovered DOC TYPE cannot read as the business statement `NO`.
- `engine/validation/sow.py` — comparison against column AM of
  `QatarEnergy-TN WORKING`, with mismatches grouped by root cause.
- `services/sow_service.py`, `export_sow_report`, and
  `scripts/validate_phase.py --phase 2b`.
- `SheetTable` now records each data row's true Excel row number; the
  `DOCUMENT TYPE` sheet has a blank spacer row that position alone drifts past.

**`OLD REV NOT SOW` and `NOT SOW` resolve to `NO`** — exceptionless across
13,582 reference rows. Both are consumed as verdicts; Phase 2B contains no
old-revision logic of its own. `OTHER` is deliberately not treated the same
way: it reads `NO` in 4,237 rows and `YES-…` in 174, so it states no rule.

**93.92% agreement** with column AM over the 15,977 rows where both sides
state a value (15,005 matches, 972 mismatches). The mismatches are reported,
not patched: the rules workbook and the working sheet flatly disagree over
whether five SOW strings contain `/HIERARCHY` (166 rows, zero agreement on
those DOKARs), column AM overrides 391 in-scope rows to `NO` on a distinction
DOC TYPE does not predict, and MOM's rule value never occurs in the sheet at
all. No per-document exception was hard-coded. See
`docs/business-rules/sow-rules.md` for the six open questions.

### Added — Phase 2A: DOC TYPE classification

Documents are now classified from the keyword rules workbook
(`data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`, 182 rules across its two
keyword sheets). **DOC TYPE only** — SOW, IDB and CHECK STATUS remain
unimplemented, and nothing writes an Excel file.

- `engine/classification/` — `rules.py` (keyword syntax, rule model,
  precedence) and `classifier.py` (the verdict). Two modules, no framework, no
  `utils.py`.
- `domain/models/classification.py` — `DocumentClassification` retains **every**
  matching rule, not just the winner; 1,865 reference rows match more than one.
- `infrastructure/excel/rules_workbook.py` and `reference_workbook.py` — the two
  new read-only adapters. The classifier never sees a worksheet or a column.
- `engine/validation/doc_type.py` — comparison against column AL of
  `QatarEnergy-TN WORKING`, with mismatches grouped by root cause.
- `DocumentRecord` gains `doc_type` and `doc_type_rule`; `documents.csv` gains
  both columns and `doc_type_report.json` is a new artefact.
- `scripts/validate_phase.py --phase 2`, and `--out` on both phases.
- `settings.vendor_consolidation_enabled = False` — `TN FROM VENDORS` is
  explicitly **not** merged into the processing universe. A named switch with
  no implementation behind it, so a future plant has somewhere to turn it on.

**Matching semantics**, derived from the workbook rather than assumed: plain
keywords match as substrings (they are written in the singular and must catch
plurals — word-bounded matching loses 78 rows and gains 4), `*` is a wildcard,
` or ` is alternation, and a run of X's in a document-number keyword means
digits. Required-sheet rules outrank not-required ones — where both matched, the
reference agreed with the required sheet 84 times and the not-required sheet 0.

**Validation:** 2,564 exact matches of the 3,356 rows where column AL states a
document type — **76.40 %**. The remaining 18,016 rows of that column hold
scope-of-work and revision verdicts (`OLD REV NOT SOW`, `NOT SOW`, `OTHER`) that
no keyword rule can produce. The 792 mismatches are grouped by cause — label
drift, a stale reference, compound labels the rule set cannot express, missing
rules, and manual answers that contradict each other — and **no special case was
added for any of them**. See
[`docs/business-rules/classification-rules.md`](docs/business-rules/classification-rules.md).

Phase 1 behaviour is unchanged; its 120 tests pass untouched. Test count
120 → 240.

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
