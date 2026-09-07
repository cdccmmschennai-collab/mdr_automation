"""Verbatim rules-workbook rows for the classification unit tests.

Every row below is copied exactly from
`data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`, including its sheet row number,
its `KEYWORD NOT APPLICABLE` markers and the lower-case `or` in row 21. Nothing
here is invented: `tests/integration/test_rules_workbook.py` reads the real
workbook and asserts every one of these rows is still present, byte for byte,
at that row.

Keeping the fixture separate from the file means the unit suite runs without
the workbook while still testing the workbook's actual rules.
"""

from __future__ import annotations

from app.engine.classification.classifier import DocumentClassifier
from app.engine.classification.rules import RuleBook, RuleRow

#: A representative slice of REQUIRED-KEY DOC.WORDS and
#: NOT REQUIRED-KEY DOC.WORDS, in workbook order.
SAMPLE_RULE_ROWS: tuple[RuleRow, ...] = (
    RuleRow("REQUIRED", 10, "KEYWORD NOT APPLICABLE", "*P&ID*LEGEND*", "LGD"),
    RuleRow("REQUIRED", 13, "-13-XXXX", "KEYWORD NOT APPLICABLE", "MDS"),
    RuleRow("REQUIRED", 14, "KEYWORD NOT APPLICABLE", "DATASHEET", "MDS"),
    RuleRow("REQUIRED", 15, "KEYWORD NOT APPLICABLE", "DATA SHEET", "MDS"),
    RuleRow("REQUIRED", 16, "-43-XXXX", "KEYWORD NOT APPLICABLE", "MIR"),
    RuleRow("REQUIRED", 17, "KEYWORD NOT APPLICABLE", "SPIR", "MIR"),
    RuleRow("REQUIRED", 18, "KEYWORD NOT APPLICABLE", "SPARE PARTS", "MIR"),
    RuleRow("REQUIRED", 21, "KEYWORD NOT APPLICABLE",
            "LIGHTING LAYOUT or LIGHTNING LAYOUT", "MLD"),
    RuleRow("REQUIRED", 29, "KEYWORD NOT APPLICABLE", "*LAYOUT*PLAN*", "MLD"),
    RuleRow("REQUIRED", 30, "KEYWORD NOT APPLICABLE", "LOOP DIAGRAM", "MLP"),
    RuleRow("REQUIRED", 34, "KEYWORD NOT APPLICABLE", "BILL OF MATERIAL", "MMC"),
    RuleRow("REQUIRED", 43, "KEYWORD NOT APPLICABLE", "SLD", "MSL"),
    RuleRow("REQUIRED", 44, "KEYWORD NOT APPLICABLE", "SINGLE LINE", "MSL"),
    RuleRow("REQUIRED", 47, "KEYWORD NOT APPLICABLE", "TEST CERTIFICATE", "MTC"),
    RuleRow("REQUIRED", 48, "KEYWORD NOT APPLICABLE", "HOOK-UP", "MVA"),
    RuleRow("REQUIRED", 49, "KEYWORD NOT APPLICABLE", "HOOK UP", "MVA"),
    RuleRow("REQUIRED", 50, "KEYWORD NOT APPLICABLE", "HOOKUP", "MVA"),
    RuleRow("REQUIRED", 51, "KEYWORD NOT APPLICABLE", "P&ID", "MXB"),
    RuleRow("REQUIRED", 55, "KEYWORD NOT APPLICABLE", "CROSS SECTION", "MXS"),
    RuleRow("REQUIRED", 70, "-MS-", "*MATERIAL*SUBMITTAL*", "MATERIAL SUBMITTAL"),
    RuleRow("NOT_REQUIRED", 2, "KEYWORD NOT APPLICABLE", "PLAN", "PLAN"),
    RuleRow("NOT_REQUIRED", 3, "KEYWORD NOT APPLICABLE", "PLOT PLAN", "PLOT PLAN"),
    RuleRow("NOT_REQUIRED", 4, "KEYWORD NOT APPLICABLE", "LAYOUT PLAN", "LAYOUT"),
    RuleRow("NOT_REQUIRED", 14, "-TQ-", "KEYWORD NOT APPLICABLE",
            "TECHNICAL QUERY"),
    RuleRow("NOT_REQUIRED", 15, "KEYWORD NOT APPLICABLE", "TECHNICAL QUERY",
            "TECHNICAL QUERY"),
    RuleRow("NOT_REQUIRED", 16, "-CV-", "KEYWORD NOT APPLICABLE", "CV"),
    RuleRow("NOT_REQUIRED", 17, "KEYWORD NOT APPLICABLE", "*CV*", "CV"),
    RuleRow("NOT_REQUIRED", 18, "-AR-", "AUDIT", "AUDIT REPORT"),
    RuleRow("NOT_REQUIRED", 19, "-PQD-", "KEYWORD NOT APPLICABLE",
            "PREQUALIFICATION"),
    RuleRow("NOT_REQUIRED", 20, "-WPR-", "WEEKLY PROGRESS REPORT",
            "WEEKLY PROGRESS REPORT"),
    RuleRow("NOT_REQUIRED", 22, "-NCR-", "KEYWORD NOT APPLICABLE",
            "NON CONFORMANCE REPORT"),
    RuleRow("NOT_REQUIRED", 29, "KEYWORD NOT APPLICABLE", "*METHOD*STATEMENT*",
            "METHOD STATEMENT"),
    RuleRow("NOT_REQUIRED", 30, "KEYWORD NOT APPLICABLE", "*SHOP*DRAWING*",
            "SHOP DRAWING"),
)


def sample_rulebook() -> RuleBook:
    return RuleBook.from_rows(SAMPLE_RULE_ROWS)


def sample_classifier() -> DocumentClassifier:
    return DocumentClassifier(sample_rulebook())
