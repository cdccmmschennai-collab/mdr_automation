"""The keyword-rules workbook adapter.

Everything the backend knows about where the DOC TYPE keywords sit in
`INPUT-KEYWORDS  FOR MDR TOOL.xlsx` lives here. It hands the engine plain
`RuleRow` tuples; the engine never opens the file.

Three of the four sheets are consumed: the two keyword sheets for Phase 2A's
DOC TYPE, and `DOCUMENT TYPE` for Phase 2B's DOC IS REQUIRED SOW.
`FOLDER-UPDATE` belongs to a later phase and is deliberately not read.

Opened read-only; never written to.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...engine.classification.rules import NOT_REQUIRED, REQUIRED, RuleRow
from ...engine.sow.rules import SowRuleRow
from .workbook_reader import SheetTable, read_table

REQUIRED_SHEET = ("REQUIRED-KEY DOC.WORDS",)
NOT_REQUIRED_SHEET = ("NOT REQUIRED-KEY DOC.WORDS",)
DOCUMENT_TYPE_SHEET = ("DOCUMENT TYPE",)

#: Headers used to score which row is the header row.
RULES_EXPECTED = ["DOC NUMBER- KEYWORD", "DOC DESC- KEYWORDS", "DOC TYPE"]
SOW_EXPECTED = ["S NO", "DOCUMENT TYPE", "DOKAR", "DOCUMENT SOW"]


@dataclass(frozen=True)
class RulesDiscovery:
    """What was found when the rules workbook was loaded."""

    required_sheet: str
    required_rules: int
    not_required_sheet: str
    not_required_rules: int


@dataclass(frozen=True)
class SowDiscovery:
    """What was found when the `DOCUMENT TYPE` sheet was loaded."""

    sheet_name: str
    header_row: int
    rule_count: int


class RulesWorkbookReader:
    """Read-only access to the rules sheets Phases 2A and 2B consume."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    def read_rule_rows(self) -> tuple[list[RuleRow], RulesDiscovery]:
        required, req_table = self._read_sheet(REQUIRED_SHEET, REQUIRED)
        not_required, not_req_table = self._read_sheet(
            NOT_REQUIRED_SHEET, NOT_REQUIRED)
        discovery = RulesDiscovery(
            required_sheet=req_table.name, required_rules=len(required),
            not_required_sheet=not_req_table.name,
            not_required_rules=len(not_required),
        )
        return required + not_required, discovery

    def _read_sheet(self, candidates: tuple[str, ...],
                    source: str) -> tuple[list[RuleRow], SheetTable]:
        table = read_table(self.path, candidates, RULES_EXPECTED)
        c_number = table.index("DOC NUMBER- KEYWORD")
        c_title = table.index("DOC DESC- KEYWORDS")
        c_type = table.index("DOC TYPE")

        rows = [
            RuleRow(
                source=source,
                row=table.excel_row_number(i),
                number_keyword=table.value(row, c_number),
                title_keyword=table.value(row, c_title),
                doc_type=table.value(row, c_type),
            )
            for i, row in enumerate(table.rows)
        ]
        # A row with no DOC TYPE states no rule; the engine drops those too,
        # but dropping them here keeps the discovery counts honest.
        return [r for r in rows if r.doc_type], table

    def read_sow_rows(self) -> tuple[list[SowRuleRow], SowDiscovery]:
        """Read the `DOCUMENT TYPE` sheet: document type, DOKAR, DOCUMENT SOW.

        The sheet has a blank spacer row under its header, which `read_table`
        already discards along with any other empty row.
        """
        table = read_table(self.path, DOCUMENT_TYPE_SHEET, SOW_EXPECTED)
        c_type = table.index("DOCUMENT TYPE")
        c_dokar = table.index("DOKAR")
        c_sow = table.index("DOCUMENT SOW")

        rows = [
            SowRuleRow(
                row=table.excel_row_number(i),
                document_type=table.value(row, c_type),
                dokar=table.value(row, c_dokar),
                sow=table.value(row, c_sow),
            )
            for i, row in enumerate(table.rows)
        ]
        # A row with no SOW value states no rule.
        rows = [r for r in rows if r.sow]
        return rows, SowDiscovery(sheet_name=table.name,
                                  header_row=table.header_row,
                                  rule_count=len(rows))
