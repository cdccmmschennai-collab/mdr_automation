"""FastAPI dependencies.

One dependency: the resolved `Settings`. Routes take it through `Depends` so
a test can point the whole API at a throwaway database and upload directory
with `app.dependency_overrides[get_settings]`, without patching module state.
"""

from __future__ import annotations

from ..core.config import Settings, settings


def get_settings() -> Settings:
    return settings
