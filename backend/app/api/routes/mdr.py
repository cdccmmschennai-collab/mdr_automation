"""MDR endpoints.

Phase 1 exposes exactly one capability - the summary of a Phase 1 run over the
configured workbook. The route is a thin adapter: it resolves the workbook,
calls the pipeline and serialises the result. It contains no MDR rule, and it
adds no capability the CLI did not already have.

Endpoints for classification, SOW, IDB, received-check, Excel export and
uploads belong to later phases and are NOT defined here. See
docs/architecture/API_ARCHITECTURE.md.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.config import settings
from ...services.mdr_pipeline import MdrEngine

router = APIRouter(prefix="/mdr", tags=["mdr"])


class SummaryResponse(BaseModel):
    workbook: str
    discovery: dict
    summary: dict


@router.get("/summary", response_model=SummaryResponse)
def summary() -> SummaryResponse:
    """Run the Phase 1 pipeline over the configured workbook and summarise it.

    Synchronous by design: Phase 1 has no job queue, and adding one before it
    is needed would be inventing Phase 7 infrastructure.
    """
    workbook = settings.default_workbook()
    if workbook is None:
        raise HTTPException(
            status_code=404,
            detail=f"no workbook found in {settings.input_current_dir}",
        )
    try:
        result = MdrEngine(workbook).run()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SummaryResponse(workbook=workbook.name, discovery=result.discovery,
                           summary=result.summary())
