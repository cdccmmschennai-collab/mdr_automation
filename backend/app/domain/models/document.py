"""Document domain models.

`DocumentIdentity` is the normalised identity of a document; `DocumentRecord`
is one fully-resolved QatarEnergy-TN row; `VendorRecord` is one TN FROM VENDORS
row and its resolution against QatarEnergy.

These describe MDR concepts, not spreadsheet structures - no row/column
coordinates appear here beyond `source_row`, which is retained purely so a
human can find the row again in the source workbook.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..enums.status_codes import MatchStatus, RevisionStatus


@dataclass(frozen=True)
class DocumentIdentity:
    """A normalised document identity.

    `raw` is exactly what the workbook held; `canonical` is the matching key;
    `alt_key` additionally tolerates the VEN- prefix convention.
    """

    raw: str
    canonical: str
    alt_key: str
    is_null: bool = False

    def __bool__(self) -> bool:
        return not self.is_null and bool(self.canonical)


@dataclass
class DocumentRecord:
    """One QatarEnergy-TN row, fully resolved.

    Note: the pipeline attaches a private `_eligible` attribute to instances of
    this class to carry latest-candidacy between assembly and ranking. It is
    stripped before serialisation. See DECISION_LOG.md.
    """

    source_row: int
    document_identity: str
    qatarenergy_document_no: str
    vendor_document_no: str = ""
    project_document_no: str = ""
    revision: str = ""
    revision_raw: str = ""
    issue_code: str = ""
    review_code: str = ""
    revision_type: str = ""
    revision_rank: int = 0
    revision_band: int = 0
    is_latest_revision: bool = False
    revision_status: str = RevisionStatus.EXCEPTION
    match_status: str = MatchStatus.NOT_MATCHED.value
    match_method: str = ""
    reason: str = ""
    #: Phase 2A DOC TYPE. Empty when no keyword rule covers the document, or
    #: when the run had no rules workbook to load. SOW, IDB and CHECK STATUS
    #: are later phases and have no field here.
    doc_type: str = ""
    #: Which rule decided `doc_type`, e.g. `REQUIRED#51 DOCUMENT_TITLE 'P&ID'`.
    doc_type_rule: str = ""
    #: Which keyword sheet that rule came from: `REQUIRED` / `NOT_REQUIRED`,
    #: empty when no rule matched. Phase 2B reads it, because
    #: `NOT REQUIRED-KEY DOC.WORDS` is itself a scope statement - see
    #: `engine.sow.resolver`.
    doc_type_source: str = ""
    # Context retained for validation and later phases.
    document_title: str = ""
    discipline: str = ""
    originator: str = ""
    issued_date: str = ""
    workbook_latest_flag: str = ""
    #: REMARKS note that this document was renumbered / made non-deliverable.
    #: Informational only - see engine.revision.eligibility.RENUMBERED_RE.
    renumbering_note: bool = False
    is_exception: bool = False
    exception_reason: str = ""


@dataclass
class VendorRecord:
    """One TN FROM VENDORS row and its resolution against QatarEnergy."""

    source_row: int
    vendor: str = ""
    transmittal_no: str = ""
    vendor_document_no: str = ""
    project_document_drawing_no: str = ""
    project_doc_no: str = ""
    revision_raw: str = ""
    revision: str = ""
    description: str = ""
    match_status: str = MatchStatus.NOT_MATCHED.value
    match_method: str = ""
    match_source_field: str = ""
    matched_document: str = ""
    candidates: list[str] = field(default_factory=list)
    reason: str = ""
