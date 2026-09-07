# Phase 4 — Received-Document Check and CHECK STATUS

**Status:** ❌ NOT IMPLEMENTED.

## Intended scope

Reconcile MDR rows against the received-document dump and derive `CHECK STATUS`
(column AO of `QatarEnergy-TN WORKING`).

## Blocked on

**No received-document dump has been supplied.** Its format, and how its entries
match MDR rows, are unknown.

## Reserved locations

`backend/app/engine/received/` (empty), `data/received/` (empty),
[`../business-rules/check-status-rules.md`](../business-rules/check-status-rules.md)

`domain/enums/check_status.py` was deliberately not created — see
[DECISION_LOG](../architecture/DECISION_LOG.md) A-07.
