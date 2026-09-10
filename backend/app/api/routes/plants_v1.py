"""The `/api/v1/plants` product API.

    GET /api/v1/plants        the plants a submission can belong to

One read endpoint, added so a frontend can offer a plant selector without
knowing any UUID in advance: it shows `code` and `name`, keeps `id`, and sends
`id` as `plant_id` to `POST /api/v1/mdr/upload`. Selecting a plant changes
nothing but that identifier; which rules the plant's submissions are automated
with is the backend's decision and is not exposed here.

Same discipline as `mdr_v1`: read the request, call one service function,
shape the result. No SQL, no spreadsheet, no MDR rule.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...core.config import Settings
from ...services import plant_service
from ..deps import get_settings
from ..schemas.plants import PlantResponse

router = APIRouter(prefix="/plants", tags=["plants"])


@router.get("", response_model=list[PlantResponse],
            summary="List the plants a submission can belong to")
def list_plants(settings: Settings = Depends(get_settings)
                ) -> list[PlantResponse]:
    """Every registered plant, ordered by code. A read: nothing is created."""
    return [PlantResponse(id=plant.id, code=plant.code, name=plant.name)
            for plant in plant_service.list_plants(settings=settings)]
