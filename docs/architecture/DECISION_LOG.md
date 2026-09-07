# Decision Log

Decisions taken during Phase 1, each with the evidence that produced it. Where a
candidate rule was **tested and rejected**, that is recorded too — the rejection
is as valuable as the rule.

Nothing here is invented. Every business decision traces to the supplied
workbooks; the full working is in
[../business-rules/MDR_BUSINESS_RULES.md](../business-rules/MDR_BUSINESS_RULES.md).

---

## Business decisions

### D-01 — Alphabetic revisions rank *after* numeric revisions

**Decision:** `0 < 1 < 2 < … < A < B < C`. Implemented as ordering *bands*, not
lexical comparison, so `10` correctly outranks `9` and `A` outranks `99`.

**Evidence:** both orderings were tested against the workbook's own
`LATEST/ NOT LATEST` column, over groups where every row is labelled:

| Ordering | Agree | Disagree | Rate |
|---|---|---|---|
| **Alphabetic later** | **7,653** | **1** | **99.99 %** |
| Numeric later | 5,231 | 2,423 | 68.3 % |

**Where:** `engine/revision/parsing.py`, `domain/models/revision.py`

---

### D-02 — `Z` is an AS-BUILT marker, not the latest active revision

**Decision:** `Z` gets its own band (`AS_BUILT`) and is **excluded from
latest-revision candidacy**. It is reported as `revision_status = AS_BUILT`, not
as an exception — it is a well-understood category, not an error.

**Evidence:** the Status Codes sheet defines the ASB sequence as
`AFC-GRASS FIELD / Z-BROWN FIELD`. In the data: 68 rows carry revision `Z`;
**68 of 68** have issue code `ASB`; **0 of 68** are ever marked `L`; in **all
68** a sibling revision holds the `L`. Treating `Z` as the 26th letter would
wrongly hand it latest in all 68 groups.

**Where:** `engine/revision/parsing.py` (`AS_BUILT_TOKENS`)

---

### D-03 — Cancellation can still be the latest revision

**Decision:** a cancelled document is **not** excluded from latest
determination. `CODE-11` / issue code `CAN` do not affect ranking.

**Evidence:** counter-intuitive but unambiguous —

| Signal | Rows | Marked `L` |
|---|---|---|
| Issue code `CAN` | 339 | 326 (96 %) |
| Review `CODE-11` | 320 | 319 (99.7 %) |

A cancelled document *is* the latest revision of itself.

**Where:** no exclusion exists in `engine/revision/ranking.py` — deliberately.
`ReviewCode.is_cancellation` exists for reporting only.

---

### D-04 — Withdrawn submissions are excluded

**Decision:** a row whose status or remarks contain `WITHDRAW` leaves latest
candidacy **and** is flagged as an exception, so a human still sees it.

**Evidence:** `4391-MTY-4-15-0004` is the **single** genuine counter-example to
D-01 — revision `A` exists but revision `1` holds the `L`. Its status column
reads `WITHDRAWIN`, its remarks `WITHDRAWN EMAIL … RETURNED TO TECHNIP`.

**Caveat, recorded deliberately:** the evidence base is **one row** (n=1). The
marker is isolated in `WITHDRAWN_MARKERS` precisely so it is cheap to revise if
the business says otherwise.

**Where:** `engine/revision/eligibility.py`

---

### D-05 — Renumbering remarks are informational only ❌ RULE REJECTED

**Decision:** remarks saying a document was renumbered or made non-deliverable
are recorded as `renumbering_note` and **must not** exclude a row from latest
determination.

**Evidence:** the exclusion rule was implemented and then **removed**:

- the remark pattern matches 182 rows → **128 `NL` / 50 `L`**
- the overall base rate is already ~64 % `NL`, so the signal is negligible
- in all three conflicts it introduced, the renumbered row was itself the `L`
- **387 of the 480 all-NL rows carry no remark at all**, so no deterministic
  signal exists for the majority

**Where:** `engine/revision/eligibility.py` — `RENUMBERED_RE` with the evidence
recorded beside it, and `has_renumbering_note()` documented as non-gating.

---

### D-06 — Vendor matching never forces an uncertain match

**Decision:** a deterministic tier ladder (exact → normalised → VEN-prefix
tolerant). The first tier yielding exactly one QatarEnergy identity wins. A tier
yielding **more than one** records `AMBIGUOUS` and matches **nothing**. No
fuzzy, partial or prefix matching exists.

**Evidence:** only 18.5 % of vendor rows (111/600) resolve to a QatarEnergy
document, because the identifier columns are mostly empty or hold
vendor-internal numbers (`DEW-5718-*`, `BQ/IMS/QT-169/*`) that were never issued
under a project document number. This is a business fact, not a defect. Forcing
matches would manufacture false links.

Ambiguity is effectively nil: exactly **one** canonical key maps to more than
one document (`4391-0-CV-00XX` vs `4391-0-CV-00xx`, a case-only difference).

**Where:** `engine/identity/matching.py`

---

### D-07 — Groups with no LATEST require a business answer, not a guess

**Decision:** where the workbook marks **no** row in a group as latest, the
engine still names its own latest and the validation layer classifies the
disagreement as `WORKBOOK_MARKS_GROUP_INACTIVE`. It is **reported, never
guessed at**, and is explicitly excluded from the adjusted agreement rate.

**Evidence:** 431 document groups have no `L` at all. Their profile differs
sharply from normal groups (89.2 % `IFC` vs 32.4 %; 88.5 % `CODE-2` vs 38.8 %;
403 of 431 are single-row). `NL`-with-no-latest encodes *"not an active
deliverable"* — a different meaning from *"not the newest revision"* — and it is
not derivable from the available columns.

**This is the largest open question for Phase 2.** It needs a business answer.

**Where:** `engine/validation/latest.py` (`Cause.WORKBOOK_MARKS_GROUP_INACTIVE`)

---

### D-08 — Identity normalisation never drops a segment

**Decision:** normalisation collapses case and separators only.
`MEWTP-8-83-0001` and `MEWTP-8-83-0001-001` remain **distinct documents**.

**Evidence:** dropping trailing segments would merge genuinely distinct
documents. Protected by a regression test.

**Where:** `engine/identity/normalisation.py`

---

### D-09 — The revision comes from the REV field only

**Decision:** a digit or letter appearing inside a document number is never
treated as a revision. `4391-MTY-1-19-0051` parses as `UNPARSEABLE`, not as
revision 51.

**Where:** `engine/revision/parsing.py`

---

### D-10 — Status codes are loaded, not hard-coded

**Decision:** review and issue codes come from the workbook's own `Status Codes`
sheet at run time. A revised sheet changes engine behaviour without a code
change.

**Where:** `engine/revision/status_codes.py`

---

### D-11 — Ambiguity produces an exception, never a guess

**Decision:** two rows sharing the highest revision in a group → both become
`EXCEPTION` and **neither** is latest. A group with no eligible revision → the
whole group becomes `EXCEPTION`.

**Evidence:** 2 groups in the workbook have a duplicate top revision.

**Where:** `engine/revision/ranking.py`

---

### D-12 — The source workbooks are never written to

**Decision:** every workbook is opened `read_only=True`. Results go to
`data/output/latest/` only.

**Enforced by:** `tests/integration/test_phase1_workbook.py` asserts the source
file's SHA-256 **and** mtime are unchanged by a full run.

---

## Architecture decisions

### A-01 — Identity and revision stay separate

Two engine packages, not one. They answer different questions ("which document
is this?" vs "where in its life is this?") and will diverge further as Phase 2
adds classification to identity's side.

### A-02 — No `utils.py`, `helpers.py`, `common.py` or `misc.py`

Every module has one named responsibility. `clean` and `is_null_token` live in
`engine/identity/normalisation.py` because they define what a cell *means* in
this project's data — that is a business convention, not a generic string
utility.

### A-03 — Excel knowledge is confined to one file

`infrastructure/excel/mdr_workbook.py` holds every sheet name and header caption
the backend knows, including the workbook's own misspelling `ORGINATOR`. The
engine receives named `DocumentSourceRow` records and never sees a row or column
index. `openpyxl` is imported in exactly one module.

Previously these captions were embedded in the orchestration module, which meant
the revision engine's file transitively knew about Excel columns.

### A-04 — The domain has a `TYPE_CHECKING`-only reference to the engine

`domain/models/mdr_result.py` annotates `status_codes: Optional["StatusCodeBook"]`,
which is an engine type. The import is guarded by `TYPE_CHECKING`, so there is
no runtime domain → engine dependency. The alternative — moving `StatusCodeBook`
into the domain — would drag sheet-row parsing into a layer that must not know
about sheets.

### A-05 — `RevisionStatus` stays a `str` subclass, not an `Enum`

It looks like it wants to be an `Enum`, and it isn't one. Converting it would
change the emitted JSON, which is Phase 1 output that has already been
validated. Left as found.

### A-06 — `DocumentRecord._eligible` is a monkey-patched private attribute

The pipeline attaches `_eligible` to each `DocumentRecord` to carry latest
candidacy from assembly into ranking; `artifact_writer.public_fields()` strips
it before serialisation.

**This is a known wart.** A cleaner design would make it a declared field or
pass candidacy separately. It was **left unchanged** because changing it risks
altering Phase 1 behaviour, which this refactor must not do. Documented here so
the next person does not discover it by surprise. Candidate for Phase 2 cleanup,
behind the existing tests.

### A-07 — `check_status.py` was not created

The target architecture names `domain/enums/check_status.py`. It does not exist,
because CHECK STATUS is Phase 4 and no evidence yet defines its vocabulary.
Writing one now would be inventing a business rule.

### A-08 — Configuration is a frozen dataclass, not a settings framework

`core/config.py` uses `os.environ` and a dataclass. `pydantic-settings` is
available but adds a dependency and indirection Phase 1 does not need.

### A-09 — The default workbook is discovered, not hard-coded

Previously the CLI hard-coded the production workbook filename. It now takes
`MDR_INPUT_WORKBOOK`, else the first `.xlsx` in `data/input/current`, else it
reports that there is nothing to process. No production path is in source.

---

## Open questions for the business

Carried forward from Phase 1, unanswered:

1. **What does `NL` on a whole document group mean?** (431 groups) Renumbered,
   superseded, non-deliverable — or simply never reviewed? See D-07. The single
   largest unmodelled behaviour.
2. **Should a renumbered document link to its successor?** The remarks name the
   new number; a successor relationship could be modelled explicitly.
3. **Is `WITHDRAWN` a recognised lifecycle state?** Only one row uses it, with
   no dedicated column. See D-04.
4. **Should the 262 unlabelled rows be written back?** Phase 1 deliberately does
   not modify the workbook.
