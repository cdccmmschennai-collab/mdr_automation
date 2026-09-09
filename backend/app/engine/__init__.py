"""The MDR engine: all Phase 1+ business rules.

Phase 1 capabilities are kept as separate packages so a later phase can be
added without touching them:

* `identity`      - normalisation, matching, grouping          (Phase 1)
* `revision`      - parsing, ranking, status codes, candidacy  (Phase 1)
* `classification`- DOC TYPE from the keyword rules workbook   (Phase 2A)
* `sow`           - DOC IS REQUIRED SOW from the rules workbook (Phase 2B)
* `idb`           - DOC IDB COMPLETED STATUS from the SOW verdict (Phase 2C)
* `validation`    - comparison against ground truth   (Phase 1 + 2A/2B/2C)

`received` is reserved for the CHECK STATUS phase and is intentionally empty:
CHECK STATUS is NOT implemented, and it is the one column no engine here
feeds. It needs the received-document dump, which this project does not have.
"""
