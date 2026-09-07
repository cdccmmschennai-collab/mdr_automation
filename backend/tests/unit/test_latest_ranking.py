"""Latest-revision ranking: the general sequencing and explainability rules.

The cases driven by specific anomalies found in the real workbook live in
`tests/regression/test_revision_anomalies.py`.
"""

import pytest

from app.domain.enums.status_codes import RevisionStatus
from tests.support.factories import latest_of, rec, resolve


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
