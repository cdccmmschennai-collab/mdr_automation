"""Latest-revision determination, driven by cases taken from the real data."""

import pytest

from mdr_engine.engine import DocumentRecord, MdrEngine, RevisionStatus
from mdr_engine.identity import canonicalise
from mdr_engine.revision import parse_revision


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
    MdrEngine._determine_latest(records)
    return records


def latest_of(records):
    return [r for r in records if r.revision_status == RevisionStatus.LATEST]


class TestBasicSequencing:
    def test_highest_numeric_revision_wins(self):
        g = resolve([rec("D1", "0"), rec("D1", "1"), rec("D1", "2")])
        assert [r.revision for r in latest_of(g)] == ["2"]

    def test_multi_digit_revision_wins_over_single_digit(self):
        g = resolve([rec("D1", "9"), rec("D1", "10")])
        assert latest_of(g)[0].revision == "10"

    def test_single_revision_document_is_latest(self):
        g = resolve([rec("D1", "0")])
        assert g[0].revision_status == RevisionStatus.LATEST

    def test_older_revisions_are_marked_old(self):
        g = resolve([rec("D1", "0"), rec("D1", "1")])
        old = [r for r in g if r.revision_status == RevisionStatus.OLD]
        assert [r.revision for r in old] == ["0"]


class TestAlphaOverNumeric:
    def test_alpha_beats_numeric(self):
        """REV 0,1,2,A,B -> latest is B."""
        g = resolve([rec("D1", x) for x in ["0", "1", "2", "A", "B"]])
        assert latest_of(g)[0].revision == "B"

    def test_real_case_4391_MGEN_1_50_0103_001(self):
        """From the workbook: 0,1,2,A,B,C with B marked L and C unprocessed."""
        g = resolve([rec("4391-MGEN-1-50-0103-001", x)
                     for x in ["0", "1", "2", "A", "B", "C"]])
        assert latest_of(g)[0].revision == "C"

    def test_numeric_five_loses_to_letter_a(self):
        """4391-MTY-6-17-0006: revisions 0..5 then A - A is latest."""
        g = resolve([rec("D", x) for x in ["0", "1", "2", "3", "4", "5", "A"]])
        assert latest_of(g)[0].revision == "A"


class TestAsBuilt:
    def test_z_never_wins_latest(self):
        """MEWTP-style group: ...,C(L),Z(ASB). C stays latest, Z is as-built."""
        g = resolve([rec("D", x) for x in ["0", "1", "A", "B", "C", "Z"]])
        assert latest_of(g)[0].revision == "C"
        z = next(r for r in g if r.revision == "Z")
        assert z.revision_status == RevisionStatus.AS_BUILT
        assert not z.is_latest_revision

    def test_as_built_is_not_reported_as_an_exception(self):
        g = resolve([rec("D", "A"), rec("D", "Z")])
        z = next(r for r in g if r.revision == "Z")
        assert not z.is_exception


class TestWithdrawn:
    def test_withdrawn_top_revision_does_not_win(self):
        """4391-MTY-4-15-0004: rev A withdrawn, so rev 1 remains latest."""
        g = resolve([rec("D", "0"), rec("D", "1"), rec("D", "A", withdrawn=True)])
        assert latest_of(g)[0].revision == "1"

    def test_withdrawn_row_is_flagged_as_an_exception(self):
        g = resolve([rec("D", "0"), rec("D", "A", withdrawn=True)])
        w = next(r for r in g if r.revision == "A")
        assert w.is_exception
        assert "WITHDRAWN" in w.exception_reason


class TestAmbiguityAndExceptions:
    def test_duplicate_top_revision_is_an_exception_not_a_guess(self):
        g = resolve([rec("D", "1", row=1), rec("D", "1", row=2)])
        assert latest_of(g) == []
        assert all(r.revision_status == RevisionStatus.EXCEPTION for r in g)
        assert all("ambiguous" in r.exception_reason for r in g)

    def test_group_with_no_parseable_revision_is_an_exception(self):
        g = resolve([rec("D", "??"), rec("D", "-")])
        assert latest_of(g) == []
        assert all(r.is_exception for r in g)

    def test_unparseable_row_never_wins_over_a_valid_one(self):
        g = resolve([rec("D", "2"), rec("D", "??")])
        assert latest_of(g)[0].revision == "2"


class TestExplainability:
    def test_every_record_carries_a_reason(self):
        g = resolve([rec("D", "0"), rec("D", "1"), rec("D", "Z")])
        assert all(r.reason for r in g)

    def test_old_row_names_the_revision_that_supersedes_it(self):
        g = resolve([rec("D", "0"), rec("D", "B")])
        old = next(r for r in g if r.revision == "0")
        assert "'B'" in old.reason

    def test_documents_are_grouped_independently(self):
        g = resolve([rec("A1", "0"), rec("A1", "1"), rec("B2", "0")])
        assert len(latest_of(g)) == 2


class TestSeparateDocumentsNotMerged:
    def test_suffixed_document_is_a_different_document(self):
        """MEWTP-8-83-0001 and -0001-001 must not be merged into one group."""
        g = resolve([rec("MEWTP-8-83-0001", "0"),
                     rec("MEWTP-8-83-0001-001", "0")])
        assert len(latest_of(g)) == 2
