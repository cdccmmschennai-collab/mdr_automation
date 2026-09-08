"""Verbatim `DOCUMENT TYPE` sheet rows for the SOW unit tests.

Every row below is copied exactly from the `DOCUMENT TYPE` sheet of
`data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`, including its sheet row number
(the sheet has a blank spacer row at row 2, so the data starts at row 3).
Nothing here is invented: `tests/integration/test_sow_workbook.py` reads the
real workbook and asserts every one of these rows is still present, at that
row, with that SOW string.

Keeping the fixture separate from the file means the unit suite runs without
the workbook while still testing the workbook's actual rules.
"""

from __future__ import annotations

from app.engine.sow.resolver import SowResolver
from app.engine.sow.rules import SowRuleBook, SowRuleRow

#: The whole `DOCUMENT TYPE` sheet, in workbook order.
DOCUMENT_TYPE_ROWS: tuple[SowRuleRow, ...] = (
    SowRuleRow(3, "EQPT DATA SHEET", "MDS", "YES-MTL/DOC IDB"),
    SowRuleRow(4, "SPIR", "MIR", "YES-FMTL/MTL/BOM/DOC IDB"),
    SowRuleRow(5, "LAYOUT DIAGRAM", "MLD", "YES-FMTL/MTL/DOC IDB"),
    SowRuleRow(6, "LOOP DIAGRAM", "MLP", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
    SowRuleRow(7, "EQPT BOM (MFR'S PARTS LIST)", "MMC", "YES-MTL/BOM/DOC IDB"),
    SowRuleRow(8, "MANUFACTURER DRGS", "MMD", "YES-MTL/DOC IDB"),
    SowRuleRow(9, "OPERATION & MAINT MANUAL", "MOM", "YES-PM IDB/DOC IDB"),
    SowRuleRow(10, "SINGLE LINE DRGS", "MSL", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
    SowRuleRow(11, "VENDOR DRGS", "MVD", "YES-MTL/DOC IDB"),
    SowRuleRow(12, "P & I DRGS", "MXB", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
    SowRuleRow(13, "CROSS SECTIONAL DRGS", "MXS", "YES-MTL/DOC IDB"),
    SowRuleRow(14, "SPECIFICATION SHEET", "MSS", "YES-MTL/DOC IDB"),
    SowRuleRow(15, "TEST CERTIFICATE", "MTC", "YES-MTL/DOC IDB"),
    SowRuleRow(16, "NAME PLATE PHOTOGRAPHY", "MNP", "YES-MTL/DOC IDB"),
    SowRuleRow(17, "SPADE DRAWING", "MXX", "YES-DOC IDB"),
    SowRuleRow(18, "CAUSE & EFFECT", "MCE", "YES-DOC IDB"),
    SowRuleRow(19, "SIL STUDY REPORT", "MSI", "YES-DOC IDB"),
    SowRuleRow(20, "HAZOP STUDY REPORT", "MHR", "YES-DOC IDB"),
    SowRuleRow(21, "ISOMETRIC DRAWING", "MPI", "YES-MTL/DOC IDB"),
    SowRuleRow(22, "PIPING SPECIFICATION", "MPS", "YES-MTL/DOC IDB"),
    SowRuleRow(23, "BLOCK DIAGRAM", "MBD", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
    SowRuleRow(24, "SCHEMATIC DIAGRAM", "MSD", "YES-FMTL/MTL/HIERARCHY/DOC IDB"),
)

#: DOKAR -> DOCUMENT SOW, as the sheet states it. The expected values the
#: resolver tests assert against.
EXPECTED_SOW: dict[str, str] = {r.dokar: r.sow for r in DOCUMENT_TYPE_ROWS}


def sample_sow_rulebook() -> SowRuleBook:
    return SowRuleBook.from_rows(DOCUMENT_TYPE_ROWS)


def sample_sow_resolver() -> SowResolver:
    return SowResolver(sample_sow_rulebook())
