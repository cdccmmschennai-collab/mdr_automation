"""plants select their rules workbook

Adds one nullable column, `plants.rules_workbook`: the filename under
`settings.rules_dir` of the rules workbook this plant's submissions are
automated with. NULL means the deployment default, which is what every plant
used before this column existed - so the existing plant's behaviour is
unchanged and no row needs updating.

This is the plant -> rule-set relationship. It is a column rather than a table
because a plant selects one rules configuration, and the rule set itself is
still identified by content digest in `rule_sets` (see `RULE_VERSIONING.md`):
two plants naming the same file share one `rule_sets` row, and a plant naming
a different file - base rules plus its own overrides, say - produces its own.
Nothing about `rule_sets` or `mdr_processing_summaries` moves, so every
existing result keeps the rule set it was automated under.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-10 12:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plants',
                  sa.Column('rules_workbook', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('plants', 'rules_workbook')
