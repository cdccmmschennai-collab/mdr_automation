"""FastAPI application.

The API is a boundary, not a layer of logic: it mounts routers and configures
CORS so the frontend can reach it. Authentication, job queues and production
deployment are later delivery phases and are not present.

Two prefixes, and the difference between them is deliberate:

* ``/api`` - operational endpoints. ``/api/health`` is for a load balancer, a
  deploy script and a monitor. Those consumers are not product clients and must
  not be made to follow the product API's version when it moves, so health is
  unversioned and stays that way.
* ``/api/v1`` - the product API. Versioned at the boundary and nowhere else:
  there is no ``services/v1`` or ``domain/v1``, and there will not be. ``v1`` is
  the initial stable contract; ``v2`` is created only by a genuinely
  backward-incompatible change, and backward-compatible additions stay in v1.

`GET /api/mdr/summary` existed until Delivery Phase 2 and has been removed
rather than left alongside the versioned routes - see
`docs/architecture/API_ARCHITECTURE.md`. The CLI (`mdr-engine`) still provides
that capability locally.

Run with:

    uvicorn app.main:app --reload      # from backend/
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes import health, mdr_v1, plants_v1
from .core.config import settings
from .core.logging import configure_logging

#: Operational endpoints. Never versioned.
API_PREFIX = "/api"

#: The public product API. See the module docstring for the versioning policy.
API_V1_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="MDR Automation Tool",
        version=__version__,
        description=(
            "MDR automation: upload, extract, automate, summary, download, "
            "and the plants a submission can belong to. Product endpoints "
            "live under /api/v1; /api/health is operational and unversioned."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(mdr_v1.router, prefix=API_V1_PREFIX)
    app.include_router(plants_v1.router, prefix=API_V1_PREFIX)
    return app


app = create_app()
