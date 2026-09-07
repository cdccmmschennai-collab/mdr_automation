# Phase 2 — DOC TYPE Classification

**Status:** ❌ NOT IMPLEMENTED.

## Intended scope

Assign `DOC TYPE` (column AL of `QatarEnergy-TN WORKING`) from the rules
workbook''s keyword sheets against each document.

## Prerequisites

- A business answer to the largest Phase 1 open question: **what does `NL` on a
  whole document group mean?** (431 groups — see DECISION_LOG D-07)
- A decision on how to parse the rules workbook''s glob syntax (`*P&ID*LEGEND*`)
  and inline alternation (`LIGHTING LAYOUT or LIGHTNING LAYOUT`)

## Reserved locations

`backend/app/engine/classification/` (empty), and
[`../business-rules/classification-rules.md`](../business-rules/classification-rules.md)
for the rules once they are derived.

Nothing in the codebase reads `data/rules/` today.
