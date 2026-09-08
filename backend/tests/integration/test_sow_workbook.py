"""The real `DOCUMENT TYPE` sheet still says what the SOW fixture claims.

`tests/support/sow.py` copies the sheet verbatim so the unit suite can run
without the file. This suite reads the actual workbook and holds that copy
honest: same rows, same row numbers, same SOW strings.

It also asserts the workbook is opened read-only - the source file must come
out of a run byte-for-byte unchanged.

Skipped automatically when the rules workbook is absent.
"""

import hashlib

import pytest

from app.infrastructure.excel.rules_workbook import RulesWorkbookReader
from app.services.sow_service import build_resolver
from tests.support.sow import DOCUMENT_TYPE_ROWS, EXPECTED_SOW
from tests.support.workbook import RULES_WORKBOOK, requires_rules_workbook

pytestmark = requires_rules_workbook


@pytest.fixture(scope="module")
def sow_rows():
    rows, _ = RulesWorkbookReader(RULES_WORKBOOK).read_sow_rows()
    return rows


@pytest.fixture(scope="module")
def discovery():
    _, disc = RulesWorkbookReader(RULES_WORKBOOK).read_sow_rows()
    return disc


class TestDiscovery:
    def test_the_document_type_sheet_is_found(self, discovery):
        assert discovery.sheet_name == "DOCUMENT TYPE"

    def test_its_header_is_the_first_row(self, discovery):
        assert discovery.header_row == 1

    def test_it_states_twenty_two_rules(self, discovery):
        assert discovery.rule_count == 22


class TestTheFixtureMatchesTheWorkbook:
    def test_every_fixture_row_is_present_verbatim(self, sow_rows):
        assert list(sow_rows) == list(DOCUMENT_TYPE_ROWS)

    def test_the_spacer_row_does_not_shift_the_row_numbers(self, sow_rows):
        """The sheet has a blank row 2, so its data starts at row 3."""
        assert [r.row for r in sow_rows] == list(range(3, 25))

    @pytest.mark.parametrize("dokar,sow", sorted(EXPECTED_SOW.items()))
    def test_each_dokar_still_carries_its_sow_string(self, sow_rows, dokar, sow):
        assert {r.dokar: r.sow for r in sow_rows}[dokar] == sow


class TestBuiltFromTheRealWorkbook:
    def test_the_resolver_builds_from_the_workbook(self):
        resolver = build_resolver(RULES_WORKBOOK)
        assert resolver is not None
        assert resolver.resolve("MDS").sow == "YES-MTL/DOC IDB"

    def test_it_answers_for_every_dokar_the_sheet_defines(self):
        resolver = build_resolver(RULES_WORKBOOK)
        assert all(resolver.resolve(d).is_resolved for d in EXPECTED_SOW)


class TestSourceIntegrity:
    def test_reading_the_sow_rules_does_not_change_the_workbook(self):
        before = hashlib.sha256(RULES_WORKBOOK.read_bytes()).hexdigest()
        RulesWorkbookReader(RULES_WORKBOOK).read_sow_rows()
        after = hashlib.sha256(RULES_WORKBOOK.read_bytes()).hexdigest()
        assert before == after
