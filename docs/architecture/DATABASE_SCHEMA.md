# Database Schema — Delivery Phase 2

PostgreSQL 16, SQLAlchemy 2.0 ORM, psycopg 3, Alembic migrations.

```
plants  1────*  mdr_submissions  1────*  mdr_document_rows
                       │
                       1────1  mdr_processing_summaries  *────1  rule_sets
```

Five tables. The MDR workbook has some seventy columns; copying it into
PostgreSQL column-for-column would produce a database that needs migrating
every time the spreadsheet changes and would still not be the authority — the
workbook is. What is stored is what the product needs in order to answer
questions about a submission after the fact.

Definitions: `backend/app/infrastructure/persistence/models.py`.
Migration: `backend/alembic/versions/…-0001_delivery_phase_2_initial_schema.py`.

---

## Conventions

**UUID primary keys** on the four low-volume tables; `BIGINT` identity on
`mdr_document_rows`, which takes ~22k rows per submission and accumulates.

**`TIMESTAMPTZ` everywhere.** A submission is uploaded at an instant, not at a
wall-clock reading. Naive timestamps would make two plants in two time zones
incomparable.

**Status is `VARCHAR` + `CHECK`, not a PostgreSQL `ENUM`.** A native enum reads
better in `psql`, but adding a value to one is a migration that cannot run
inside a transaction on older servers — and the legal values are a domain fact
belonging in `domain/enums/lifecycle.py`, not in the database's type system.

**Constraint names are fixed** by a naming convention in `persistence/base.py`.
Without it PostgreSQL invents names, Alembic emits migrations referencing those
invented names, and a later `ALTER` cannot find what it wants to drop on a
database built by a different server version.

---

## `plants`

A plant/project that submissions belong to. One row today (QatarEnergy-TN); the
table exists so the second plant is a row rather than a migration.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | **PK** |
| `code` | VARCHAR(64) | **UNIQUE**. Business key, e.g. `QATARENERGY-TN`. |
| `name` | TEXT | |
| `created_at`, `updated_at` | TIMESTAMPTZ | Server-defaulted. |

`code` is unique because two plants sharing one would make every submission
ambiguous.

---

## `rule_sets`

One identified version of the MDR rule inputs. See `RULE_VERSIONING.md`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | **PK** |
| `version_label` | VARCHAR(64) | **UNIQUE**. Human-facing, e.g. `A`. |
| `source_filename` | TEXT | Audit trail only — the digest is the identity. |
| `content_sha256` | VARCHAR(64) | **UNIQUE**, `CHECK length = 64`. |
| `required_rule_count` | INT | Rules loaded from `REQUIRED-KEY DOC.WORDS`. |
| `not_required_rule_count` | INT | From `NOT REQUIRED-KEY DOC.WORDS`. |
| `sow_rule_count` | INT | From `DOCUMENT TYPE`. |
| `idb_rules_origin` | VARCHAR(32) | `code` today — Phase 2C's rules are in `engine/idb/rules.py`, not in any sheet. |
| `notes` | TEXT | |
| `created_at` | TIMESTAMPTZ | |

**No `updated_at`, deliberately.** A rule set that changed in place would
silently rewrite the history of every submission pointing at it — the exact
failure the table exists to prevent. A changed workbook produces a new digest
and therefore a new row.

`content_sha256` is unique so the same file cannot be registered twice under
two labels and appear to be two different rule sets.

---

## `mdr_submissions`

One uploaded MDR workbook and how far it has been processed.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | **PK** |
| `plant_id` | UUID | **FK** → `plants.id` `ON DELETE RESTRICT` |
| `submission_no` | INT | The business's `MDR #6`. `CHECK > 0`. |
| `status` | VARCHAR(16) | `CHECK IN ('UPLOADED','EXTRACTED','AUTOMATED','FAILED')` |
| `failure_reason` | TEXT | Populated only when `FAILED`. |
| `source_filename` | TEXT | Not unique — the same name arrives every month. |
| `source_sha256` | VARCHAR(64) | `CHECK length = 64`. Indexed, **not** unique. |
| `source_byte_size` | BIGINT | `CHECK > 0` |
| `stored_path` | TEXT | Empty until a storage adapter exists. |
| `source_sheet_name` | TEXT NULL | Extraction discovery. Null until `EXTRACTED`. |
| `source_header_row` | INT NULL | ″ |
| `source_row_count` | INT NULL | ″ |
| `uploaded_at` | TIMESTAMPTZ | |
| `extracted_at` | TIMESTAMPTZ NULL | |
| `automated_at` | TIMESTAMPTZ NULL | |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

**Constraints**

* `UNIQUE (plant_id, submission_no)` — each plant numbers its own submissions,
  so two plants may both have an `MDR #6` and one plant may not.

**Indexes**

* `(plant_id, uploaded_at)` — a plant's history in order.
* `(source_sha256)` — find every submission made from identical bytes.
* `(status)` — find everything stuck at a step.

**Why the FK is `RESTRICT`.** Deleting a plant must not silently take its
submission history with it.

**Why `source_sha256` is not unique.** Re-processing the same workbook under a
new rule set is legitimate. Two submissions sharing a digest is a fact worth
being able to find, not an error.

---

## `mdr_document_rows`

One processed QatarEnergy-TN row of one submission: the four automation
columns, the identity and revision context needed to make sense of them, and
the provenance of each verdict.

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT identity | **PK** |
| `submission_id` | UUID | **FK** → `mdr_submissions.id` `ON DELETE CASCADE` |
| `source_row` | INT | 1-based row in the source sheet. `CHECK > 0`. |
| `document_identity` | TEXT | Normalised matching key (Phase 1). |
| `qatarenergy_document_no` | TEXT | |
| `revision`, `revision_raw` | VARCHAR | |
| `revision_status` | VARCHAR(32) | `LATEST` / `OLD` / `AS_BUILT` / `EXCEPTION` |
| `is_latest_revision` | BOOLEAN | |
| `document_title`, `discipline` | TEXT | |
| **`doc_with_rev`** | TEXT | `DOC WITH REV` (Phase 1) |
| **`doc_type`** | TEXT | `DOC TYPE` (Phase 2A). Empty = no rule covered it. |
| **`sow`** | TEXT | `DOC IS REQUIRED SOW` (Phase 2B) |
| **`idb_completed_status`** | TEXT | `DOC IDB COMPLETED STATUS` (Phase 2C). Empty = a person must still check it. |
| `check_status` | TEXT | `CHECK check_status = ''` — see below. |
| `doc_type_rule` | TEXT | Which keyword rule decided `doc_type`. |
| `sow_source`, `idb_source` | TEXT | Where each verdict came from. |
| `created_at` | TIMESTAMPTZ | |

**Constraints**

* `UNIQUE (submission_id, source_row)` — one row of one workbook, stored once.
* `CHECK (check_status = '')`.

**Indexes**

* `(submission_id, document_identity)`
* `(submission_id, doc_type)`

Both are composite and lead with `submission_id`, because every query into this
table is scoped to one submission.

**`check_status` and its CHECK constraint.** `CHECK STATUS` is Phase 3B and
cannot be decided without the received-document dump, which does not exist.
`AutomationRow` refuses to be constructed with a value in it; this constraint
means the database refuses too. Both have to be removed deliberately, together,
for the column to start being written — which is the point. A blank there means
*not evaluated*, and must never be read as `NOT RECEIVED`.

**Why `CASCADE` here and `RESTRICT` above.** These rows have no meaning apart
from their submission; a plant's history does.

---

## `mdr_processing_summaries`

The record of one processing run over one submission.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | **PK** |
| `submission_id` | UUID | **FK** → `mdr_submissions.id` `ON DELETE CASCADE`, **UNIQUE** |
| `rule_set_id` | UUID | **FK** → `rule_sets.id` `ON DELETE RESTRICT`, `NOT NULL` |
| `engine_version` | VARCHAR(32) | The backend version that produced it. |
| `row_count` | INT | `CHECK >= 0` |
| `doc_with_rev_populated` | INT | |
| `doc_type_populated` | INT | |
| `sow_populated`, `sow_unresolved` | INT | |
| `idb_populated`, `idb_unmapped` | INT | |
| `idb_manual_check_required` | INT | Required documents left blank for a human. |
| `check_status_populated` | INT | `CHECK = 0` |
| `counts` | JSONB | Per-value breakdowns + the extraction discovery map. |
| `created_at` | TIMESTAMPTZ | |

**Index:** `(rule_set_id)` — *which submissions would be affected if these rules
turn out to be wrong?*

The counters are `AutomationRun.summary()` — the numbers the CLI already prints,
persisted rather than recomputed. The scalar counts are columns so they can be
queried and constrained; the per-value maps (`doc_type_counts`, `sow_counts`,
`idb_counts`) are JSONB because they are variable-width maps keyed by business
values, and a table per map would be a schema that changes whenever the business
adds a document type.

`rule_set_id` is the load-bearing column: it is what keeps MDR #6 explainable
after Rule Set B replaces Rule Set A. `NOT NULL`, and `RESTRICT`, so a rule set
any result points at cannot be deleted.

**`UNIQUE (submission_id)`** because Delivery Phase 2 stores one run per
submission. Re-running under a new rule set is a real future requirement; when
it arrives, dropping this one constraint turns the table into the run history it
is already shaped like, and no other column moves.

`engine_version` is here because the rule set explains the *rules* and this
explains the *code*. A result can differ from another for either reason.

---

## Historical submissions are independent by construction

The requirement — MDR #6, #7 and #8 must stay separately identifiable and
queryable — is satisfied structurally rather than by convention:

* No column, index or repository method refers to "the latest" or "the current"
  submission. `SubmissionRepository` has no `get_latest()`, deliberately.
* No row is updated when a newer submission arrives.
* Every query into `mdr_document_rows` is scoped by `submission_id`, and both
  indexes lead with it.
* Each submission's summary pins its own `rule_set_id`, so a later rules change
  cannot retroactively re-explain an older result.

`tests/persistence/test_repositories.py::TestHistoricalSubmissionsStayIndependent`
and `test_rule_versioning.py::TestHistoricalResultsStayExplainable` assert this.

---

## Migrations

```bash
cd backend
alembic upgrade head      # apply
alembic current           # what this database is at
alembic downgrade -1      # step back one
```

The URL comes from `MDR_DATABASE_URL` (or `DATABASE_URL`) via the application's
own settings — `alembic.ini` carries no `sqlalchemy.url`, so the migrations and
the application cannot be pointed at different databases by accident, and no
committed file holds a credential.

**The application never creates schema.** There is no `create_all` anywhere,
including in the tests, which build their throwaway database by running the
migrations. The schema has exactly one source.
`tests/persistence/test_migrations.py` asserts that autogenerate finds no
difference between the migrated database and the models, so a model cannot gain
a column that no migration creates.
