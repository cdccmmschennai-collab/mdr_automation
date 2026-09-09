# Phase numbering — read this before trusting a phase number

Three numbering schemes are in use in this repository, and they do not agree.
None is wrong; they were written for different audiences at different times.
This page is the map between them. **A bare "Phase 3" is ambiguous — always say
which scheme.**

## The three schemes

**A. Engine phases** — used in the source, the docstrings, the CLI banner and
the test suite names (`test_phase2d_pipeline.py`). Sub-lettered, because the
classification work split into four independent resolvers.

**B. Document phases** — the filenames in this directory, `phase-01` … `phase-07`.
Numbered before the sub-lettering existed, so one document can cover several
engine phases.

**C. Delivery phases** — the build-out plan agreed with the business:
Excel → PostgreSQL → API → download → Docker → freeze. This scheme restarts at
1 and is the one meant in planning conversations.

## The map

| Work | A. Engine | B. Document | C. Delivery | Status |
|---|---|---|---|---|
| Identity, revision, latest | Phase 1 | `phase-01-identity-revision` | — | done |
| `DOC TYPE` classification | Phase 2A | `phase-02-classification` | — | done |
| `DOC IS REQUIRED SOW` | Phase 2B | `phase-03-sow-idb` | — | done |
| `DOC IDB COMPLETED STATUS` | Phase 2C | `phase-03-sow-idb` | — | done |
| Excel output, `QatarEnergy-TN Automated` sheet | Phase 2D | `phase-05-excel-output` | Phase 1 | done |
| Received dump, `CHECK STATUS` | Phase 3A/3B | `phase-04-received-check` | — | not implemented |
| Validation vs the manual columns | — | `phase-06-validation` | — | partial |
| PostgreSQL + persistence | — | — | Phase 2 | not started |
| Upload / process / summary API | — | `phase-07-web-application` | Phase 3 | not started |
| Excel download endpoint | — | `phase-07-web-application` | Phase 4 | not started |
| Docker local development | — | — | Phase 5 | not started |
| Hardening + API freeze | — | — | Phase 6 | not started |

## The two collisions that actually mislead

* **"Phase 4"** is the received-document check in scheme B, but the Excel
  *download endpoint* in scheme C. The engine work and the delivery work are
  unrelated.
* **"Phase 5"** is the Excel output in scheme B (delivered), but Docker in
  scheme C (not started). A reader who sees "Phase 5 is done" in one place and
  "Phase 5 has not begun" in another is reading two different schemes.

## Why this was not renumbered

Renaming the engine phases would touch the docstrings, the CLI output and the
test module names across a suite that is green — a large diff whose only effect
is cosmetic, and which would invalidate every phase reference in the decision
log. Renaming the document files would break the links pointing at them. The
cheaper and safer correction is this table.

If the numbering is ever unified, scheme C is the one to keep: it is the one
the business uses.
