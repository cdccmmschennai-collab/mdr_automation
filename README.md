# MDR Automation Tool — Phase 1 Engine

Deterministic engine that reads the MDR workbooks, normalises document
identities, consolidates `QatarEnergy-TN` with `TN FROM VENDORS`, interprets
Status Codes, sequences revisions and determines the latest revision.

**The source workbooks are never modified.** Every workbook is opened
read-only, and a test asserts the file hash and mtime are unchanged by a run.

## Run

```bash
python -m mdr_engine.cli --validate            # uses input/new/… by default
python -m mdr_engine.cli --workbook path/to.xlsx --outdir output
```

Set `PYTHONPATH=src`, or run from the project root where `tests/conftest.py`
puts `src` on the path.

## Output (`output/`)

| File | Contents |
|---|---|
| `mdr_phase1_result.json` | Full machine-readable result + summary |
| `documents.csv` | One row per QatarEnergy-TN document row |
| `vendor_rows.csv` | Vendor rows with match status/method |
| `exceptions.csv` | Rows needing human review |
| `validation_report.json` | Comparison vs the workbook's own L/NL column |

Each document record carries: `document_identity`, `qatarenergy_document_no`,
`revision`, `issue_code`, `review_code`, `revision_type`, `revision_rank`,
`is_latest_revision`, `revision_status`, `match_status`, `match_method` and a
`reason` explaining the decision.

## Results

- **0 genuine conflicts** against the workbook's own `LATEST/ NOT LATEST` column
- 97.58% raw agreement; every disagreement has an identified root cause
- 79 rows where the engine is right and the manual workbook is stale
- 262 unlabelled rows the engine resolves — the manual backlog

See [`docs/PHASE1_FINDINGS.md`](docs/PHASE1_FINDINGS.md) for the evidence
behind every rule, including one candidate rule that was **tested and
rejected**, and the open questions for the business.

## Design

```
src/mdr_engine/
  identity.py      normalisation + canonical keys (conservative: never drops segments)
  revision.py      revision parsing and ordering bands
  status_codes.py  Status Codes sheet -> review/issue codes (loaded, not hard-coded)
  workbook_io.py   read-only sheet/column discovery by header text, not position
  matching.py      QE <-> vendor tier ladder; ambiguity matches nothing
  engine.py        orchestration, grouping, latest determination
  validate.py      ground-truth comparison with root-cause classification
  cli.py           entry point
```

Principles held throughout: accuracy over coverage; an explicit exception
instead of a guess; every decision carries a reason. Modules are independent so
Phase 2 (DOC TYPE, SOW, IDB, received-document dump, Excel output) can be added
without touching the revision/matching engine.

## Tests

```bash
python -m pytest tests -q     # 120 tests
```

Unit tests cover the rules and the specific anomalies found in the real data;
`test_integration.py` runs the full workbook and asserts invariants (at most
one latest per document, no genuine conflicts, source file unmodified). It
skips automatically if the workbooks are absent.

## Not in Phase 1

DOC TYPE, SOW, IDB, CHECK STATUS / received-document dump, Excel output,
frontend, deployment. No AI/LLM is used — all logic is deterministic.
