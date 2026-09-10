"""The Delivery Phase 2 schema: five tables, and the reasons for each.

    plants  1--*  mdr_submissions  1--*  mdr_document_rows
                        |
                        1--1  mdr_processing_summaries  *--1  rule_sets

The schema is deliberately small. The MDR workbook has some seventy columns;
copying it into PostgreSQL column-for-column would produce a database that has
to be migrated every time the spreadsheet changes, and would still not be the
authority - the workbook is. What is stored is what the *product* needs to
answer questions about a submission after the fact: which plant it belongs to,
which file it came from, how far it got, what the four automation columns
resolved to for each row, and which rule set produced those answers.

Two conventions worth stating once:

**Text, not PostgreSQL ENUM.** `status` is `VARCHAR` with a CHECK constraint
listing `SubmissionStatus`. A native enum type reads better in `psql` but adding
a value to one is a schema migration that cannot run inside a transaction on
older servers, and the legal values are a domain fact that belongs in
`domain.enums.lifecycle` - not in the database's type system.

**Timestamps are `TIMESTAMPTZ`.** A submission is uploaded at an instant, not at
a wall-clock reading; storing naive timestamps would make two plants in two
time zones incomparable.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...domain.enums.lifecycle import INITIAL_STATUS, SUBMISSION_STATUSES
from .base import Base, TimestampMixin

#: A hex SHA-256 digest.
SHA256_LENGTH = 64

_STATUS_LIST = ", ".join(repr(s) for s in SUBMISSION_STATUSES)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PgUUID(as_uuid=True), primary_key=True,
                         default=uuid.uuid4)


class Plant(TimestampMixin, Base):
    """A plant/project that MDR submissions belong to.

    Present because a submission is meaningless without one: `MDR #6` is only
    identifiable as *this plant's* sixth submission. One row today
    (QatarEnergy-TN); the table exists so the second plant is a row rather than
    a migration.
    """

    __tablename__ = "plants"

    id: Mapped[uuid.UUID] = _uuid_pk()
    #: Stable business key, e.g. `QATARENERGY-TN`. Unique: two plants sharing a
    #: code would make every submission ambiguous.
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    submissions: Mapped[list["MdrSubmission"]] = relationship(
        back_populates="plant")

    def __repr__(self) -> str:                      # pragma: no cover
        return f"<Plant {self.code}>"


class RuleSet(Base):
    """One identified version of the MDR rule inputs.

    This is the Delivery Phase 2 answer to *"which rules produced this
    result?"* - see `services.rule_set_service` for what is fingerprinted and
    `docs/architecture/RULE_VERSIONING.md` for why the rule *content* is not
    copied in here.

    Immutable by intention: there is no `updated_at`. A rule set that changed
    in place would silently rewrite the history of every submission that points
    at it, which is exactly the failure this table exists to prevent. A changed
    rules workbook produces a new digest and therefore a new row.
    """

    __tablename__ = "rule_sets"
    __table_args__ = (
        CheckConstraint("length(content_sha256) = 64",
                        name="content_sha256_is_a_digest"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    #: Human-facing name for the version, e.g. `A` or `2026-09-rev2`.
    version_label: Mapped[str] = mapped_column(String(64), nullable=False,
                                               unique=True)
    #: Filename the rules came from, kept for the audit trail only. The digest,
    #: not the name, is the identity.
    source_filename: Mapped[str] = mapped_column(Text, nullable=False)
    #: SHA-256 of the rules workbook bytes. Unique, so the same file cannot be
    #: registered twice under two labels and appear to be two rule sets.
    content_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH),
                                                nullable=False, unique=True)

    #: Rule counts at registration. Cheap, and they make an accidental
    #: half-empty rules workbook obvious without reopening the file.
    required_rule_count: Mapped[int] = mapped_column(Integer, nullable=False,
                                                     default=0)
    not_required_rule_count: Mapped[int] = mapped_column(Integer,
                                                         nullable=False,
                                                         default=0)
    sow_rule_count: Mapped[int] = mapped_column(Integer, nullable=False,
                                                default=0)
    #: Where the IDB rules came from. `code` today: Phase 2C's two rules are
    #: stated in `engine.idb.rules`, not in any sheet. Recorded so a future
    #: rules-workbook-driven IDB is distinguishable from this one.
    idb_rules_origin: Mapped[str] = mapped_column(String(32), nullable=False,
                                                  default="code")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now())

    summaries: Mapped[list["MdrProcessingSummary"]] = relationship(
        back_populates="rule_set")

    def __repr__(self) -> str:                      # pragma: no cover
        return f"<RuleSet {self.version_label} {self.content_sha256[:8]}>"


class MdrSubmission(TimestampMixin, Base):
    """One uploaded MDR workbook, and how far it has been processed.

    `submission_no` is the business's `MDR #6`, unique within a plant. It is
    assigned by `SubmissionRepository.next_submission_no` rather than by a
    sequence, because the number belongs to the plant and a global sequence
    would leave gaps that look like lost submissions.

    Historical submissions are independent by construction: nothing here points
    at "the current MDR", no row is updated when a newer submission arrives,
    and every query into `mdr_document_rows` is scoped by `submission_id`.
    """

    __tablename__ = "mdr_submissions"
    __table_args__ = (
        UniqueConstraint("plant_id", "submission_no",
                         name="uq_mdr_submissions_plant_id_submission_no"),
        CheckConstraint(f"status IN ({_STATUS_LIST})", name="status_is_known"),
        CheckConstraint("submission_no > 0", name="submission_no_is_positive"),
        CheckConstraint("source_byte_size > 0", name="source_byte_size_is_positive"),
        CheckConstraint("length(source_sha256) = 64",
                        name="source_sha256_is_a_digest"),
        Index("ix_mdr_submissions_plant_id_uploaded_at", "plant_id",
              "uploaded_at"),
        Index("ix_mdr_submissions_source_sha256", "source_sha256"),
        Index("ix_mdr_submissions_status", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    plant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        # RESTRICT, not CASCADE: deleting a plant must not silently take its
        # submission history with it.
        ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False)
    submission_no: Mapped[int] = mapped_column(Integer, nullable=False)

    # -- lifecycle ---------------------------------------------------------
    status: Mapped[str] = mapped_column(String(16), nullable=False,
                                        default=INITIAL_STATUS.value)
    #: Populated only when `status` is FAILED. Empty otherwise.
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # -- source workbook metadata -----------------------------------------
    #: The name the file arrived under. Not unique: the same filename is
    #: uploaded month after month, and that is normal.
    source_filename: Mapped[str] = mapped_column(Text, nullable=False)
    #: SHA-256 of the uploaded bytes. Indexed, not unique - re-processing the
    #: same workbook under a new rule set is legitimate, and two submissions
    #: with one digest is a fact worth being able to find, not an error.
    source_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH),
                                               nullable=False)
    source_byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Where the bytes were put: the storage *key*, `<submission_id>/<filename>`,
    #: resolved against `settings.uploads_dir` by `infrastructure.storage` -
    #: never an absolute path, so the data directory can move.
    stored_path: Mapped[str] = mapped_column(Text, nullable=False, default="")

    #: What extraction found in the workbook - `MdrEngine.run().discovery`.
    #: Null until the submission reaches EXTRACTED.
    source_sheet_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_header_row: Mapped[Optional[int]] = mapped_column(Integer,
                                                             nullable=True)
    source_row_count: Mapped[Optional[int]] = mapped_column(Integer,
                                                            nullable=True)

    # -- when each step happened ------------------------------------------
    uploaded_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now())
    extracted_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    automated_at: Mapped[Optional[_dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    plant: Mapped["Plant"] = relationship(back_populates="submissions")
    rows: Mapped[list["MdrDocumentRow"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan",
        passive_deletes=True)
    summary: Mapped[Optional["MdrProcessingSummary"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan",
        passive_deletes=True, uselist=False)

    def __repr__(self) -> str:                      # pragma: no cover
        return f"<MdrSubmission #{self.submission_no} {self.status}>"


class MdrDocumentRow(Base):
    """One processed QatarEnergy-TN row of one submission.

    Carries the four automation columns the engines resolve, the identity and
    revision context needed to make sense of them, and the provenance of each
    verdict. It is a record of what the automation decided - not a copy of the
    workbook. Columns the product does not query are left in the workbook,
    which remains the authority for them.

    `check_status` exists and is constrained to the empty string. Phase 3B
    would fill it; until then, `domain.models.automation.AutomationRow` refuses
    to be constructed with a value in it, and the CHECK constraint means the
    database refuses too. Both must be removed deliberately, together, for
    CHECK STATUS to start being written - which is the point.
    """

    __tablename__ = "mdr_document_rows"
    __table_args__ = (
        UniqueConstraint("submission_id", "source_row",
                         name="uq_mdr_document_rows_submission_id_source_row"),
        CheckConstraint("check_status = ''", name="check_status_not_evaluated"),
        CheckConstraint("source_row > 0", name="source_row_is_positive"),
        Index("ix_mdr_document_rows_submission_id_document_identity",
              "submission_id", "document_identity"),
        Index("ix_mdr_document_rows_submission_id_doc_type", "submission_id",
              "doc_type"),
    )

    #: BIGINT: a single submission contributes ~22k rows, and submissions
    #: accumulate. An INT ceiling is not a limit worth discovering in
    #: production.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True,
                                    autoincrement=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        # CASCADE: these rows have no meaning apart from their submission.
        ForeignKey("mdr_submissions.id", ondelete="CASCADE"), nullable=False)
    #: The 1-based row number in the source sheet, so a human can find it again.
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)

    # -- identity and revision (Phase 1) -----------------------------------
    document_identity: Mapped[str] = mapped_column(Text, nullable=False,
                                                   default="")
    qatarenergy_document_no: Mapped[str] = mapped_column(Text, nullable=False,
                                                         default="")
    revision: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    revision_raw: Mapped[str] = mapped_column(String(64), nullable=False,
                                              default="")
    revision_status: Mapped[str] = mapped_column(String(32), nullable=False,
                                                 default="")
    is_latest_revision: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                     default=False)
    document_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    discipline: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # -- the automation columns -------------------------------------------
    #: `DOC WITH REV` (Phase 1).
    doc_with_rev: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: `DOC TYPE` (Phase 2A). Empty means no keyword rule covered the document.
    doc_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: `DOC IS REQUIRED SOW` (Phase 2B).
    sow: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: `DOC IDB COMPLETED STATUS` (Phase 2C). Empty means a person must still
    #: check it - see `domain.models.automation.MANUAL_CHECK_REQUIRED`.
    idb_completed_status: Mapped[str] = mapped_column(Text, nullable=False,
                                                      default="")
    #: `CHECK STATUS` (Phase 3B). Structurally blank - see the class docstring.
    check_status: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # -- provenance --------------------------------------------------------
    doc_type_rule: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sow_source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    idb_source: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now())

    submission: Mapped["MdrSubmission"] = relationship(back_populates="rows")

    def __repr__(self) -> str:                      # pragma: no cover
        return f"<MdrDocumentRow row={self.source_row} {self.doc_with_rev}>"


class MdrProcessingSummary(Base):
    """The record of one processing run over one submission.

    `rule_set_id` is the load-bearing column: it is what makes MDR #6 stay
    explainable after Rule Set B replaces Rule Set A. It is NOT NULL and its
    foreign key is RESTRICT, so a rule set that any result points at cannot be
    deleted.

    Unique on `submission_id`, because Delivery Phase 2 stores one run per
    submission. Re-running a submission under a new rule set is a real future
    requirement; when it arrives, dropping this one constraint turns the table
    into the run history it is already shaped like, and no other column moves.

    The counts are `AutomationRun.summary()` - the same numbers the CLI already
    prints, persisted rather than recomputed. `counts` holds the per-value
    breakdowns (`doc_type_counts`, `sow_counts`, `idb_counts`) as JSONB: they
    are a variable-width map whose keys are business values, and a table per
    map would be a schema that changes whenever the business adds a document
    type.
    """

    __tablename__ = "mdr_processing_summaries"
    __table_args__ = (
        UniqueConstraint("submission_id",
                         name="uq_mdr_processing_summaries_submission_id"),
        CheckConstraint("row_count >= 0", name="row_count_is_not_negative"),
        CheckConstraint("check_status_populated = 0",
                        name="check_status_never_populated"),
        Index("ix_mdr_processing_summaries_rule_set_id", "rule_set_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("mdr_submissions.id", ondelete="CASCADE"), nullable=False)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        # RESTRICT: a rule set that explains a stored result is not deletable.
        ForeignKey("rule_sets.id", ondelete="RESTRICT"), nullable=False)

    #: The backend version that produced the result, from `pyproject.toml`.
    #: The rule set explains the *rules*; this explains the *code*.
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False,
                                                default="")

    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    doc_with_rev_populated: Mapped[int] = mapped_column(Integer, nullable=False,
                                                        default=0)
    doc_type_populated: Mapped[int] = mapped_column(Integer, nullable=False,
                                                    default=0)
    sow_populated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sow_unresolved: Mapped[int] = mapped_column(Integer, nullable=False,
                                                default=0)
    idb_populated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idb_unmapped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Required documents left blank on purpose, awaiting a human check.
    idb_manual_check_required: Mapped[int] = mapped_column(Integer,
                                                           nullable=False,
                                                           default=0)
    #: Always 0, and constrained to it: nothing evaluates CHECK STATUS yet.
    check_status_populated: Mapped[int] = mapped_column(Integer, nullable=False,
                                                        default=0)

    #: `doc_type_counts` / `sow_counts` / `idb_counts`, plus the Phase 1
    #: discovery and summary maps.
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now())

    submission: Mapped["MdrSubmission"] = relationship(back_populates="summary")
    rule_set: Mapped["RuleSet"] = relationship(back_populates="summaries")

    def __repr__(self) -> str:                      # pragma: no cover
        return f"<MdrProcessingSummary rows={self.row_count}>"
