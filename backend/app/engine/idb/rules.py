"""The rules that decide DOC IDB COMPLETED STATUS, and where they come from.

There is no IDB sheet in the rules workbook. The `DOCUMENT TYPE` sheet states
which documents are in scope (`DOCUMENT SOW`), `FOLDER-UPDATE` is a note about
folder names, and `Status Codes` describes QatarEnergy review and issue codes.
None of them states an IDB status. The authority for Phase 2C is therefore the
observed behaviour of column AN of `QatarEnergy-TN WORKING`, read as evidence
and reduced to the two rules below.

**Rule 1 - out of scope means no check is due.**
Every row whose DOC IS REQUIRED SOW reads `NO` carries `NO NEED TO CHECK` in
column AN: 18,704 of 18,706 rows, the two exceptions being the literal `0`
that column AM also carries on those rows. This holds through every other
column - it is true of all 300 rows whose submission was cancelled, of latest
and old revisions alike, and of every issue and review code.

**Rule 2 - in scope means a check is due, and its outcome is recorded
elsewhere.**
The remaining values (`COMPLETED`, `PENDING`, `TO BE CHECK`, `CANCELLED`, ...)
appear only on rows whose SOW value begins `YES`, and *nothing in any workbook
this project reads predicts which one*. The measured evidence:

* no column separates `COMPLETED` from `PENDING`: not the issue code, the
  QatarEnergy review code, the discipline, the originator, the latest flag,
  nor the remarks;
* the values track sheet position instead - the last ~350 rows, the newest
  transmittals, hold 91 of the 114 `TO BE CHECK` rows while the older bands
  are almost entirely `COMPLETED`. That is a record of how far the checker has
  got, not a rule;
* `TAG NOT IN FMTL` needs the FMTL, which is not in any workbook here;
* `GENERAL SPECIFICATION` and `REFERENCE` are human judgements - identically
  worded titles carry `COMPLETED` on some rows and `GENERAL SPECIFICATION` on
  others.

So the outcome is an input, not a derivation. A completion source states it
and the resolver carries it through; when none has spoken the status is
`TO BE CHECK`, which is what the column itself says for an in-scope document
nobody has checked yet.

`docs/business-rules/idb-rules.md` holds the full value-by-value evidence and
the open questions.
"""

from __future__ import annotations

from typing import Optional

from ...domain.models.idb import CHECK_OUTCOMES
from ...domain.models.sow import NOT_REQUIRED, REQUIRED_PREFIX
from ..identity.normalisation import clean, is_null_token

#: The `YEE-...` typo in the working sheet. Accepted when reading a SOW value
#: for its *scope*, because `YEE-MTL/DOC IDB` plainly states a requirement.
#: It never reaches a Phase 2C output; only the yes/no reading of it does.
_REQUIRED_PREFIXES = (REQUIRED_PREFIX, "YEE")


def normalise(value: object) -> str:
    """Comparison form for a status or SOW label: whitespace and case only.

    Punctuation is left alone, exactly as in `engine.sow.rules`, so
    `COMPLETED (REV UPDATED)` keeps its parentheses and a reference spelling
    variant stays visible as a variant rather than being quietly erased.
    """
    return clean(value).upper()


def scope_of(sow: object) -> Optional[bool]:
    """Read a DOC IS REQUIRED SOW string as an in-scope / out-of-scope verdict.

    True when the value states a requirement, False when it states `NO`, and
    None when it states neither - blank, or one of the non-verdict entries the
    working sheet carries in column AM (`CANCELLED`, `0`, `COMMON`). A value
    that states no verdict must not be read as `NO`; that is the difference
    between a document confirmed out of scope and one nobody has decided.
    """
    label = "" if is_null_token(sow) else normalise(sow)
    if not label:
        return None
    if label == NOT_REQUIRED:
        return False
    if label.startswith(_REQUIRED_PREFIXES):
        return True
    return None


def outcome_of(value: object) -> str:
    """The vocabulary status a completion source stated, or empty if unknown.

    Matching is exact on the normalised label. Near-misses are deliberately
    *not* repaired: the working sheet's `COMPLETE` and `REF` are data-entry
    variants, and a completion source that emits one is stating something the
    vocabulary does not define. The resolver reports that rather than guessing
    which value was meant.
    """
    label = "" if is_null_token(value) else normalise(value)
    return label if label in CHECK_OUTCOMES else ""
