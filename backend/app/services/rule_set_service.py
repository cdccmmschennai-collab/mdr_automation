"""Identifying which rules produced a result (Delivery Phase 2).

The problem this solves is small to state and easy to get wrong. The rules live
in `data/rules/INPUT-KEYWORDS  FOR MDR TOOL.xlsx`. That file gets edited - a
keyword is added, a document type is re-scoped - and from then on the engine
answers differently. If nothing records which version of the file was in force,
then MDR #6, processed last quarter under the old keywords, becomes
indistinguishable from an MDR #6 that would be processed under the new ones. It
silently appears to have been processed with rules it never saw.

**What is persisted: a fingerprint, not the rules.** `rule_sets` stores the
SHA-256 of the workbook's bytes, its filename, and the rule counts each sheet
yielded. It does not store the keywords themselves.

Why not copy the rules in? Because that would make PostgreSQL a second home for
business rules that the business maintains in Excel, and two homes means two
answers. The engine would still read the workbook, so the database copy would
be documentation that can go stale without anything failing. Storing the digest
records *which* rules ran without claiming to be the rules - and a digest is
enough to prove that two runs used the same input, or that they did not.

The limit of this, stated plainly: given only the database, you can tell that
MDR #6 and MDR #8 used different rule sets, and you can tell exactly which file
each used. You cannot reconstruct the keywords of a workbook nobody kept. Doing
that needs the rules workbook archived alongside the submission, which is a
storage-adapter question and belongs to the phase that adds one.

Nothing here writes to the database; `RuleSetRepository.register` does. This
module reads the workbook and computes the fingerprint.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..infrastructure.excel.rules_workbook import RulesWorkbookReader

#: Read in blocks: the rules workbook is small, but the same helper is the
#: obvious one to reach for on the 12 MB MDR workbook.
_DIGEST_CHUNK = 1024 * 1024

#: Phase 2C's IDB rules are stated in `engine.idb.rules`, not in any sheet of
#: the rules workbook. Recorded on the rule set so that a future
#: workbook-driven IDB is distinguishable from today's code-driven one.
IDB_RULES_IN_CODE = "code"


def file_digest(path: Path) -> str:
    """SHA-256 of a file's bytes, hex."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_DIGEST_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class RuleSetFingerprint:
    """What identifies one version of the rule inputs.

    Frozen: a fingerprint that could be edited after being computed would not
    be a fingerprint.
    """

    source_filename: str
    content_sha256: str
    required_rule_count: int
    not_required_rule_count: int
    sow_rule_count: int
    idb_rules_origin: str = IDB_RULES_IN_CODE

    @property
    def default_version_label(self) -> str:
        """A stable label derived from the content, e.g. `INPUT-KEYWORDS-a1b2c3d4e5f6`.

        Derived rather than sequential so that the same workbook fingerprinted
        on two machines gets the same label. A human-chosen label (`A`, `B`)
        can be passed to `RuleSetRepository.register` instead; the digest stays
        the identity either way.
        """
        stem = Path(self.source_filename).stem.strip().replace(" ", "-")
        return f"{stem[:40]}-{self.content_sha256[:12]}"


def fingerprint_rules_workbook(rules_workbook: Optional[Path] = None
                               ) -> RuleSetFingerprint:
    """Fingerprint the rules workbook the engine would use.

    Opens it read-only through the existing `RulesWorkbookReader`, so the counts
    recorded are the counts the engine actually loads - not a second reading of
    the file that might disagree with it.

    Raises FileNotFoundError when there is no rules workbook. That is
    deliberate and differs from `classification_service.build_classifier`,
    which returns None: a run with no rules is a valid Phase 1 run, but a
    *rule set* with no rules is not a thing that can be recorded.
    """
    path = rules_workbook or settings.default_rules_workbook()
    if path is None or not Path(path).is_file():
        raise FileNotFoundError(
            f"no rules workbook to fingerprint (looked in {settings.rules_dir})")

    path = Path(path)
    reader = RulesWorkbookReader(path)
    _, rules_discovery = reader.read_rule_rows()
    _, sow_discovery = reader.read_sow_rows()

    return RuleSetFingerprint(
        source_filename=path.name,
        content_sha256=file_digest(path),
        required_rule_count=rules_discovery.required_rules,
        not_required_rule_count=rules_discovery.not_required_rules,
        sow_rule_count=sow_discovery.rule_count,
    )
