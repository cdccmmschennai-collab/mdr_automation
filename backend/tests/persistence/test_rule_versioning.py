"""A stored result stays attached to the rules that produced it.

The failure this guards against is quiet: the rules workbook is edited, and
every historical submission silently appears to have been processed with rules
it never saw. The tests below state that in the form the business asks it -
*MDR #6 was processed under Rule Set A; introducing Rule Set B must not change
what MDR #6 says about itself.*
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.infrastructure.persistence.repositories import (
    ProcessingSummaryRepository, RuleSetRepository, SubmissionRepository,
)
from app.services.rule_set_service import (
    RuleSetFingerprint, file_digest, fingerprint_rules_workbook,
)

from .conftest import make_digest

SUMMARY = {"rows": 10, "doc_type_populated": 8, "check_status_populated": 0}


def a_fingerprint(seed: str, filename: str = "INPUT-KEYWORDS.xlsx"
                  ) -> RuleSetFingerprint:
    return RuleSetFingerprint(
        source_filename=filename, content_sha256=make_digest(seed),
        required_rule_count=51, not_required_rule_count=12, sow_rule_count=30)


class TestFingerprintingTheRulesWorkbook:

    def test_the_real_rules_workbook_fingerprints(self):
        """Against the file the engine actually loads, not a fixture."""
        fingerprint = fingerprint_rules_workbook()
        assert len(fingerprint.content_sha256) == 64
        assert fingerprint.source_filename.endswith(".xlsx")
        assert fingerprint.required_rule_count > 0
        assert fingerprint.sow_rule_count > 0
        assert fingerprint.idb_rules_origin == "code", (
            "Phase 2C's rules are stated in engine.idb.rules, not in a sheet")

    def test_the_digest_is_the_file(self, tmp_path):
        first = tmp_path / "a.bin"
        second = tmp_path / "b.bin"
        first.write_bytes(b"same bytes")
        second.write_bytes(b"same bytes")
        assert file_digest(first) == file_digest(second)

        second.write_bytes(b"different bytes")
        assert file_digest(first) != file_digest(second)

    def test_the_default_label_is_derived_from_the_content(self):
        """Same file, same label, on any machine."""
        fingerprint = a_fingerprint("seed")
        assert fingerprint.default_version_label == a_fingerprint(
            "seed").default_version_label
        assert fingerprint.content_sha256[:12] in (
            fingerprint.default_version_label)

    def test_a_missing_rules_workbook_is_an_error(self, tmp_path):
        """Unlike a Phase 1 run, a rule set with no rules is not a thing."""
        with pytest.raises(FileNotFoundError):
            fingerprint_rules_workbook(tmp_path / "nothing.xlsx")


class TestRegisteringRuleSets:

    def test_a_rule_set_persists(self, session):
        stored = RuleSetRepository(session).register(a_fingerprint("A"))
        session.flush()
        assert stored.required_rule_count == 51
        assert stored.sow_rule_count == 30
        assert stored.idb_rules_origin == "code"

    def test_the_same_workbook_registers_once(self, session):
        repo = RuleSetRepository(session)
        fingerprint = a_fingerprint("identical")
        first = repo.register(fingerprint)
        session.flush()
        assert repo.register(fingerprint).id == first.id

    def test_re_registering_does_not_relabel(self, session):
        """Relabelling would rewrite what every stored result claims it used."""
        repo = RuleSetRepository(session)
        fingerprint = a_fingerprint("stable")
        first = repo.register(fingerprint, version_label="A")
        session.flush()
        again = repo.register(fingerprint, version_label="B")
        assert again.version_label == "A"

    def test_a_changed_workbook_is_a_different_rule_set(self, session):
        repo = RuleSetRepository(session)
        first = repo.register(a_fingerprint("before"))
        second = repo.register(a_fingerprint("after"))
        session.flush()
        assert first.id != second.id

    def test_two_labels_cannot_share_a_digest(self, session):
        repo = RuleSetRepository(session)
        digest = make_digest("one-file")
        repo.add(version_label="A", source_filename="k.xlsx",
                 content_sha256=digest)
        with pytest.raises(IntegrityError):
            repo.add(version_label="B", source_filename="k.xlsx",
                     content_sha256=digest)

    def test_a_digest_must_look_like_one(self, session):
        with pytest.raises(IntegrityError):
            RuleSetRepository(session).add(
                version_label="short", source_filename="k.xlsx",
                content_sha256="abc")


class TestHistoricalResultsStayExplainable:

    def test_mdr_6_keeps_rule_set_a_after_rule_set_b_arrives(self, session,
                                                            plant):
        """The requirement, stated directly."""
        rules = RuleSetRepository(session)
        subs = SubmissionRepository(session)
        summaries = ProcessingSummaryRepository(session)

        set_a = rules.register(a_fingerprint("rule-set-A"), version_label="A")
        sixth = subs.add(plant_id=plant.id, submission_no=6,
                         source_filename="six.xlsx",
                         source_sha256=make_digest("six"), source_byte_size=6)
        summaries.add(submission_id=sixth.id, rule_set_id=set_a.id,
                      summary=SUMMARY)
        session.flush()

        # The rules workbook is edited; a new rule set is registered and a new
        # submission is processed under it.
        set_b = rules.register(a_fingerprint("rule-set-B"), version_label="B")
        eighth = subs.add(plant_id=plant.id, submission_no=8,
                          source_filename="eight.xlsx",
                          source_sha256=make_digest("eight"),
                          source_byte_size=8)
        summaries.add(submission_id=eighth.id, rule_set_id=set_b.id,
                      summary=SUMMARY)
        session.flush()
        session.expire_all()

        assert summaries.for_submission(sixth.id).rule_set.version_label == "A"
        assert summaries.for_submission(eighth.id).rule_set.version_label == "B"

    def test_the_rule_set_a_result_points_at_cannot_be_deleted(self, session,
                                                               plant):
        """ON DELETE RESTRICT: an explanation cannot be removed from under a result."""
        rules = RuleSetRepository(session)
        set_a = rules.register(a_fingerprint("pinned"))
        submission = SubmissionRepository(session).add(
            plant_id=plant.id, source_filename="x.xlsx",
            source_sha256=make_digest("x"), source_byte_size=1)
        ProcessingSummaryRepository(session).add(
            submission_id=submission.id, rule_set_id=set_a.id, summary=SUMMARY)
        session.flush()

        with pytest.raises(IntegrityError):
            session.execute(text("DELETE FROM rule_sets WHERE id = :id"),
                            {"id": set_a.id})

    def test_every_result_a_rule_set_produced_is_findable(self, session, plant):
        """Asked from the other side: what would a wrong rule set have affected?"""
        rules = RuleSetRepository(session)
        subs = SubmissionRepository(session)
        summaries = ProcessingSummaryRepository(session)

        set_a = rules.register(a_fingerprint("A-many"))
        for n in (1, 2, 3):
            submission = subs.add(plant_id=plant.id, submission_no=n,
                                  source_filename=f"{n}.xlsx",
                                  source_sha256=make_digest(f"m{n}"),
                                  source_byte_size=n)
            summaries.add(submission_id=submission.id, rule_set_id=set_a.id,
                          summary=SUMMARY)
        session.flush()
        assert len(summaries.by_rule_set(set_a.id)) == 3

    def test_a_result_cannot_be_stored_without_a_rule_set(self, session,
                                                          submission):
        """The column is NOT NULL: an unexplainable result is not storable."""
        with pytest.raises(TypeError):
            ProcessingSummaryRepository(session).add(
                submission_id=submission.id, summary=SUMMARY)

    def test_a_result_cannot_invent_a_rule_set(self, session, submission):
        with pytest.raises(IntegrityError):
            ProcessingSummaryRepository(session).add(
                submission_id=submission.id, rule_set_id=uuid.uuid4(),
                summary=SUMMARY)
