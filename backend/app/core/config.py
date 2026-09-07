"""Centralised configuration.

Every path and tunable the backend needs, resolved once, overridable by
environment variable. No credentials, no secrets and no production paths are
baked in here: the defaults are repository-relative, and a deployment supplies
its own values through the environment (see `.env.example`).

Deliberately plain: a frozen dataclass and `os.environ`, not a settings
framework. Phase 1 needs nothing more.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo
REPO_ROOT = Path(__file__).resolve().parents[3]

ENV_PREFIX = "MDR_"


def _env_path(name: str) -> Optional[Path]:
    value = os.environ.get(ENV_PREFIX + name, "").strip()
    return Path(value).expanduser() if value else None


@dataclass(frozen=True)
class Settings:
    """Resolved backend configuration."""

    repo_root: Path
    data_dir: Path
    log_level: str
    cors_origins: tuple[str, ...]

    #: Whether TN FROM VENDORS rows are merged into the QatarEnergy-TN
    #: processing universe. Off for this plant: the current business rule is
    #: that the two sheets stay separate, and Phase 1 matching resolves vendor
    #: rows against QatarEnergy documents without consolidating them. A future
    #: plant may need it, which is why the switch exists; nothing reads it as
    #: True today and no consolidation code exists.
    vendor_consolidation_enabled: bool = False

    # -- data locations ----------------------------------------------------

    @property
    def input_current_dir(self) -> Path:
        """Workbooks currently being processed."""
        return self.data_dir / "input" / "current"

    @property
    def input_archive_dir(self) -> Path:
        return self.data_dir / "input" / "archive"

    @property
    def reference_working_dir(self) -> Path:
        """The manually prepared working file used to validate the engine."""
        return self.data_dir / "reference" / "working"

    @property
    def reference_historical_dir(self) -> Path:
        return self.data_dir / "reference" / "historical"

    @property
    def rules_dir(self) -> Path:
        """Keyword/classification rules workbook (Phase 2A)."""
        return self.data_dir / "rules"

    @property
    def received_dir(self) -> Path:
        """Received-document dump. Not consumed until Phase 4."""
        return self.data_dir / "received"

    @property
    def output_latest_dir(self) -> Path:
        return self.data_dir / "output" / "latest"

    @property
    def output_archive_dir(self) -> Path:
        return self.data_dir / "output" / "archive"

    @property
    def fixtures_dir(self) -> Path:
        return self.data_dir / "fixtures"

    # -- workbook selection ------------------------------------------------

    def default_workbook(self) -> Optional[Path]:
        """The workbook to process when none is named on the command line.

        `MDR_INPUT_WORKBOOK` wins; otherwise the first `.xlsx` in
        `data/input/current`, by name. Returns None when there is nothing to
        process, so callers can report that rather than crash on a path that
        was hard-coded at development time.
        """
        return _first_workbook(self.input_current_dir, _env_path("INPUT_WORKBOOK"))

    def default_rules_workbook(self) -> Optional[Path]:
        """The DOC TYPE keyword rules workbook.

        `MDR_RULES_WORKBOOK` wins; otherwise the first `.xlsx` in `data/rules`.
        Returns None when there is none, so classification is simply skipped
        rather than crashing a Phase 1 run.
        """
        return _first_workbook(self.rules_dir, _env_path("RULES_WORKBOOK"))

    def default_reference_workbook(self) -> Optional[Path]:
        """The manually prepared working file used to validate DOC TYPE.

        `MDR_REFERENCE_WORKBOOK` wins; otherwise the first `.xlsx` in
        `data/reference/working`.
        """
        return _first_workbook(self.reference_working_dir,
                               _env_path("REFERENCE_WORKBOOK"))


def _first_workbook(directory: Path, override: Optional[Path]) -> Optional[Path]:
    """An explicit override, else the first `.xlsx` in `directory` by name."""
    if override is not None:
        return override
    if not directory.is_dir():
        return None
    candidates = sorted(
        p for p in directory.glob("*.xlsx")
        if not p.name.startswith("~$")          # Excel lock files
    )
    return candidates[0] if candidates else None


def load_settings() -> Settings:
    """Build Settings from the environment, falling back to repo defaults."""
    return Settings(
        repo_root=REPO_ROOT,
        data_dir=_env_path("DATA_DIR") or (REPO_ROOT / "data"),
        log_level=os.environ.get(ENV_PREFIX + "LOG_LEVEL", "INFO").upper(),
        cors_origins=tuple(
            o.strip() for o in os.environ.get(
                ENV_PREFIX + "CORS_ORIGINS", "http://localhost:5173"
            ).split(",") if o.strip()
        ),
    )


#: Module-level default. Call `load_settings()` directly to re-read the
#: environment (tests do this).
settings = load_settings()
