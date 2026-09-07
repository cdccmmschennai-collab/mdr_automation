"""Shared test configuration.

Puts `backend/` on the path so `app.*` and `tests.support.*` import cleanly no
matter which directory pytest is invoked from, and provides the single
Phase 1 run that the integration and regression suites share.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402

from app.services.mdr_pipeline import MdrEngine  # noqa: E402
from tests.support.workbook import PHASE1_WORKBOOK  # noqa: E402


@pytest.fixture(scope="session")
def result():
    """One Phase 1 run over the real workbook, shared by every suite.

    Session-scoped because the run takes several seconds and no test mutates
    it. Tests that must observe a *fresh* run (the source-integrity check)
    construct their own engine.
    """
    return MdrEngine(PHASE1_WORKBOOK).run()
