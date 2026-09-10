"""Plants as the frontend sees them: a list to choose from.

The application layer behind `GET /api/v1/plants`. A plant is context: the
frontend shows the business identifier and name, keeps the `id`, and sends it
to `POST /api/v1/mdr/upload`. Which rules that plant's submissions are
automated with is decided here on the backend (`Plant.rules_workbook`,
resolved by `rule_set_service.rules_workbook_for_plant` when a step runs) and
is not part of what a client is told - a client that knew would have nothing
legitimate to do with it.

Nothing here creates a plant. Registration stays `submission_service
.register_plant`, run by an operator; the second plant is a row, not a
deployment.
"""

from __future__ import annotations

from ..core.config import Settings, settings as default_settings
from ..infrastructure.persistence.database import session_scope
from ..infrastructure.persistence.models import Plant
from ..infrastructure.persistence.repositories import PlantRepository


def list_plants(*, settings: Settings = default_settings) -> list[Plant]:
    """Every registered plant, ordered by code. A read."""
    with session_scope(settings) as session:
        return PlantRepository(session).list_all()
