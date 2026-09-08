# Backend

The MDR engine, the domain it operates on, the Excel/filesystem adapters that
feed it, and the HTTP boundary that exposes it.

**Phase 1, Phase 2A (DOC TYPE) and Phase 2B (DOC IS REQUIRED SOW) only.**
Phase 2C onwards is not implemented; `engine/idb` and `engine/received` are
empty, and nothing writes an Excel file.

---

## Layers

```
api          HTTP boundary. Adapters only — no MDR rule may live here.
  ↓
services     Orchestration. mdr_pipeline (the run), export_service (artefacts).
  ↓
engine       Every MDR business rule.
  ↓
domain       MDR concepts. Standard library only.

infrastructure   Excel / filesystem / storage — supports engine and services.
core             Configuration and logging.
```

Dependencies point downward only. `openpyxl` is imported in exactly one module
(`infrastructure/excel/workbook_reader.py`); nothing in `domain/` imports
FastAPI. See
[`../docs/architecture/SYSTEM_ARCHITECTURE.md`](../docs/architecture/SYSTEM_ARCHITECTURE.md).

---

## Install

```bash
pip install -r requirements.txt
```

Python ≥ 3.11.

## Run the engine

```bash
python -m app.cli --validate                        # data/input/current → data/output/latest
python -m app.cli --workbook path/to.xlsx --outdir out/
```

The engine is usable without the API or the CLI:

```python
from app.services.mdr_pipeline import MdrEngine
result = MdrEngine("data/input/current/log.xlsx").run()
print(result.summary())
```

## Run the API

```bash
uvicorn app.main:app --reload      # http://127.0.0.1:8000/docs
```

`GET /api/health` · `GET /api/mdr/summary`. **Unauthenticated — local use
only.** See
[`../docs/architecture/API_ARCHITECTURE.md`](../docs/architecture/API_ARCHITECTURE.md).

## Test

```bash
python -m pytest tests                 # 410 tests (120 Phase 1, 120 Phase 2A, 170 Phase 2B)
python -m pytest tests/unit            # rules in isolation, no I/O
python -m pytest tests/regression      # real-world cases that must not regress
```

Integration and regression suites skip automatically when the source workbook is
absent. `pyproject.toml` puts `backend/` on the import path, so pytest works
from here or from the repository root.

---

## Adding a rule

1. The rule goes in `engine/<capability>/`, next to the rules it belongs with.
2. If it needs a new concept, add it to `domain/` first.
3. If it needs new spreadsheet data, add the caption to
   `infrastructure/excel/mdr_workbook.py` and a field to the source-row record —
   never read a column index from the engine.
4. Add a unit test. If the rule exists because of something found in the real
   workbook, add a regression test naming that case.
5. Record the decision and its evidence in
   [`../docs/architecture/DECISION_LOG.md`](../docs/architecture/DECISION_LOG.md).

## Conventions

- No `utils.py`, `helpers.py`, `common.py` or `misc.py`.
- Every decision a row receives carries a `reason` explaining it.
- Ambiguity produces an exception, never a guess.
- Source workbooks are opened `read_only=True` and are never written to.
