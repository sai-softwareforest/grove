# Changelog

Notable changes to Grove, newest first. The format follows Keep a Changelog;
versions follow Semantic Versioning as described in `REQUIREMENTS.md`,
section 3. Requirement ids (`R-…`) and work orders (`WO-…`) refer to
`REQUIREMENTS.md` and `docs/work-orders.md`.

## Unreleased

### Added

- `REQUIREMENTS.md`: the single requirements document, with stable ids and a
  status for every requirement (WO-01).
- `docs/blueprint.md` (architecture, data model, operation map, traceability,
  decision log), `docs/work-orders.md`, `docs/analysis.md` and
  `docs/industry-survey.md` (WO-01).
- `grove status` / `grove_status` report `home_source` (`flag`, `env` or
  `default`) and a `hint` when the data directory holds no projects
  (R-HOME-2, WO-02).
- `grove search` / `grove_knowledge_search` without a query list the latest
  revision of every knowledge document, newest first, without bodies, with
  `body_chars`. Results carry `mode` (`list` or `search`) (R-KNOW-6, WO-04).
- Scan results report `long_lines` and `caps.max_line_chars`; map ingest
  reports `long_lines` (R-SCAN-7, WO-06).
- Tests that guard the invariants: an import allow-list (no network, no
  model, no process spawning), module layering, the closed set of error
  codes, deterministic scans, and a size budget for the MCP tool list
  (WO-03, WO-07).

### Changed

- Lines longer than 5000 characters are no longer analysed by the scanner or
  the map parser. They are counted and reported. This can change which
  blueprint items a scan produces for files with very long lines
  (R-COMPAT-7, R-COMPAT-9).
- The scan's time cap is now also checked between the lines of a file, so a
  scan stops inside a large file instead of after it (R-SCAN-8).
- `grove mcp` logs how the data directory was chosen.

### Fixed

- Opening a fresh data directory from several processes at once could fail
  with "database is locked" (about 4 % of concurrent first opens in a stress
  run). The switch to WAL is now retried (R-HOME-8, WO-05).
- A single long line could take minutes to scan: the Markdown
  table-separator pattern was quadratic on runs of spaces, and link, image
  and HTML patterns on repeated openers. The first is rewritten; the line cap
  bounds the rest (WO-06).
- A paragraph of many thousand lines took time quadratic in its length
  (WO-06).
- A UTF-8 byte order mark hid the first line of a file from the scanner, so
  a leading heading or definition was lost (WO-06).
- The `grove_recommend_next` description left out the documented-limit tier
  and the `scan` and `none` actions (R-REC-1, WO-03).

## 0.1.0 — 2026-11-12

First version: project scan into a three-layer blueprint with heuristic gap
findings, revisioned knowledge with full-text search, map ingest, local work
items, one recommendation, a CLI and an MCP stdio server with sixteen tools.
See `BUILD_NOTES.md`.
