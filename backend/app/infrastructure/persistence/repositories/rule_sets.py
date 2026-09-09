"""Rule-set persistence.

The digest is the identity. `register` is written around that: a rules workbook
whose bytes are already known returns the existing row rather than creating a
second one, so re-registering the same rules cannot fork a submission's history
into two rule sets that are actually the same rules.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RuleSet


class RuleSetRepository:
    """Read and write `rule_sets`."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, *, version_label: str, source_filename: str,
            content_sha256: str, required_rule_count: int = 0,
            not_required_rule_count: int = 0, sow_rule_count: int = 0,
            idb_rules_origin: str = "code", notes: str = "") -> RuleSet:
        rule_set = RuleSet(
            version_label=version_label, source_filename=source_filename,
            content_sha256=content_sha256,
            required_rule_count=required_rule_count,
            not_required_rule_count=not_required_rule_count,
            sow_rule_count=sow_rule_count, idb_rules_origin=idb_rules_origin,
            notes=notes,
        )
        self.session.add(rule_set)
        self.session.flush()
        return rule_set

    def get(self, rule_set_id: uuid.UUID) -> Optional[RuleSet]:
        return self.session.get(RuleSet, rule_set_id)

    def by_digest(self, content_sha256: str) -> Optional[RuleSet]:
        return self.session.execute(
            select(RuleSet).where(RuleSet.content_sha256 == content_sha256)
        ).scalar_one_or_none()

    def by_label(self, version_label: str) -> Optional[RuleSet]:
        return self.session.execute(
            select(RuleSet).where(RuleSet.version_label == version_label)
        ).scalar_one_or_none()

    def register(self, fingerprint, version_label: Optional[str] = None
                 ) -> RuleSet:
        """Return the rule set for this fingerprint, registering it if new.

        `fingerprint` is a `services.rule_set_service.RuleSetFingerprint`. It is
        typed loosely here so the persistence layer does not import a service:
        the dependency runs service -> repository, never back.

        When the digest is already known the stored row wins unchanged, label
        included. Relabelling an existing rule set would rewrite what every
        historical result claims it was processed with.
        """
        existing = self.by_digest(fingerprint.content_sha256)
        if existing is not None:
            return existing
        return self.add(
            version_label=version_label or fingerprint.default_version_label,
            source_filename=fingerprint.source_filename,
            content_sha256=fingerprint.content_sha256,
            required_rule_count=fingerprint.required_rule_count,
            not_required_rule_count=fingerprint.not_required_rule_count,
            sow_rule_count=fingerprint.sow_rule_count,
            idb_rules_origin=fingerprint.idb_rules_origin,
        )

    def list_all(self) -> list[RuleSet]:
        return list(self.session.execute(
            select(RuleSet).order_by(RuleSet.created_at)).scalars())
