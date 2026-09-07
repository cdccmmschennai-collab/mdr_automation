"""Health endpoint.

Deliberately trivial: it exists so the frontend can prove the API boundary
works end to end without any MDR business logic being involved.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    phase: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", phase="1")
