"""Pipeline orchestration: load -> normalise -> sequence -> classify -> emit.

This is the application layer. It wires the Excel adapters to the engine and
returns an `EngineResult`; it holds no rule of its own beyond the assembly
order. Every business decision it makes is delegated:

* identity          -> engine.identity.normalisation
* revision parsing  -> engine.revision.parsing
* latest candidacy  -> engine.revision.eligibility
* latest ranking    -> engine.revision.ranking
* status codes      -> engine.revision.status_codes
* vendor matching   -> engine.identity.matching
* DOC TYPE          -> engine.classification.classifier      (Phase 2A)

The class is named `MdrEngine` because that is the public entry point Phase 1
established; it is usable with nothing but a workbook path, independently of
the API and the frontend.

`TN FROM VENDORS` rows are resolved against QatarEnergy documents but are not
merged into the document universe - see `settings.vendor_consolidation_enabled`,
which is off, and for which no consolidation code exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..domain.models.document import DocumentRecord, VendorRecord
from ..domain.models.mdr_result import EngineResult
from ..domain.models.revision import RevisionBand
from ..engine.classification.classifier import DocumentClassifier
from ..engine.identity.matching import MatchResult, QeIndex, match_vendor_row
from ..engine.identity.normalisation import is_null_token, normalise_identity
from ..engine.revision.eligibility import has_renumbering_note, is_withdrawn
from ..engine.revision.parsing import parse_revision
from ..engine.revision.ranking import determine_latest
from ..engine.revision.status_codes import StatusCodeBook
from ..infrastructure.excel.mdr_workbook import (
    DocumentSourceRow, MdrWorkbookReader, VendorSourceRow,
)
from .classification_service import build_classifier


class MdrEngine:
    """The MDR pipeline. Reads workbooks; never writes to them."""

    def __init__(self, mdr_workbook: Path, rules_workbook: Optional[Path] = None):
        self.mdr_workbook = Path(mdr_workbook)
        self.reader = MdrWorkbookReader(self.mdr_workbook)
        #: None means "classify nothing" - a run without the rules workbook is
        #: a valid Phase 1 run, and every DOC TYPE simply stays empty.
        rules = rules_workbook or settings.default_rules_workbook()
        self.rules_workbook = Path(rules) if rules else None

    # ---------------------------------------------------------------- loading

    def load_status_codes(self) -> StatusCodeBook:
        return StatusCodeBook.from_rows(self.reader.read_status_code_rows())

    def load_classifier(self) -> Optional[DocumentClassifier]:
        """Build the DOC TYPE classifier, or None when no rules are available."""
        return build_classifier(self.rules_workbook)

    # --------------------------------------------------------------- pipeline

    def run(self) -> EngineResult:
        result = EngineResult()
        result.status_codes = self.load_status_codes()
        classifier = self.load_classifier()

        qe_rows, qe_found = self.reader.read_document_rows()
        vendor_rows, vendor_found = self.reader.read_vendor_rows()
        result.discovery = {
            "workbook": str(self.mdr_workbook),
            "qe_sheet": qe_found.sheet_name, "qe_header_row": qe_found.header_row,
            "qe_data_rows": qe_found.row_count,
            "vendor_sheet": vendor_found.sheet_name,
            "vendor_header_row": vendor_found.header_row,
            "vendor_data_rows": vendor_found.row_count,
            "rules_workbook": str(self.rules_workbook) if classifier else None,
            "classification_rules": len(classifier.rules) if classifier else 0,
        }

        result.documents = self._build_documents(qe_rows, result.status_codes,
                                                 classifier)
        determine_latest(result.documents)
        result.vendor_rows = self._build_vendor_rows(vendor_rows, result.documents)
        return result

    # -------------------------------------------------------------- documents

    @staticmethod
    def _build_documents(rows: list[DocumentSourceRow],
                         codes: StatusCodeBook,
                         classifier: Optional[DocumentClassifier] = None,
                         ) -> list[DocumentRecord]:
        records: list[DocumentRecord] = []
        for row in rows:
            if is_null_token(row.document_no):
                continue                       # no identity -> not a document row

            ident = normalise_identity(row.document_no)
            rev = parse_revision(row.rev)
            issue = codes.issue(row.issued_status_in_pdms)
            review = codes.review(row.qe_status)

            rec = DocumentRecord(
                source_row=row.source_row,
                document_identity=ident.canonical,
                qatarenergy_document_no=ident.raw,
                vendor_document_no=row.vendor_tn_no,
                revision=rev.normalised,
                revision_raw=rev.raw,
                issue_code=issue.code if issue else row.issued_status_in_pdms.upper(),
                review_code=review.code if review else row.qe_status,
                revision_type=rev.category,
                revision_rank=rev.ordinal,
                revision_band=int(rev.band),
                document_title=row.document_title,
                discipline=row.discipline,
                originator=row.originator,
                issued_date=row.issued_date,
                workbook_latest_flag=row.workbook_latest_flag.upper(),
                reason=rev.reason,
            )

            if classifier is not None:
                verdict = classifier.classify(row.document_no, row.document_title)
                rec.doc_type = verdict.doc_type
                rec.doc_type_rule = (verdict.winning_match.describe()
                                     if verdict.winning_match else "")
                # Which keyword sheet decided it. Phase 2B needs this: the
                # not-required sheet states scope, not just a label.
                rec.doc_type_source = verdict.rule_source

            # Signals that remove a row from latest candidacy.
            rec_withdrawn = is_withdrawn(row.qe_status, row.remarks)
            # Context only - see eligibility.RENUMBERED_RE; does not gate
            # eligibility.
            rec.renumbering_note = has_renumbering_note(row.remarks)

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

    # ----------------------------------------------------------- vendor rows

    @staticmethod
    def _build_vendor_rows(rows: list[VendorSourceRow],
                           documents: list[DocumentRecord]) -> list[VendorRecord]:
        index = QeIndex.build(
            normalise_identity(d.qatarenergy_document_no) for d in documents)

        out: list[VendorRecord] = []
        for row in rows:
            candidates = {
                "PROJECT_DOCUMENT_DRAWING_NO": row.project_document_drawing_no,
                "PROJECT_DOC_NO": row.project_doc_no,
                "VENDOR_DOCUMENT_NO": row.vendor_document_no,
            }
            if all(is_null_token(v) for v in candidates.values()):
                if is_null_token(row.transmittal_no):
                    continue               # entirely blank / decorative row
            m: MatchResult = match_vendor_row(candidates, index)
            rev = parse_revision(row.rev)
            out.append(VendorRecord(
                source_row=row.source_row,
                vendor=row.vendor,
                transmittal_no=row.transmittal_no,
                vendor_document_no=candidates["VENDOR_DOCUMENT_NO"],
                project_document_drawing_no=candidates["PROJECT_DOCUMENT_DRAWING_NO"],
                project_doc_no=candidates["PROJECT_DOC_NO"],
                revision_raw=rev.raw, revision=rev.normalised,
                description=row.description,
                match_status=m.status.value, match_method=m.match_method,
                match_source_field=m.source_field,
                matched_document=m.matched_document,
                candidates=list(m.candidates), reason=m.reason,
            ))
        return out
