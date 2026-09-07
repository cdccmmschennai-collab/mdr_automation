"""FastAPI application.

The API is a boundary, not a layer of logic: it mounts routers and configures
CORS so the frontend can reach it. Authentication, uploads, job queues and
production deployment are Phase 7 and are not present.

Run with:

    uvicorn app.main:app --reload      # from backend/
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import health, mdr
from .core.config import settings
from .core.logging import configure_logging

API_PREFIX = "/api"


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="MDR Automation Tool",
        version="0.1.0",
        description="Phase 1: document identity, matching and revision.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(mdr.router, prefix=API_PREFIX)
    return app


app = create_app()
