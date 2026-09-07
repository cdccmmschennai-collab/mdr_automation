"""Builders for latest-revision tests.

`rec` constructs a `DocumentRecord` exactly the way the pipeline's
`_build_documents` does, including the private `_eligible` attribute that
carries latest candidacy into ranking. Keeping this in one place means the unit
and regression suites exercise the same construction the real pipeline uses.
"""

from __future__ import annotations

from app.domain.enums.status_codes import RevisionStatus
from app.domain.models.document import DocumentRecord
from app.engine.identity.normalisation import canonicalise
from app.engine.revision.parsing import parse_revision
from app.engine.revision.ranking import determine_latest


def rec(doc, rev, row=1, withdrawn=False, flag=""):
    """Build a DocumentRecord the way _build_documents does."""
    r = parse_revision(rev)
    d = DocumentRecord(
        source_row=row,
        document_identity=canonicalise(doc),
        qatarenergy_document_no=doc,
        revision=r.normalised, revision_raw=r.raw,
        revision_type=r.category, revision_rank=r.ordinal,
        revision_band=int(r.band), workbook_latest_flag=flag,
    )
    d._eligible = r.eligible_for_latest and not withdrawn
    if withdrawn:
        d.is_exception = True
        d.exception_reason = "submission marked WITHDRAWN"
    return d


def resolve(records):
    determine_latest(records)
    return records


def latest_of(records):
    return [r for r in records if r.revision_status == RevisionStatus.LATEST]
