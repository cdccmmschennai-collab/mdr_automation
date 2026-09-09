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
* any UI or endpoint for choosing a rule set. Assigning a human label (`A`,
  `B`) is possible through the repository but nothing calls it yet; the default
  label is derived from the digest.
