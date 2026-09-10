"""The `/api/v1/plants` contract.

One shape: what a client needs to offer a plant selector and to make an
upload. `id` is the value `POST /api/v1/mdr/upload` takes as `plant_id`;
`code` and `name` are what a person is shown. Nothing about which rules the
plant uses is here - that is decided on the backend when a submission is
processed, and a client has no use for it.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class PlantResponse(BaseModel):
    """One registered plant."""

    id: uuid.UUID = Field(
        description="Identifier to send as `plant_id` on upload.")
    code: str = Field(
        description="The plant's business identifier, e.g. a project number.")
    name: str = Field(description="Display name.")
