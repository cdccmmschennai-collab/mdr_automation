"""Phase 1 orchestration: load -> normalise -> sequence -> classify -> emit."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional

from .identity import DocumentIdentity, clean, is_null_token, normalise_identity
from .matching import MatchResult, MatchStatus, QeIndex, match_vendor_row
from .revision import Revision, RevisionBand, parse_revision
from .status_codes import StatusCodeBook
from .workbook_io import SheetTable, read_table

QE_SHEET = ("QatarEnergy-TN", "QatarEnergy TN", "QE-TN")
VENDOR_SHEET = ("TN FROM VENDORS", "TN FROM VENDOR")
STATUS_SHEET = ("Status Codes", "StatusCodes")

QE_EXPECTED = ["DOCUMENT NO.", "REV", "DISCIPLINE", "DOCUMENT TITLE",
               "ISSUED STATUS IN PDMS", "LATEST/ NOT LATEST"]
VENDOR_EXPECTED = ["VENDOR/ SUBCON", "TRANSMITTAL NO.", "Vendor Document No.",
                   "PROJECT DOCUMENT/ DRAWING NO.", "REV", "PROJECT DOC NO."]

#: Free-text markers that withdraw a submission from latest candidacy.
#: Evidenced by 4391-MTY-4-15-0004 rev A (status 'WITHDRAWIN'), the single
#: genuine counter-example to the revision ordering in the reference data.
WITHDRAWN_MARKERS = ("WITHDRAW",)

#: Remarks noting that the document was renumbered or reclassified as
#: non-deliverable.
#:
#: This is recorded as CONTEXT ONLY and deliberately does NOT affect latest
#: determination. It was tested as an exclusion rule and rejected: of the 182
#: rows it matches, 128 are NL and 50 are L against a 64% NL base rate, so it
#: carries almost no signal - and in every case examined the renumbered row was
#: itself the one the workbook marked latest. Useful for exception review and
#: for the later identity/DOC TYPE phases; not a revision rule.
RENUMBERED_RE = re.compile(
    r"(DOC(?:UMENT)?\.?\s*(?:REF\.?\s*)?NO\.?[^.]{0,30}?"
    r"(?:UPDATED|CHANGED|REVISED))"
    r"|(?:NUMBER\s+REVISED)"
    r"|(NON[-\s]?DELIVERABLE)",
    re.IGNORECASE,
)


class RevisionStatus(str):
    LATEST = "LATEST"
    OLD = "OLD"
    #: An as-built (Z) issue. A known, well-understood category that sits
    #: outside the A,B,C.. sequence - not an error needing review.
    AS_BUILT = "AS_BUILT"
    EXCEPTION = "EXCEPTION"


@dataclass
class DocumentRecord:
    """One QatarEnergy-TN row, fully resolved."""

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
    # Context retained for validation and later phases.
    document_title: str = ""
    discipline: str = ""
    originator: str = ""
    issued_date: str = ""
    workbook_latest_flag: str = ""
    #: REMARKS note that this document was renumbered / made non-deliverable.
    #: Informational only - see RENUMBERED_RE.
    renumbering_note: bool = False
    is_exception: bool = False
    exception_reason: str = ""


@dataclass
class VendorRecord:
    """One TN FROM VENDORS row and its resolution against QE."""

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


@dataclass
class EngineResult:
    documents: list[DocumentRecord] = field(default_factory=list)
    vendor_rows: list[VendorRecord] = field(default_factory=list)
    status_codes: Optional[StatusCodeBook] = None
    discovery: dict = field(default_factory=dict)

    @property
    def exceptions(self) -> list[DocumentRecord]:
        return [d for d in self.documents if d.is_exception]

    def summary(self) -> dict:
        groups = {d.document_identity for d in self.documents if d.document_identity}
        match_counts: dict[str, int] = defaultdict(int)
        for v in self.vendor_rows:
            match_counts[v.match_status] += 1
        return {
            "document_rows": len(self.documents),
            "distinct_documents": len(groups),
            "latest_rows": sum(1 for d in self.documents
                               if d.revision_status == RevisionStatus.LATEST),
            "old_rows": sum(1 for d in self.documents
                            if d.revision_status == RevisionStatus.OLD),
            "as_built_rows": sum(1 for d in self.documents
                                 if d.revision_status == RevisionStatus.AS_BUILT),
            "exception_rows": len(self.exceptions),
            "vendor_rows": len(self.vendor_rows),
            "vendor_match_counts": dict(match_counts),
            "review_codes_loaded": len(self.status_codes.review_codes)
            if self.status_codes else 0,
            "issue_codes_loaded": len(self.status_codes.issue_codes)
            if self.status_codes else 0,
        }


class MdrEngine:
    """Phase 1 engine. Reads workbooks; never writes to them."""

    def __init__(self, mdr_workbook: Path):
        self.mdr_workbook = Path(mdr_workbook)
        if not self.mdr_workbook.is_file():
            raise FileNotFoundError(self.mdr_workbook)

    # ---------------------------------------------------------------- loading

    def load_status_codes(self) -> StatusCodeBook:
        table = read_table(self.mdr_workbook, STATUS_SHEET,
                           ["REVIEW CODE FROM QatarEnergy", "ISSUE CODE"])
        # Include the header row itself: the sheet's first data row sits
        # directly under a title row, so pass everything from the top.
        return StatusCodeBook.from_rows(table.rows)

    # --------------------------------------------------------------- pipeline

    def run(self) -> EngineResult:
        result = EngineResult()
        result.status_codes = self.load_status_codes()

        qe = read_table(self.mdr_workbook, QE_SHEET, QE_EXPECTED)
        vendors = read_table(self.mdr_workbook, VENDOR_SHEET, VENDOR_EXPECTED)
        result.discovery = {
            "workbook": str(self.mdr_workbook),
            "qe_sheet": qe.name, "qe_header_row": qe.header_row,
            "qe_data_rows": len(qe.rows),
            "vendor_sheet": vendors.name, "vendor_header_row": vendors.header_row,
            "vendor_data_rows": len(vendors.rows),
        }

        result.documents = self._build_documents(qe, result.status_codes)
        self._determine_latest(result.documents)
        result.vendor_rows = self._build_vendor_rows(vendors, result.documents)
        return result

    # -------------------------------------------------------------- documents

    def _build_documents(self, qe: SheetTable,
                         codes: StatusCodeBook) -> list[DocumentRecord]:
        c_doc = qe.index("DOCUMENT NO.")
        c_rev = qe.index("REV")
        c_issue = qe.index("ISSUED STATUS IN PDMS")
        c_status = qe.index("QatarEnergy/MG/TEN/TEB STATUS", required=False)
        c_final = qe.index("FINAL ISSUE CODES", required=False)
        c_title = qe.index("DOCUMENT TITLE", required=False)
        c_disc = qe.index("DISCIPLINE", required=False)
        c_orig = qe.index("ORGINATOR", "ORIGINATOR", required=False)
        c_date = qe.index("ISSUED DATE to QE", required=False)
        c_latest = qe.index("LATEST/ NOT LATEST", required=False)
        c_remarks = qe.index("REMARKS", required=False)
        c_vendor_tn = qe.index("SUBCON/VENDOR TN NO.", required=False)

        records: list[DocumentRecord] = []
        for i, row in enumerate(qe.rows):
            raw_doc = qe.value(row, c_doc)
            if is_null_token(raw_doc):
                continue                       # no identity -> not a document row

            ident = normalise_identity(raw_doc)
            rev = parse_revision(qe.value(row, c_rev))
            issue = codes.issue(qe.value(row, c_issue))
            review = codes.review(qe.value(row, c_status))

            rec = DocumentRecord(
                source_row=qe.excel_row_number(i),
                document_identity=ident.canonical,
                qatarenergy_document_no=ident.raw,
                vendor_document_no=qe.value(row, c_vendor_tn),
                revision=rev.normalised,
                revision_raw=rev.raw,
                issue_code=issue.code if issue else qe.value(row, c_issue).upper(),
                review_code=review.code if review else qe.value(row, c_status),
                revision_type=rev.category,
                revision_rank=rev.ordinal,
                revision_band=int(rev.band),
                document_title=qe.value(row, c_title),
                discipline=qe.value(row, c_disc),
                originator=qe.value(row, c_orig),
                issued_date=qe.value(row, c_date),
                workbook_latest_flag=qe.value(row, c_latest).upper(),
                reason=rev.reason,
            )

            # Signals that remove a row from latest candidacy.
            remarks = qe.value(row, c_remarks)
            haystack = f"{qe.value(row, c_status)} {remarks}".upper()
            rec_withdrawn = any(m in haystack for m in WITHDRAWN_MARKERS)
            # Context only - see RENUMBERED_RE; does not gate eligibility.
            rec.renumbering_note = bool(RENUMBERED_RE.search(remarks))

            if not rev.is_parseable:
                rec.is_exception = True
                rec.exception_reason = (
                    f"revision {rev.raw!r} could not be parsed ({rev.reason})")
            elif rec_withdrawn:
                rec.is_exception = True
                rec.exception_reason = "submission marked WITHDRAWN"
            elif rev.band is RevisionBand.AS_BUILT:
                rec.exception_reason = "as-built (Z) marker: not a sequence revision"

            rec._eligible = rev.eligible_for_latest and not rec_withdrawn  # type: ignore[attr-defined]
            records.append(rec)
        return records

    # ------------------------------------------------------------ latest logic

    @staticmethod
    def _determine_latest(records: list[DocumentRecord]) -> None:
        """Mark the latest revision within each document identity group."""
        groups: dict[str, list[DocumentRecord]] = defaultdict(list)
        for r in records:
            groups[r.document_identity].append(r)

        for identity, group in groups.items():
            eligible = [r for r in group if getattr(r, "_eligible", False)]
            if not eligible:
                for r in group:
                    r.revision_status = RevisionStatus.EXCEPTION
                    r.is_latest_revision = False
                    if not r.exception_reason:
                        r.is_exception = True
                        r.exception_reason = (
                            "no revision in this document group is eligible to be "
                            "the latest")
                continue

            best_key = max((r.revision_band, r.revision_rank) for r in eligible)
            winners = [r for r in eligible
                       if (r.revision_band, r.revision_rank) == best_key]

            for r in group:
                is_winner = r in winners
                r.is_latest_revision = is_winner and len(winners) == 1
                if len(winners) > 1 and is_winner:
                    # Duplicate top revision - refuse to pick one.
                    r.revision_status = RevisionStatus.EXCEPTION
                    r.is_exception = True
                    r.is_latest_revision = False
                    r.exception_reason = (
                        f"{len(winners)} rows share the highest revision "
                        f"{r.revision!r}; latest is ambiguous")
                    r.reason = "AMBIGUOUS_TOP_REVISION"
                elif is_winner:
                    r.revision_status = RevisionStatus.LATEST
                    r.reason = (
                        f"highest revision in group ({len(group)} row(s)); "
                        f"band={RevisionBand(r.revision_band).name} rank={r.revision_rank}")
                elif getattr(r, "_eligible", False):
                    r.revision_status = RevisionStatus.OLD
                    top = winners[0]
                    r.reason = (
                        f"superseded by revision {top.revision!r} "
                        f"(band={RevisionBand(top.revision_band).name})")
                elif r.revision_band == int(RevisionBand.AS_BUILT):
                    r.revision_status = RevisionStatus.AS_BUILT
                    r.is_latest_revision = False
                    r.reason = ("as-built (Z) issue: outside the revision "
                                "sequence, never the latest revision")
                else:
                    r.revision_status = RevisionStatus.EXCEPTION
                    r.is_latest_revision = False
                    r.is_exception = True
                    if not r.exception_reason:
                        r.exception_reason = "row not eligible for latest determination"
                    r.reason = r.exception_reason

    # ----------------------------------------------------------- vendor rows

    @staticmethod
    def _build_vendor_rows(vendors: SheetTable,
                           documents: list[DocumentRecord]) -> list[VendorRecord]:
        index = QeIndex.build(
            normalise_identity(d.qatarenergy_document_no) for d in documents)

        c_vendor = vendors.index("VENDOR/ SUBCON", required=False)
        c_tn = vendors.index("TRANSMITTAL NO.", required=False)
        c_vdoc = vendors.index("Vendor Document No.", required=False)
        c_pdoc = vendors.index("PROJECT DOCUMENT/ DRAWING NO.", required=False)
        c_rev = vendors.index("REV", required=False)
        c_desc = vendors.index("Description", required=False)
        c_pdno = vendors.index("PROJECT DOC NO.", required=False)

        out: list[VendorRecord] = []
        for i, row in enumerate(vendors.rows):
            candidates = {
                "PROJECT_DOCUMENT_DRAWING_NO": vendors.value(row, c_pdoc),
                "PROJECT_DOC_NO": vendors.value(row, c_pdno),
                "VENDOR_DOCUMENT_NO": vendors.value(row, c_vdoc),
            }
            if all(is_null_token(v) for v in candidates.values()):
                if is_null_token(vendors.value(row, c_tn)):
                    continue               # entirely blank / decorative row
            m: MatchResult = match_vendor_row(candidates, index)
            rev = parse_revision(vendors.value(row, c_rev))
            out.append(VendorRecord(
                source_row=vendors.excel_row_number(i),
                vendor=vendors.value(row, c_vendor),
                transmittal_no=vendors.value(row, c_tn),
                vendor_document_no=candidates["VENDOR_DOCUMENT_NO"],
                project_document_drawing_no=candidates["PROJECT_DOCUMENT_DRAWING_NO"],
                project_doc_no=candidates["PROJECT_DOC_NO"],
                revision_raw=rev.raw, revision=rev.normalised,
                description=vendors.value(row, c_desc),
                match_status=m.status.value, match_method=m.match_method,
                match_source_field=m.source_field,
                matched_document=m.matched_document,
                candidates=list(m.candidates), reason=m.reason,
            ))
        return out


# ------------------------------------------------------------------- emitters

def _clean_record(rec) -> dict:
    d = {k: v for k, v in asdict(rec).items() if not k.startswith("_")}
    return d


def write_json(result: EngineResult, path: Path) -> None:
    payload = {
        "summary": result.summary(),
        "discovery": result.discovery,
        "documents": [_clean_record(d) for d in result.documents],
        "vendor_rows": [_clean_record(v) for v in result.vendor_rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def write_csv(rows: Iterable, path: Path) -> None:
    import csv
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = [k for k in _clean_record(rows[0])]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            d = _clean_record(r)
            writer.writerow({k: ("|".join(v) if isinstance(v, list) else v)
                             for k, v in d.items()})
