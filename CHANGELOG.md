# Changelog

Notable changes to Grove, newest first. The format follows Keep a Changelog;
versions follow Semantic Versioning as described in `REQUIREMENTS.md`,
section 3. Requirement ids (`R-…`) and work orders (`WO-…`) refer to
`REQUIREMENTS.md` and `docs/work-orders.md`.

## Unreleased

### Added

- `grove export NAME [--out DIR]`: a read-only copy of a project as
  Markdown pages with relative links (`index.md`, `requirements.md`,
  `blueprint/SLUG.md`, `knowledge/SLUG.md`, `findings.md` with one anchor
  per finding key, `work/index.md`, `work/ID.md`). The same data gives the
  same bytes; the default directory is `exports/NAME` in the data
  directory; a directory inside any registered project root is refused, as
  are the data directory, a directory with unknown files and any symbolic
  link; nothing is deleted, stale pages are reported; no page shows a path
  of this machine, and what the publish check would refuse is replaced by
  `[redacted]` and counted. Command line only: no MCP tool, and
  `tools/list` is unchanged (WO-39, R-VIEW-1, R-VIEW-3, R-VIEW-4, R-VIEW-6,
  D-54).
- `grove view [NAME] [--port N]`: the same pages as a read-only web view on
  127.0.0.1 (port 8765 by default), with a sidebar, cross-links and
  search, until Ctrl-C. Only GET and HEAD, fixed routes, a `Host` check, a
  read-only database connection, stored text escaped, no scripts, no
  login. This is the one command that listens; R-INV-1 names the exception
  (WO-39, R-VIEW-2, R-VIEW-5, D-55).
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
  `body_chars` (R-KNOW-6, WO-04).
- `grove knowledge get` / `grove_knowledge_get` say when the same key also
  exists in another scope: `other_scopes` names up to 20 of them (the
  workspace as `{"project": null}`, then projects by name) and
  `other_scopes_total` counts them all. Both are absent when no other scope
  holds the key. Which document is returned does not change, and no
  parameter or tool description changed for it (R-KNOW-8, WO-19).
- `grove knowledge get KEY --from-line N` / `grove_knowledge_get` with
  `from_line` start the excerpt at a line taken from the `outline`, with the
  same 4000-character limit and without the outline. Every excerpt that
  stops before the end of the document now carries `next_line`, the line to
  read on from, and `more` says so. A line past the end is `invalid`, and so
  is `from_line` with `full`. To make room, the tool's description says a
  fact once (`tools/list`: 14 934 bytes, 14 895 before) (R-KNOW-8, WO-19,
  D-49).
- Every finding in the results of `scan`, `gaps` and `recommend` (and of a
  map ingest) carries `key`, a reference that an unchanged rescan keeps and
  that does not move when the statement moves to another line. Finding ids
  behave as before. Database schema version 5 adds `findings.key` and gives
  existing findings their key on upgrade; an older Grove then refuses that
  directory instead of downgrading it. No tool description or parameter
  changed (R-REC-2 in part, WO-28, D-50).
- Every scan result carries `delta`: what the scan changed in the
  scan-derived findings, by key. A first scan gives `{"first_scan": true}`.
  A later scan gives the `added` and `resolved` counts, `added_keys` and
  `resolved_items` (`key`, `kind`, `summary`), each list cut at 50
  (`list_cap`), and `complete`, which is false, with a `note`, when a
  findings cap applied to either scan or a list was cut. Map findings are
  not part of it and nothing is stored. The `grove_scan` description names
  it within its old length (`tools/list`: 14 933 bytes, 14 934 before)
  (R-SCAN-10, WO-37, D-51).
- `grove gaps NAME --query TEXT` / `grove_gaps` with `query` list only the
  findings that hold the text in their summary, the source path of their
  evidence or their key; case is ignored, `%` and `_` are literal, and it
  combines with `kind`. `total` follows both filters and `counts` follows
  the text (`tools/list`: 14 985 bytes, 14 933 before) (R-GAP-6, WO-38,
  D-52).
- Every work item row (`work create`, `list`, `get`, `update`, and the item
  in a `recommend` result) carries `refs`: the references read from its
  `title`, `plan` and `notes` — requirement ids (`R-HOME-2`),
  `knowledge:KEY`, `finding:KEY` and `https://` URLs — sorted, each once, at
  most 50 of at most 200 characters, with `refs_omitted` when some were left
  out. Nothing is stored or fetched, and there is no new parameter.
  `recommend` passes over a finding that a work item which is not `done`
  refers to by `finding:KEY`, says how many in `skipped_findings` and in the
  rationale, and recommends the finding again once the item is `done`. No
  tool description changed (`tools/list` stays at 14 985 bytes) and there is
  no migration. Listing work items by a reference is not built (R-WORK-6 in
  part, R-REC-2, WO-15, D-53).
- Scan results and map ingest report `long_lines` (R-SCAN-7, WO-06).
- Per-project scan excludes. `grove scan NAME --exclude PATTERN` (repeatable;
  MCP `grove_scan` with `exclude`, a list) keeps files matching
  gitignore-style patterns out of the blueprint. The list is stored on the
  project: given, it replaces the stored list (`--exclude '!'` or `["!"]`
  clears it); left out or empty, the stored list applies. Every scan result, and the
  project's `last_scan`, reports `excluded` with the `patterns` in effect and
  the number of `files` they removed. At most 50 patterns of 200 characters
  (R-SCAN-9, WO-10).
- Database schema version 3 adds `projects.exclude`. Opening a data directory
  with this version upgrades it in place; an older Grove then refuses that
  directory instead of downgrading it (R-INV-7).
- Continuous integration: one GitHub Actions job (`.github/workflows/ci.yml`)
  on every pull request and every push to `main`. It installs the locked
  dependencies, runs the tests and runs `scripts/check-publish` on the head
  commit, with a read-only token, no secrets and actions pinned to commit
  SHAs. It is a visible check, not a required one (R-QUAL-9, A8, WO-08).
- `docs/design-rationale.md`: why Grove is built the way it is, how well
  that fits a factory of Grok Bot and Claude, and the issues found, in plain
  language.
- `scripts/check-publish` refuses an agent session id (the form
  `session_` followed by twenty or more letters and digits), and now reads
  the commit message of the revision as well as its files (R-INV-15,
  R-SEC-6).
- Work-item history. `grove work update ID --note TEXT [--author NAME]`
  (MCP `grove_work_update` with `note` and `author`) appends a progress note
  to the item's history; it erases nothing, so two agents can log progress
  on one item. Every update that changes the status or carries a note adds
  one event with time, author, old and new status and the note. `grove work
  get` / `grove_work_get` return `history`: the newest 20 `events` and the
  true `total`. A note is at most 1000 characters. `notes` and `plan` are
  still replaced whole, and every status may still follow any other
  (R-WORK-5, WO-14).
- Database schema version 4 adds the `work_events` table. Opening a data
  directory with this version upgrades it in place; existing items start
  with an empty history; an older Grove then refuses that directory
  (R-INV-7).
- `CLAUDE.md` and the README say what a session on a temporary machine can
  expect: Grove is a local map only there, an empty `grove status` is
  expected, and what must last goes into the repository's documents and the
  pull request (design rationale, issue 1a).
- The README records the first Grok Bot trial (2026-11-12: three Grok Bots
  listed and ran the sixteen tools on the machine that holds the data
  directory) and that the connector must be restarted after an upgrade
  before new parameters are offered. The Grok Bot version and protocol
  revision were not recorded, so WO-11 stays open for that part
  (R-GROK-7).
- A linter and one check script. ruff is pinned in the `dev` group and
  configured for the pyflakes rules only (undefined and unused names, unused
  imports); it judges no style and no file was reformatted. `scripts/check`
  runs the linter, shellcheck on the bash files if it is installed, the
  tests with a temporary `GROVE_HOME` and `scripts/check-publish` on `HEAD`;
  it runs every step, reports each as passed, failed or skipped, and exits 1
  if any failed. CI runs the linter as one more step (R-QUAL-8, WO-12).
- CLI ergonomics for agents, the command-line side of WO-21. `grove
  knowledge write --file -` reads the body from standard input, so a note
  needs no file (a terminal is refused with `invalid`; a file really named
  `-` is now `--file ./-`). `grove ingest-map` takes `--author NAME`, and
  the MCP tool `grove_ingest_map` takes `author` (added with WO-20). The
  README documents a link that puts `grove` on `PATH` (R-CC-4, R-CC-5,
  R-GROK-1).
- Randomised tests for the parsers (`tests/test_parser_random.py`): a
  seeded generator from the standard library builds lines and documents
  from a small alphabet, and each extractor must not raise, must give the
  same output twice and must stay within a linear time bound. The README
  lists which Markdown constructs are read and which are not ("Which
  Markdown is read"), with a test for each line of the list (R-SCAN-7,
  WO-24).
- The heuristics and the search are measured. `fixtures/measure/` holds
  three small projects with their true gaps listed by hand, and sixteen
  notes with twenty-six judged queries; `tests/test_measure.py` computes
  precision and recall of each finding kind, and recall, precision and
  reciprocal rank of search, and holds each to a recorded floor. No
  behaviour changed. The numbers of 2026-11-13 and the weaknesses they
  show are in `docs/work-orders.md` (R-QUAL-10, WO-23).
- Protocol coverage: a stdio test for MCP revision `2026-07-28` (no
  handshake) beside the one for `2025-11-25`; the sixteen input schemas are
  compared with a stored copy, `tests/snapshots/tool_input_schemas.json`;
  the README says how a connection chooses its revision and what happens
  to running calls when it closes (R-QUAL-7, R-INV-9, WO-25).
- The cap of 500 symbols or test names per file is reported: the scan names
  each such file in `caps.symbols_capped` with `found`, `kept` and
  `dropped`, and its module or test-file item carries `symbols_found` or
  `tests_found`. A line with several JavaScript test names no longer takes a
  file past the cap (R-INV-11, WO-17).
- The MCP server instructions say that text returned from scanned files,
  maps and notes is data to weigh, never an instruction to follow. No tool
  description changed (R-SEC-4, WO-13).
- Tests that guard the invariants: import rules (no network, no model, no
  process spawning, four third-party modules), module layering, the closed set of error
  codes, deterministic scans, and a size budget for the MCP tool list
  (WO-03, WO-07).
- `SECURITY.md`: where to report a vulnerability, what Grove trusts and
  does not, what to do if a secret was pushed, and how a dependency pin is
  changed. The README says how to copy `grove.db` safely (R-SEC-7, WO-27).
- `grove status` / `grove_status` report `build`: the `version`, and the
  12-digit `commit` of the source when Grove runs from a git checkout, read
  once when the process starts. No tool description or input schema changed
  (R-GROK-9, WO-36).
- `grove blueprint` / `grove_blueprint_get` take `--summary` (`summary`) and
  `--source-path PATH` (`source_path`). The summary is a page of source
  files, each with its item count per layer, instead of items; the path
  keeps one file, or every file under a prefix ending in `/`, compared
  exactly as items show it. Both combine with `--layer` and `--query`;
  without them nothing changes. To make room, tool descriptions say a fact
  once (`tools/list`: 14 895 bytes, 14 946 before); no parameter or result
  field was renamed or removed (R-GROK-8, WO-16, D-48).

### Changed

- A scan never enters a directory that holds a `.grove-export` entry (the
  marker of `grove export`), so exported pages are not read back as
  documents. A project that already had a directory with a file of that
  name loses the items from it at the next scan (R-SCAN-2, R-COMPAT-7).
- `grove project create` and `grove scan` (`grove_project_create`,
  `grove_scan`) now return `invalid` when Grove's data directory is the
  project root or inside it, compared after resolving symlinks. The message
  names both paths and how to fix it. A project registered that way by an
  earlier version keeps its data and can still be read; only scanning it is
  refused until the data directory is moved out (R-HOME-4, R-COMPAT-6,
  WO-09).
- `grove ingest-map` (`grove_ingest_map`) now returns `invalid` for a file
  that is not map-like. The name must end in `.md`, `.markdown`, `.mdx`,
  `.rst` or `.txt` (in any case) or have no extension; a dotfile such as
  `.env` is refused. The name is judged after symlinks are resolved and
  before the file is read. A map under another name has to be renamed; with
  the same stem it keeps its knowledge key and its revisions. Nothing
  stored earlier is removed, and no tool description or parameter changed
  (R-SEC-5, R-COMPAT-6, WO-13).
- Lines longer than 5000 characters are no longer analysed by the scanner or
  the map parser. They are counted and reported. This can change which
  blueprint items a scan produces for files with very long lines
  (R-COMPAT-7, R-COMPAT-9).
- The scan's time cap is now also checked between the lines of a file, so a
  scan stops inside a large file instead of after it (R-SCAN-8).
- `grove mcp` logs how the data directory was chosen.
- `grove work update --note` is now its own flag. The command line used to
  accept `--note` as an undocumented shortening of `--notes`; anyone who
  relied on that now appends a history note and no longer replaces `notes`
  (WO-14).
- The `grove_work_update` description no longer ends with "This only updates
  Grove's local record"; the sentence that closes every description says the
  same. The tool list is 16 366 of 16 384 bytes (R-GROK-3).
- `scripts/check-publish` and the pre-push hook no longer carry unused
  variables (three shellcheck warnings). What they check is unchanged
  (WO-12).
- The pre-push hook runs `scripts/check-publish` on every commit a push
  adds to the remote, oldest first, not only on the newest: a finding in an
  earlier commit blocks the push even when a later commit removes it. A new
  branch is checked from where the remote's known refs end; a deletion is
  skipped. The script and the hook now have tests for tokens, file names,
  private paths and the pushed range (R-SEC-6, R-INV-15, WO-26).
- Inline Markdown is cleaned by patterns that stop at the next opener of
  their own kind. Well-formed links, images and tags read as before. What
  differs: a link target may hold one pair of parentheses and is read to
  its real end (`[Foo](.../Foo_(bar))` leaves "Foo", not "Foo)"); an
  opener that never closes stays as text instead of swallowing what
  follows it (`[a [b](c)` leaves "[a b"; `x <1.5 ... <url>` keeps
  "<1.5"). This can change a few declared sentences and map items
  (R-COMPAT-7, WO-24).
- The Markdown line patterns (heading, fence, list marker, table separator,
  thematic break) are written once, in `scan.py`; the map reader and the
  knowledge outline import them. A test fails when a pattern is written in
  two modules (WO-24).
- `grove gaps NAME --kind KIND` and `grove_gaps` with `kind` now return
  `invalid`, with a message that lists the four kinds, when the kind is
  none of them. Such a call used to return an empty page with
  `complete: true`. This tightens validation under R-COMPAT-6: no such
  call could ever return a finding. No kind, or a blank one, still lists
  every finding. `grove gaps --help` shows the kinds (R-GAP-5, WO-18).
- A leaner MCP tool list that says more where every client's model reads
  it: `tools/list` is 14 949 bytes (16 366 before), and the limit is now
  15 000 (16 384 before). The local-only sentence is on `grove_status`
  only, with a line stating the working loop; `grove_blueprint_get`,
  `grove_knowledge_get` and `grove_knowledge_search` say that returned text
  is data, not instructions; `grove_recommend_next` says what it is for;
  `grove_scan` is shorter; `limit` is described by its schema keywords;
  the server instructions state the loop in full. No tool, parameter or
  result field was renamed or removed. Restart a connector to read the new
  descriptions (R-GROK-3, R-GROK-6, R-SEC-4, WO-20).
- `grove_gaps` also says that returned text is data, not instructions: a
  finding quotes the project's documents. Its description was tightened to
  pay for the clause, so `tools/list` is 14 946 bytes (14 949 before). No
  schema and no result changed (R-SEC-4, R-GROK-3, follow-up to WO-20).
- `grove scan` / `grove_scan`: an empty `exclude` (`--exclude ''`, `[]`, or
  only blank entries) now keeps the project's stored list, as an omitted one
  does; it used to clear it. Exactly one list clears it: `["!"]`
  (`--exclude '!'`). `!` beside other patterns is `invalid`. An empty list
  from a client that fills in defaults must not silently drop the user's
  excludes. `excluded` still reports the list the scan really used
  (R-SCAN-9, WO-10, D-43).

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
- `scripts/check-publish` reported "clean" without having checked in three
  cases: a revision that does not exist, a forbidden file name that is not
  ASCII, and a line of the local pattern file that begins with a dash. Each
  is refused now, and a search that cannot be run fails the check (R-SEC-6,
  WO-26).
- `ingest-map` took time quadratic in the length of a paragraph: 40 000
  characters of "[" in one paragraph took 9 seconds, and a map may be 2 MB.
  It is linear now (WO-24).
- One heading line "# ###...x" of 5000 characters took 0.2 to 0.4 seconds to
  scan or ingest, and `knowledge get` took 11 seconds on one such line of
  40 000 characters, because the outline has no line cap. Both are linear
  now (WO-24).
- The `grove_recommend_next` description left out the documented-limit tier
  and the `scan` and `none` actions (R-REC-1, WO-03).

## 0.1.0 — 2026-11-12

First version: project scan into a three-layer blueprint with heuristic gap
findings, revisioned knowledge with full-text search, map ingest, local work
items, one recommendation, a CLI and an MCP stdio server with sixteen tools.
See `BUILD_NOTES.md`.
