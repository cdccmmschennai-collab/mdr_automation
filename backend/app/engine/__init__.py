"""The MDR engine: all Phase 1+ business rules.

Phase 1 capabilities are kept as separate packages so a later phase can be
added without touching them:

* `identity`      - normalisation, matching, grouping          (Phase 1)
* `revision`      - parsing, ranking, status codes, candidacy  (Phase 1)
* `classification`- DOC TYPE from the keyword rules workbook   (Phase 2A)
* `validation`    - comparison against ground truth        (Phase 1 + 2A)

`sow`, `idb` and `received` are reserved for Phases 2B-4 and are intentionally
empty. SOW, IDB and CHECK STATUS are NOT implemented.
"""
