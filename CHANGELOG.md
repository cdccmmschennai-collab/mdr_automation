# Changelog

All notable changes to this project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — Phase 2C: DOC IDB COMPLETED STATUS

The scope verdict decided by Phase 2B now resolves to an IDB status.
**IDB only** — CHECK STATUS, the received dump and the Excel output remain
unimplemented, and nothing writes an `.xlsx` file.

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
