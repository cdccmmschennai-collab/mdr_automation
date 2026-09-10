"""`GET /api/v1/plants`, and a plant selecting its rules.

The first half is the selector contract: the frontend lists plants, shows
code and name, keeps the id, and that id is what upload accepts. The second
half is the plant -> rule-set relationship over the real workflow: which
workbook automates a submission is decided by the submission's plant, two
plants naming the same workbook share one rule set, a plant naming its own
gets its own, and a plant whose selection is not installed is refused
without touching the submission.
"""

from __future__ import annotations

import shutil
import uuid

import pytest

from app.domain.enums.lifecycle import SubmissionStatus
from app.services.rule_set_service import file_digest
from tests.support.workbook import RULES_WORKBOOK, requires_rules_workbook

from .conftest import stored_submission, upload


def add_plant(settings, *, rules_workbook=None, name="Plant"):
    from app.infrastructure.persistence.database import session_scope
    from app.infrastructure.persistence.repositories import PlantRepository

    with session_scope(settings) as session:
        return PlantRepository(session).add(
            code=f"PLANT-{uuid.uuid4().hex[:8]}", name=name,
            rules_workbook=rules_workbook)


def automate(client, plant, workbook):
    mdr_id = upload(client, plant, workbook).json()["mdr_id"]
    assert client.post(f"/api/v1/mdr/{mdr_id}/extract").status_code == 200
    return mdr_id, client.post(f"/api/v1/mdr/{mdr_id}/automate")


# ====================================================== THE SELECTOR

class TestListingPlants:

    def test_a_registered_plant_is_listed_with_id_code_and_name(self, client,
                                                                plant):
        response = client.get("/api/v1/plants")
        assert response.status_code == 200
        listed = {p["id"]: p for p in response.json()}
        assert str(plant.id) in listed
        assert listed[str(plant.id)] == {
            "id": str(plant.id), "code": plant.code, "name": plant.name}

    def test_the_listed_id_is_what_upload_accepts(self, client, plant,
                                                  small_workbook):
        """The whole point: the frontend never types a UUID."""
        listed = {p["code"]: p["id"] for p in client.get("/api/v1/plants").json()}
        response = client.post(
            "/api/v1/mdr/upload",
            data={"plant_id": listed[plant.code]},
            files={"mdr_file": (small_workbook.name,
                                small_workbook.read_bytes())})
        assert response.status_code == 201
        assert response.json()["plant_id"] == str(plant.id)

    def test_plants_are_ordered_by_code(self, client, workflow_settings):
        add_plant(workflow_settings)
        add_plant(workflow_settings)
        codes = [p["code"] for p in client.get("/api/v1/plants").json()]
        assert codes == sorted(codes)

    def test_nothing_about_rules_or_the_server_is_exposed(
            self, client, workflow_settings):
        """A plant with its own rules workbook lists exactly like any other."""
        configured = add_plant(workflow_settings, rules_workbook="own.xlsx")
        listed = {p["id"]: p for p in client.get("/api/v1/plants").json()}
        assert set(listed[str(configured.id)]) == {"id", "code", "name"}

    def test_an_unknown_plant_is_still_refused_on_upload(self, client,
                                                         small_workbook):
        response = client.post(
            "/api/v1/mdr/upload",
            data={"plant_id": str(uuid.uuid4())},
            files={"mdr_file": (small_workbook.name,
                                small_workbook.read_bytes())})
        assert response.status_code == 404


# ============================================= A PLANT SELECTS ITS RULES

@pytest.fixture(scope="module")
def rules_dir(tmp_path_factory):
    """A rules directory holding a copy of the real workbook, so that "the
    same rules" and "different rules" can both be built from it without
    inventing any rule."""
    directory = tmp_path_factory.mktemp("rules")
    if RULES_WORKBOOK is not None and RULES_WORKBOOK.is_file():
        shutil.copy(RULES_WORKBOOK, directory / RULES_WORKBOOK.name)
    return directory


@pytest.fixture
def settings(workflow_settings, rules_dir, monkeypatch):
    """The workflow's settings with `rules_dir` pointed at the copy and the
    environment override cleared, so the default rules workbook is the first
    file in that directory - exactly how a deployment finds its rules."""
    from app.core import config

    monkeypatch.delenv("MDR_RULES_WORKBOOK", raising=False)
    # `rules_dir` is derived from `data_dir`; the tmp directory is not laid
    # out that way, so the property is patched for the duration of the test.
    monkeypatch.setattr(config.Settings, "rules_dir",
                        property(lambda self: rules_dir))
    return workflow_settings


@requires_rules_workbook
class TestAPlantSelectsItsRules:

    def test_a_plant_with_no_selection_uses_the_default_as_before(
            self, client, settings, small_workbook):
        plant = add_plant(settings)
        _, response = automate(client, plant, small_workbook)
        assert response.status_code == 200, response.text
        assert response.json()["rule_set"]["content_sha256"] == file_digest(
            RULES_WORKBOOK)

    def test_a_plant_naming_the_default_file_shares_its_rule_set(
            self, client, settings, small_workbook):
        """Selection by filename, same bytes -> the same `rule_sets` row."""
        by_default = add_plant(settings)
        by_name = add_plant(settings, rules_workbook=RULES_WORKBOOK.name)
        _, first = automate(client, by_default, small_workbook)
        _, second = automate(client, by_name, small_workbook)
        assert first.json()["rule_set"]["rule_set_id"] == (
            second.json()["rule_set"]["rule_set_id"])

    def test_a_plant_with_its_own_workbook_gets_its_own_rule_set(
            self, client, settings, small_workbook, rules_dir):
        """Different bytes -> a different rule set, and the other plant's
        submission still points at the one it was automated under."""
        own = rules_dir / "plant-b-rules.xlsx"
        shutil.copy(RULES_WORKBOOK, own)
        with open(own, "ab") as handle:       # same rules, different bytes
            handle.write(b"\0")

        common = add_plant(settings)
        plant_b = add_plant(settings, rules_workbook=own.name)
        common_id, first = automate(client, common, small_workbook)
        _, second = automate(client, plant_b, small_workbook)

        assert first.status_code == 200 and second.status_code == 200
        assert second.json()["rule_set"]["content_sha256"] == file_digest(own)
        assert second.json()["rule_set"]["source_filename"] == own.name
        assert first.json()["rule_set"]["rule_set_id"] != (
            second.json()["rule_set"]["rule_set_id"])
        # The earlier result is untouched by the later plant's rules.
        summary = client.get(f"/api/v1/mdr/{common_id}/summary").json()
        assert summary["rule_set"]["rule_set_id"] == (
            first.json()["rule_set"]["rule_set_id"])

    def test_a_missing_selection_is_refused_and_the_submission_kept(
            self, client, settings, small_workbook):
        """Never a silent fall-back to another plant's rules."""
        plant = add_plant(settings, rules_workbook="not-installed.xlsx")
        mdr_id = upload(client, plant, small_workbook).json()["mdr_id"]

        response = client.post(f"/api/v1/mdr/{mdr_id}/extract")
        assert response.status_code == 422
        assert "not-installed.xlsx" in response.json()["detail"]
        assert str(settings.rules_dir) not in response.json()["detail"]
        assert stored_submission(settings, mdr_id).status == (
            SubmissionStatus.UPLOADED)
