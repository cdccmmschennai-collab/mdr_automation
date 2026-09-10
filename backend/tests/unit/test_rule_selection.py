"""`rules_workbook_for_plant`: a plant's selection becomes the engine's path.

No database, no engine. The function is the one place a plant and the rules
meet, and these are its four answers: the default when nothing is selected,
the file under `rules_dir` when something is, a refusal when the selection is
not installed, and a refusal when it is not a filename.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.core.config import load_settings
from app.services.rule_set_service import (
    PlantRulesUnavailable, rules_workbook_for_plant,
)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Settings whose `rules_dir` is an empty temporary directory."""
    monkeypatch.delenv("MDR_RULES_WORKBOOK", raising=False)
    (tmp_path / "rules").mkdir()
    return dataclasses.replace(load_settings(), data_dir=tmp_path)


class TestNoSelection:

    def test_none_means_the_deployment_default(self, settings):
        (settings.rules_dir / "default.xlsx").write_bytes(b"x")
        assert rules_workbook_for_plant(None, settings=settings) == (
            settings.rules_dir / "default.xlsx")

    def test_blank_means_the_same(self, settings):
        (settings.rules_dir / "default.xlsx").write_bytes(b"x")
        assert rules_workbook_for_plant("  ", settings=settings) == (
            settings.rules_dir / "default.xlsx")

    def test_no_default_either_is_none_not_an_error(self, settings):
        """As before this column existed: a Phase 1 run without rules."""
        assert rules_workbook_for_plant(None, settings=settings) is None


class TestASelection:

    def test_a_filename_resolves_under_the_rules_directory(self, settings):
        (settings.rules_dir / "default.xlsx").write_bytes(b"x")
        (settings.rules_dir / "plant-b.xlsx").write_bytes(b"y")
        assert rules_workbook_for_plant("plant-b.xlsx", settings=settings) == (
            settings.rules_dir / "plant-b.xlsx")

    def test_a_missing_file_is_refused_not_defaulted(self, settings):
        (settings.rules_dir / "default.xlsx").write_bytes(b"x")
        with pytest.raises(PlantRulesUnavailable, match="plant-b.xlsx"):
            rules_workbook_for_plant("plant-b.xlsx", plant_code="B",
                                     settings=settings)

    @pytest.mark.parametrize("value", [
        "../other/rules.xlsx", "sub/rules.xlsx", "/etc/rules.xlsx", "..", ".",
    ])
    def test_anything_but_a_filename_is_refused(self, settings, value):
        with pytest.raises(PlantRulesUnavailable, match="not a filename"):
            rules_workbook_for_plant(value, settings=settings)

    def test_the_message_names_the_plant_and_never_the_directory(
            self, settings):
        with pytest.raises(PlantRulesUnavailable) as raised:
            rules_workbook_for_plant("gone.xlsx", plant_code="4391",
                                     settings=settings)
        assert "4391" in str(raised.value)
        assert str(settings.rules_dir) not in str(raised.value)
