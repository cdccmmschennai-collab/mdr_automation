"""Status Codes sheet interpretation.

The review codes (CODE-1..CODE-11) and issue codes (IFC, IFA, AFC, ...) are
loaded from the workbook's own 'Status Codes' sheet rather than hard-coded, so
that a revised sheet changes engine behaviour without a code change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .identity import clean, is_null_token

#: Issue codes whose revision sequence is alphabetic, per the Status Codes sheet.
_ALPHA_SEQUENCE_RE = re.compile(r"\bA\s*,\s*B\s*,\s*C", re.IGNORECASE)
#: Issue codes whose revision sequence is numeric.
_NUMERIC_SEQUENCE_RE = re.compile(r"\b0\b|\b1\s*,\s*2\s*,\s*3", re.IGNORECASE)


@dataclass(frozen=True)
class ReviewCode:
    """A QatarEnergy review code, e.g. CODE-2."""

    code: str
    description: str

    @property
    def number(self) -> Optional[int]:
        m = re.search(r"(\d+)", self.code)
        return int(m.group(1)) if m else None

    @property
    def requires_resubmission(self) -> bool:
        """CODE-1/2/3 all call for a resubmission; 6/7/10/11 do not."""
        return self.number in (1, 2, 3)

    @property
    def work_may_proceed(self) -> bool:
        return self.number in (1, 2, 10)

    @property
    def is_cancellation(self) -> bool:
        return self.number == 11


@dataclass(frozen=True)
class IssueCode:
    """An issue/PDMS status code, e.g. IFA, RE-AFC, ASB."""

    code: str
    description: str
    revision_sequence: str

    @property
    def base_code(self) -> str:
        """'RE-IFA' -> 'IFA'. Re-issues share the base code's semantics."""
        return re.sub(r"^RE-+", "", self.code)

    @property
    def is_reissue(self) -> bool:
        return self.code.startswith("RE-")

    @property
    def is_as_built(self) -> bool:
        return self.base_code == "ASB"

    @property
    def expected_revision_band(self) -> Optional[str]:
        """'ALPHABETIC' / 'NUMERIC' / None, derived from the sheet text."""
        seq = self.revision_sequence or ""
        if _ALPHA_SEQUENCE_RE.search(seq):
            return "ALPHABETIC"
        if _NUMERIC_SEQUENCE_RE.search(seq):
            return "NUMERIC"
        return None


def normalise_code(value: object) -> str:
    """Upper-case and repair the casing/punctuation variants found in the data.

    The workbook contains 'AfC', 'Re-AFC' and 'RE--IFA' alongside the clean
    forms; all collapse to a single canonical code.
    """
    text = clean(value).upper()
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"^RE-+", "RE-", text)
    return text


@dataclass
class StatusCodeBook:
    """Review + issue codes loaded from the 'Status Codes' sheet."""

    review_codes: dict[str, ReviewCode] = field(default_factory=dict)
    issue_codes: dict[str, IssueCode] = field(default_factory=dict)

    def review(self, value: object) -> Optional[ReviewCode]:
        """Resolve a review code cell.

        The STATUS column holds bare numbers ('2', '10') where the Status Codes
        sheet spells them 'CODE-2'; both forms resolve.
        """
        raw = normalise_code(value)
        if not raw:
            return None
        if raw in self.review_codes:
            return self.review_codes[raw]
        if raw.isdigit() and f"CODE-{int(raw)}" in self.review_codes:
            return self.review_codes[f"CODE-{int(raw)}"]
        return None

    def issue(self, value: object) -> Optional[IssueCode]:
        """Resolve an issue code cell, tolerating RE- prefixes."""
        raw = normalise_code(value)
        if not raw:
            return None
        if raw in self.issue_codes:
            return self.issue_codes[raw]
        base = re.sub(r"^RE-+", "", raw)
        if base in self.issue_codes:
            known = self.issue_codes[base]
            # Synthesise the RE- variant from its base definition.
            return IssueCode(code=raw, description=f"RE-ISSUED: {known.description}",
                             revision_sequence=known.revision_sequence)
        return None

    @classmethod
    def from_rows(cls, rows: list[tuple]) -> "StatusCodeBook":
        """Build from the raw cell rows of the 'Status Codes' sheet.

        Layout (discovered, not assumed): col A/B carry review code +
        description, col D/E/F carry issue code + description + revision
        sequence, under a header row containing 'REVIEW CODE'/'ISSUE CODE'.
        """
        book = cls()
        for row in rows:
            def cell(i: int) -> str:
                return clean(row[i]) if len(row) > i and row[i] is not None else ""

            code_a, desc_a = cell(0), cell(1)
            if re.fullmatch(r"CODE-\d+", code_a.upper()):
                book.review_codes[code_a.upper()] = ReviewCode(code_a.upper(), desc_a)

            code_d, desc_d, seq_d = cell(3), cell(4), cell(5)
            if code_d and not is_null_token(code_d) and code_d.upper() != "ISSUE CODE":
                key = normalise_code(code_d)
                if re.fullmatch(r"(RE-)?[A-Z]{2,4}", key):
                    book.issue_codes[key] = IssueCode(key, desc_d, seq_d)
        return book

    def __len__(self) -> int:  # pragma: no cover - convenience only
        return len(self.review_codes) + len(self.issue_codes)
