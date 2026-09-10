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

**Which workbook, for which plant.** A plant selects its rules
(`Plant.rules_workbook`); `rules_workbook_for_plant` turns that selection into
the path the engine is given. That is the only place the plant and the rules
meet. The engine, the classifier and the SOW/IDB resolvers never see a plant:
they see a workbook, so a second plant with slightly different keywords is a
second workbook and a row in `plants` - not a branch in any rule.

Nothing here writes to the database; `RuleSetRepository.register` does. This
module reads the workbook and computes the fingerprint.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.config import Settings, settings
from ..infrastructure.excel.rules_workbook import RulesWorkbookReader

#: Read in blocks: the rules workbook is small, but the same helper is the
#: obvious one to reach for on the 12 MB MDR workbook.
_DIGEST_CHUNK = 1024 * 1024

#: Phase 2C's IDB rules are stated in `engine.idb.rules`, not in any sheet of
#: the rules workbook. Recorded on the rule set so that a future
#: workbook-driven IDB is distinguishable from today's code-driven one.
IDB_RULES_IN_CODE = "code"


class PlantRulesUnavailable(FileNotFoundError):
    """The plant selects a rules workbook that is not installed, or names one
    in a form that is not a filename. The message names the plant and the
    filename, never the server's directory."""


def rules_workbook_for_plant(rules_workbook: Optional[str], *,
                             plant_code: str = "",
                             settings: Settings = settings) -> Optional[Path]:
    """The rules workbook a plant's submissions are automated with.

    `rules_workbook` is `Plant.rules_workbook`. None means the plant has not
    selected one and the deployment default applies - `MDR_RULES_WORKBOOK`,
    else the first `.xlsx` in `rules_dir` - which may itself be None when no
    rules are installed; that is the caller's call to report, as it always
    was. A selection is a bare filename resolved under `rules_dir` and nothing
    else: an absolute path, a directory component or `..` is refused, so a
    value in the database can never point outside the rules directory.

    A selected workbook that is not installed is an error rather than a
    silent fall-back to the default: a plant that asked for its own rules
    and got another plant's would produce a result nobody asked for.
    """
    if rules_workbook is None or not rules_workbook.strip():
        return settings.default_rules_workbook()

    name = rules_workbook.strip()
    if (Path(name).name != name or name in (".", "..")
            or Path(name).is_absolute()):
        raise PlantRulesUnavailable(
            f"plant {plant_code or '?'} selects rules workbook {name!r}, "
            f"which is not a filename")
    path = settings.rules_dir / name
    if not path.is_file():
        raise PlantRulesUnavailable(
            f"plant {plant_code or '?'} selects rules workbook {name!r}, "
            f"which is not installed in the rules directory")
    return path


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
