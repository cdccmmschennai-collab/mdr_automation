"""Plant persistence."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Plant


class PlantRepository:
    """Read and write `plants`."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, code: str, name: str) -> Plant:
        plant = Plant(code=code, name=name)
        self.session.add(plant)
        self.session.flush()          # assign the PK without committing
        return plant

    def get(self, plant_id: uuid.UUID) -> Optional[Plant]:
        return self.session.get(Plant, plant_id)

    def by_code(self, code: str) -> Optional[Plant]:
        return self.session.execute(
            select(Plant).where(Plant.code == code)).scalar_one_or_none()

    def get_or_create(self, code: str, name: str) -> Plant:
        """Fetch the plant with this code, creating it if it is not there yet.

        Not race-free, and does not pretend to be: two concurrent callers can
        both miss and both insert, and the unique index on `code` then rejects
        the loser rather than producing a duplicate plant. That is the correct
        outcome for a table written once per plant.
        """
        return self.by_code(code) or self.add(code, name)

    def list_all(self) -> list[Plant]:
        return list(self.session.execute(
            select(Plant).order_by(Plant.code)).scalars())
