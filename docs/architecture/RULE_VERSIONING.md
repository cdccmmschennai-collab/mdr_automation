# Rule-set versioning

## The problem

The MDR rules live in `data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`. The
business edits that file — a keyword is added, a document type is re-scoped —
and from then on the engine answers differently.

If nothing records which version of the file was in force, MDR #6, processed
last quarter under the old keywords, becomes indistinguishable from an MDR #6
processed under the new ones. It does not merely become unexplainable; it
silently appears to have been processed with rules it never saw.

```
        Rule Set A                          Rule Set B
            │                                   │
            ▼                                   ▼
      MDR #6 processed                   MDR #8 processed
            │                                   │
            └────── rule_set_id = A             └────── rule_set_id = B
                    stored, permanently                 stored, permanently
```

## What is persisted

`rule_sets` stores, per version:

* the **SHA-256 of the rules workbook's bytes** — the identity, and `UNIQUE`;
* the filename, for the audit trail;
* the **rule counts** each sheet yielded (`REQUIRED-KEY DOC.WORDS`,
  `NOT REQUIRED-KEY DOC.WORDS`, `DOCUMENT TYPE`);
* `idb_rules_origin`, which is `code` today.

`mdr_processing_summaries.rule_set_id` is `NOT NULL` with an `ON DELETE
RESTRICT` foreign key. A result that cannot name its rules cannot be stored,
and a rule set that a stored result points at cannot be deleted.

The fingerprint is computed by `services/rule_set_service.py`, which opens the
workbook read-only through the **existing** `RulesWorkbookReader`. The counts
recorded are therefore the counts the engine actually loads, not a second
reading of the file that might disagree with it.

## What is *not* persisted, and why

**The rule content is not copied into PostgreSQL.**

That would make the database a second home for business rules the business
maintains in Excel, and two homes means two answers. The engine would still read
the workbook, so the database copy would be documentation that can go stale
without anything failing — the worst kind, because it looks authoritative.

A digest records *which* rules ran without claiming to *be* the rules. It is
enough to prove that two runs used the same input, or that they did not.

## The limit of this, stated plainly

Given only the database, you can tell that MDR #6 and MDR #8 used different rule
sets, and exactly which file each used, by name, digest and rule counts.

**You cannot reconstruct the keywords of a workbook nobody kept.** Doing that
needs the rules workbook archived alongside the submission, which is a
storage-adapter question and belongs to the phase that adds one. Until then, the
operational implication is worth stating: **keep the old rules workbooks.** The
database can tell you which one you need; it cannot hand it to you.

## Plants and rule sets

```
                    PLANT  (plants.rules_workbook, NULL = default)
                      │  selects a rules workbook by filename
                      ▼
              data/rules/<file>.xlsx
                      │  fingerprinted by digest at automate
                      ▼
                  RULE SET  (rule_sets, one row per distinct content)
                      │
                      ▼
                 MDR ENGINE  (handed the path; knows no plant)
                      │
                      ▼
          mdr_processing_summaries.rule_set_id   (pinned, permanently)
```

The rule set is not owned by a plant, and a plant does not own rules. A plant
**selects** a rules workbook; the workbook's content **is** the rule set. That
one indirection gives both of the shapes the business needs:

| | Plant A | Plant B |
|---|---|---|
| Same rules | `rules_workbook = NULL` (default) | `NULL`, or the default's filename — **same `rule_sets` row** |
| Small differences | `NULL` | `plant-b-rules.xlsx`: the common rules plus B's own DOC TYPE / SOW keywords, as one workbook — **its own `rule_sets` row** |
| Rules revised | the default file is replaced → new digest → new row for A | B's file is revised when B's rules change → new row for B |

Where the differences are expressed: in Excel, in the sheets the reader
already consumes (`REQUIRED-KEY DOC.WORDS`, `NOT REQUIRED-KEY DOC.WORDS`,
`DOCUMENT TYPE`). A plant-specific rule is a row in that plant's workbook. It
is **never** an `if plant == …` in `engine/`, and the workflow service passes
the plant's workbook path down without looking inside it.

Reproducibility is unchanged: `rule_set_id` on a stored summary is what it
was when the result was produced. Changing which workbook a plant selects
affects submissions automated *after* the change and no earlier one; the
earlier rule set cannot be deleted while a result points at it (`RESTRICT`).

Not implemented, deliberately: a composed rule set (a base workbook plus an
override workbook merged at load time). Today one plant selects one file; a
plant whose rules differ maintains one workbook that holds its full rules.
If keeping several near-identical workbooks in step becomes a real cost, the
composition belongs in `RulesWorkbookReader` / `rule_set_service` with the
fingerprint covering both inputs — and nothing above the service, and nothing
in `engine/`, would change.

## Three different versions, easily confused

These are unrelated and are tracked separately:

| | What it protects | Where it lives |
|---|---|---|
| **API version** (`v1`) | The frontend's contract against breaking changes | A URL prefix, and nowhere else |
| **Rule-set version** | The meaning of a past automation result | `rule_sets`, referenced by `mdr_processing_summaries` |
| **MDR submission** (`#6`, `#7`) | The historical business record | `mdr_submissions.submission_no` |
| **Engine version** | Which *code* produced a result | `mdr_processing_summaries.engine_version` |

The last row is not the same as the rule-set version. A result can differ from
another because the rules changed or because the code did, and only recording
both distinguishes the two.

## Registering a rule set

`RuleSetRepository.register(fingerprint)` returns the existing row when the
digest is already known, rather than creating a second one — so re-registering
the same rules cannot fork a submission's history into two rule sets that are
actually the same rules.

Re-registering with a **different label does not relabel** the stored row.
Relabelling would rewrite what every historical result claims it was processed
with.

## What is implemented in Delivery Phase 2

Implemented and tested:

* fingerprinting the real rules workbook;
* the `rule_sets` table, its uniqueness and its digest `CHECK`;
* `mdr_processing_summaries.rule_set_id`, `NOT NULL` and `RESTRICT`;
* MDR #6 keeping Rule Set A after Rule Set B is introduced
  (`tests/persistence/test_rule_versioning.py`);
* an end-to-end run over the real workbook whose stored summary names the real
  rules workbook's digest.

Not implemented, and not claimed:

* archiving the rules workbook itself;
* re-running a submission under a new rule set (the schema is shaped for it —
  one `UNIQUE` constraint stands in the way, deliberately);
* any UI or endpoint for choosing a rule set. A plant's selection is a
  column set by an operator (`plants.rules_workbook`); no endpoint reads or
  writes it, and `GET /api/v1/plants` does not expose it. Assigning a human
  label (`A`, `B`) is possible through the repository but nothing calls it
  yet; the default label is derived from the digest.
