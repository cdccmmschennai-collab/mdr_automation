"""MDR Automation Tool - Phase 1 engine.

Scope (Phase 1 only): workbook/sheet/column discovery, document identity
normalisation, QatarEnergy-TN <-> TN FROM VENDORS matching, Status Code
interpretation, revision normalisation/sequencing and latest-revision
determination, emitted as a machine-readable result.

The engine NEVER writes to the source workbooks; every workbook is opened
read-only.
"""

__version__ = "0.1.0"

from .identity import DocumentIdentity, canonicalise, normalise_identity
from .revision import Revision, RevisionBand, parse_revision
from .status_codes import IssueCode, ReviewCode, StatusCodeBook
from .engine import MdrEngine, EngineResult, DocumentRecord

__all__ = [
    "DocumentIdentity",
    "canonicalise",
    "normalise_identity",
    "Revision",
    "RevisionBand",
    "parse_revision",
    "IssueCode",
    "ReviewCode",
    "StatusCodeBook",
    "MdrEngine",
    "EngineResult",
    "DocumentRecord",
]
