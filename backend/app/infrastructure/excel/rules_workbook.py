"""The keyword-rules workbook adapter.

Everything the backend knows about where the DOC TYPE keywords sit in
`INPUT-KEYWORDS  FOR MDR TOOL.xlsx` lives here. It hands the engine plain
`RuleRow` tuples; the engine never opens the file.

Two of the four sheets are consumed. `DOCUMENT TYPE` (DOKAR codes and SOW
strings) and `FOLDER-UPDATE` belong to later phases and are deliberately not
read.

Opened read-only; never written to.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...engine.classification.rules import NOT_REQUIRED, REQUIRED, RuleRow
from .workbook_reader import SheetTable, read_table

REQUIRED_SHEET = ("REQUIRED-KEY DOC.WORDS",)
NOT_REQUIRED_SHEET = ("NOT REQUIRED-KEY DOC.WORDS",)

#: Headers used to score which row is the header row.
RULES_EXPECTED = ["DOC NUMBER- KEYWORD", "DOC DESC- KEYWORDS", "DOC TYPE"]


@dataclass(frozen=True)
class RulesDiscovery:
    """What was found when the rules workbook was loaded."""

    required_sheet: str
    required_rules: int
    not_required_sheet: str
    not_required_rules: int


class RulesWorkbookReader:
    """Read-only access to the two keyword sheets Phase 2A consumes."""

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
