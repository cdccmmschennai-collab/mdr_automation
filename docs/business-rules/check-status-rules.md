# Check Status Rules

**Status:** ❌ NOT IMPLEMENTED — Phase 4
**Reserved code location:** `backend/app/engine/received/` (empty)
**Reserved data location:** `data/received/` (empty)

No check-status rule has been derived, and none is stated here.

---

## Why there is no `domain/enums/check_status.py`

The target architecture names that file. It was deliberately **not created**:
no evidence yet defines the CHECK STATUS vocabulary, and writing an enum now
would be inventing a business rule. See
[DECISION_LOG.md](../architecture/DECISION_LOG.md) A-07.

## Target output column

`CHECK STATUS` — column AO of the `QatarEnergy-TN WORKING` sheet in the
reference workbook. Phase 1 does not populate it.

## Open

- What is the format of the received-document dump? No such file has been
  supplied.
- How are received documents matched to MDR rows — by document number, by
  document-number-plus-revision, or by filename convention?
- What are the permitted CHECK STATUS values?
