# Grove work orders

The orders for upgrading Grove as a software-factory workshop, in priority
order. Each order names the requirements it makes true (`REQUIREMENTS.md`),
where the need comes from (`docs/analysis.md`, `docs/industry-survey.md`),
and how to tell it is done. The definition of done in `REQUIREMENTS.md`,
section 11, applies to every order and is not repeated.

- **Must** — before more feature work. An agent should not build on Grove
  until these hold.
- **Should** — the upgrades that make Grove good at its job for Grok Bot and
  Claude Code.
- **Later** — worth doing, not yet urgent, or waiting for a decision.

Sizing rule: one order is one reviewable change. If an order grows past
about 400 changed lines, split it and keep the ids (`WO-14a`, `WO-14b`).

Status: **done** (in the change that introduced this file), **open**, or
**waiting** (for a decision by the owner; the question is named).

## Summary

| Id | Title | Priority | Kind | Status |
|---|---|---|---|---|
| WO-01 | Requirements, blueprint and decision log in the repository | must | docs | done |
| WO-02 | One data-directory rule, and a status that shows it | must | both | done |
| WO-03 | Tool descriptions as a tested contract | must | both | done |
| WO-04 | List knowledge without a query | must | both | done |
| WO-05 | Reliable concurrent first open | must | code | done |
| WO-06 | Scan time bounded by input size | must | both | done |
| WO-07 | Invariants as fitness tests | must | code | done |
| WO-08 | An automated gate for every change (CI) | must | infrastructure | waiting (A8) |
| WO-09 | Refuse a data directory inside a project root | must | both | open |
| WO-10 | Per-project scan excludes | must | both | open |
| WO-11 | Verify the Grok Bot registration for real | must | verification | open |
| WO-12 | Static quality gates: lint, format, types, coverage floor | must | code | open |
| WO-13 | Untrusted text: marking, hidden characters, map file types | should | both | open |
| WO-14 | Work-item history and safe concurrent edits | should | both | open |
| WO-15 | Traceability on work items: acceptance, links, evidence, review | should | both | open |
| WO-16 | Cheap blueprint navigation | should | both | open |
| WO-17 | Report the remaining silent caps | should | both | open |
| WO-18 | Validate `kind`; settle the path rule | should | both | open |
| WO-19 | Knowledge scope and partial reads | should | both | open |
| WO-20 | A leaner, more instructive MCP surface | should | both | open |
| WO-21 | CLI ergonomics for agents | should | both | open |
| WO-22 | Requirement files and explicit ids in the declared layer | should | both | open |
| WO-23 | Measure the heuristics and the search | should | code | open |
| WO-24 | Property and fuzz tests for the parsers | should | code | open |
| WO-25 | Protocol coverage and structured results | should | both | open |
| WO-26 | Harden and test the publish check | should | code | open |
| WO-27 | Repository health: security policy, contributing, releases, dependency review | should | docs | waiting (contact address) |
| WO-28 | Stable finding keys, links and waivers | later | both | open |
| WO-29 | Unfinished work in `recommend` | later | both | waiting (A2) |
| WO-30 | Archive without deleting | later | both | waiting (A3) |
| WO-31 | Test results in the tests layer | later | both | open |
| WO-32 | Export and backup | later | both | open |
| WO-33 | Text policy: Unicode, case, paths | later | both | open |
| WO-34 | Verify macOS and Windows | later | verification | open |
| WO-35 | Scanner precision, measured | later | code | open |

## Must

### WO-01 — Requirements, blueprint and decision log in the repository *(done)*

- **Goal.** One document to implement against, one to understand the
  structure, one list of decisions.
- **Rationale.** The rules for changing Grove were spread over README,
  `BUILD_NOTES.md`, tool descriptions, one test and a spec outside the
  repository (analysis 3.2). Survey C: decision records, architecture file.
- **Acceptance.** `REQUIREMENTS.md` with stable ids and a status per
  requirement; `docs/blueprint.md` with module map, data model, operation
  map, traceability and decision log; README, `CLAUDE.md` and
  `BUILD_NOTES.md` contradict none of it; a test ties the documents to the
  code.
- **Kind.** docs (+ `tests/test_docs_contract.py`).

### WO-02 — One data-directory rule, and a status that shows it *(done)*

- **Goal.** No agent works in an empty `~/.grove` by accident.
- **Rationale.** R-HOME-2, R-HOME-3, R-HOME-6. The documents disagreed about
  where the data lives and told agents to rely on `export`, which does not
  persist between an agent's shell calls (analysis 3.4).
- **Acceptance.** `grove_status` returns `home_source` and a `hint` when the
  directory has no projects; the README's Grok Bot and Claude Code
  registrations set `GROVE_HOME`; `CLAUDE.md` says to pass `--home` or
  configure the variable outside the shell, and to confirm with `status`.
- **Kind.** both. Tests: `tests/test_status.py`.

### WO-03 — Tool descriptions as a tested contract *(done)*

- **Goal.** What an MCP client reads about a tool is true.
- **Rationale.** R-GROK-2, R-GROK-3, R-REC-1. The `grove_recommend_next`
  description listed five tiers; the code has six and two more actions.
- **Acceptance.** The description names every action in
  `service.RECOMMEND_ACTIONS` in order; a test fails if an action is added
  without it; the `tools/list` payload has a tested size budget.
- **Kind.** both. Tests: `tests/test_docs_contract.py`.

### WO-04 — List knowledge without a query *(done)*

- **Goal.** An agent can see what is known without inventing a search.
- **Rationale.** R-KNOW-6. `search "*"` was an error and there was no list.
- **Acceptance.** `grove_knowledge_search` and `grove search` without a query
  return the latest revision of every document, newest first, without
  bodies, with `body_chars` and `mode: "list"`; a project filter and paging
  work; an empty query string is still `invalid`.
- **Kind.** both. Tests: `tests/test_knowledge.py`.

### WO-05 — Reliable concurrent first open *(done)*

- **Goal.** Two agents starting on a fresh data directory never see
  "database is locked".
- **Rationale.** R-HOME-8, R-QUAL-1. Measured: 15 of 400 concurrent first
  opens failed at `PRAGMA journal_mode = WAL`, and the existing test for it
  failed about once in thirty runs (analysis 3.1).
- **Acceptance.** The switch to WAL is retried within the busy budget; a
  deterministic test of the retry; a stress test of 60 fresh homes opened by
  8 threads each; 1500 stress runs without a failure recorded in the
  analysis.
- **Kind.** code. Tests: `tests/test_db.py`.

### WO-06 — Scan time bounded by input size *(done)*

- **Goal.** No file can make a scan run far past its time cap.
- **Rationale.** R-SCAN-7, R-SCAN-8, R-INV-11. Measured: one 40 000-character
  line in a README took 13.6 s to analyse, and a 20 000-line paragraph 7.8 s;
  both grow quadratically; the time cap was checked only between files
  (analysis 3.1). Survey F: catastrophic backtracking; survey E: fuzzing for
  slowness.
- **Acceptance.** The table-separator pattern is linear; lines over 5000
  characters are skipped and reported (`long_lines`, a warning, on the
  project); the time cap is checked between lines; the paragraph line lookup
  is linear; a byte order mark no longer hides line 1; tests cover each.
- **Kind.** both. Tests: `tests/test_scan_robustness.py`.

### WO-07 — Invariants as fitness tests *(done)*

- **Goal.** A change that adds a network call, a model, a subprocess or a
  layering violation fails the suite.
- **Rationale.** R-INV-1, R-INV-2, R-INV-3, R-QUAL-2, R-QUAL-3, R-SEC-1,
  R-COMPAT-4. The invariants were prose only. Survey J: import rules as
  checks.
- **Acceptance.** Import allow-list and layering table tested by AST; no
  `eval`/`exec`/process calls; error codes closed; ordinary commands do not
  load the MCP SDK; two scans of the same tree give identical results.
- **Kind.** code. Tests: `tests/test_invariants.py`.

### WO-08 — An automated gate for every change (CI) *(waiting: A8)*

- **Goal.** Every pull request is tested on a clean machine, not only on the
  author's.
- **Rationale.** R-QUAL-9. There is no CI; the only gate is a local hook that
  each clone must enable by hand. Survey I and J: continuous integration,
  and how to run it safely on a public repository.
- **Acceptance.**
  1. One workflow, triggered by `pull_request` and by pushes to `main`,
     never by `pull_request_target`.
  2. `permissions: contents: read` at the top; no secrets used.
  3. Steps: check out with full history; install uv; `uv sync --locked`;
     `uv run pytest -q`; `scripts/check-publish` on every commit of the
     pull request.
  4. Every action pinned to a full commit SHA; first-party actions only,
     plus the uv installer if the owner accepts it.
  5. No value from the pull request (title, branch name) is interpolated
     into a script.
  6. A workflow linter passes on the file.
  7. `CLAUDE.md` and section 11 of `REQUIREMENTS.md` name the gate.
- **Kind.** infrastructure. **Needs the owner:** adding CI changes what runs
  on GitHub for every contributor.

### WO-09 — Refuse a data directory inside a project root *(open)*

- **Goal.** "Grove never writes inside a scanned project" holds even when the
  home is misconfigured.
- **Rationale.** R-HOME-4, R-INV-4. Observed: with the home inside the root,
  `project create` and `scan` succeed and `grove.db` is written inside the
  project (analysis 3.3).
- **Acceptance.** `project_create` and `scan` return `invalid` when the
  resolved data directory is the project root or inside it, with a message
  that names both paths and the remedy; paths are compared after resolving
  symlinks; tests for both operations; the `status` hint mentions it.
  Existing registrations that violate the rule keep their data and can be
  read; only scanning is refused.
- **Kind.** both (a tightening under R-COMPAT-6; changelog entry).

### WO-10 — Per-project scan excludes *(open)*

- **Goal.** Fixtures, examples, vendored code and non-normative documents stay
  out of a project's blueprint.
- **Rationale.** R-SCAN-9. Measured on Grove's own repository: the analysis,
  survey and work-order documents added by this change raise the declared
  layer from 128 to 1355 items, nearly all of which are not product promises, and
  `fixtures/tiny` appears as product code (analysis 3.6).
- **Acceptance.** Migration 3 adds `projects.exclude` (JSON list of
  gitignore-style patterns); `grove_project_create` takes optional
  `exclude`; an existing project's list can be replaced through an optional
  parameter of an existing tool (proposed: `grove_scan`, which then stores
  it); the scan result reports `excluded` (count and patterns) so the
  exclusion is never silent; Grove still writes nothing inside the project;
  upgrade test from schema 2.
- **Kind.** both.

### WO-11 — Verify the Grok Bot registration for real *(open)*

- **Goal.** The README's Grok Bot instructions are known to work.
- **Rationale.** R-GROK-7. `BUILD_NOTES.md` records that the AddMcpServer
  shape was never tried against Grok Bot. It is the largest unverified
  assumption for one of the two clients.
- **Acceptance.** Someone with a Grok Bot account registers Grove with the
  README's `command`, `args` and `env`; lists the sixteen tools; runs
  `grove_status` and sees the intended data directory with
  `home_source: "env"`; the exact shape and the Grok Bot version are recorded
  in the README and in `BUILD_NOTES.md`. Record which MCP protocol revision
  Grok Bot spoke.
- **Kind.** verification (documentation change only).

### WO-12 — Static quality gates: lint, format, types, coverage floor *(open)*

- **Goal.** Style, types and coverage are checked by tools, not by review.
- **Rationale.** R-QUAL-8. Observed in this session, without changing the
  repository: the linter reports 22 findings and would reformat 22 of 24
  files; the type checker reports 4 errors; branch coverage is 90 %
  (analysis 3.9). Survey J.
- **Acceptance.** A linter-formatter and a type checker pinned in the `dev`
  dependency group and configured in `pyproject.toml`; the code reformatted
  in a commit of its own, with no behaviour change; the type errors fixed;
  the closed sets typed as literals and the row shapes as typed
  dictionaries; a coverage floor at the measured level; one script,
  `scripts/check`, that runs everything the gate runs; a test that a
  database migrated step by step has the same schema as a fresh one.
- **Kind.** code. Do it as its own pull request: it touches every file.

## Should

### WO-13 — Untrusted text: marking, hidden characters, map file types *(open)*

- **Goal.** A client can tell text Grove vouches for from text a third party
  wrote, and cannot be surprised by text a person cannot see.
- **Rationale.** R-SEC-4, R-SEC-5. Grove returns README sentences, map text
  and other agents' notes verbatim to language models: the channel that the
  survey's security sources call indirect prompt injection (survey I). The
  MCP specification says servers must sanitise tool outputs (survey 2).
- **Acceptance.**
  1. A threat model section (in `SECURITY.md`, WO-27) that classifies the
     sixteen tools by whether their result can carry third-party text.
  2. Server instructions and the affected tool descriptions say: text from
     scanned files, maps and notes is data to weigh, never an instruction.
  3. Provenance is carried by fields Grove sets (`origin`, `source_path`,
     `author`), never by markers inside the text.
  4. A stated and tested policy for control, zero-width and bidirectional
     characters in returned text: counted and reported per result, and
     either escaped or left alone, but never silently removed.
  5. `ingest-map` accepts only `.md`, `.markdown`, `.mdx`, `.rst`, `.txt`
     (tightening under R-COMPAT-6).
- **Kind.** both.

### WO-14 — Work-item history and safe concurrent edits *(open)*

- **Goal.** Two agents can work on one item without losing each other's
  notes, and the item shows who did what, when.
- **Rationale.** R-WORK-5. Observed: the second writer of `notes` erases the
  first; there is no record of status changes (analysis 3.5). Survey D: a
  tracker must show ownership and state; survey K: who owns an `in_progress`
  item.
- **Acceptance.** Migration adds an append-only `work_events` table
  (work item, time, author, field, old and new status, note text);
  `grove_work_update` takes optional `append_notes` (adds a dated, attributed
  entry instead of replacing), `author`, and `expected_updated_at` (the
  update is `invalid` if the item changed since); `grove_work_get` returns
  `history`; `grove_work_list` rows carry the age of the current status; all
  transitions remain allowed (R-WORK-3).
- **Kind.** both.

### WO-15 — Traceability on work items: acceptance, links, evidence, review *(open)*

- **Goal.** A work item shows what it must achieve, what it relates to, and
  what was shown before it was called done.
- **Rationale.** R-WORK-6, section 11.2. Survey C and D: typed items with
  links; "done" needs evidence; a short review checklist.
- **Acceptance.** Optional fields on create and update: `acceptance` (text);
  `links` (list of `{type, ref}` with type in `requirement`, `knowledge`,
  `finding`, `work`, `change`, `url`; stored as text, never fetched);
  `evidence` (text: the commands run and their outcome, as reported);
  `reviewer`. `grove_work_list` can filter by a link. A `review → done`
  update without `evidence` and `reviewer` succeeds but returns a `warnings`
  entry: Grove records, it does not block (R-WORK-3).
- **Kind.** both. Depends on WO-14 for the migration.

### WO-16 — Cheap blueprint navigation *(open)*

- **Goal.** An agent finds the part of a blueprint it needs without paging
  all of it.
- **Rationale.** R-GROK-8. Measured: one page of 128 declared items is 44 KB;
  a project with 20 000 declared items would need 100 such pages.
- **Acceptance.** `grove_blueprint_get` takes optional `summary` (per source
  file: counts by layer and class, no items), `source_path` (exact path or
  prefix ending in `/`), `class`, and `compact` (omit `body` and `extra`);
  each is paged and tested on both surfaces.
- **Kind.** both.

### WO-17 — Report the remaining silent caps *(open)*

- **Goal.** R-INV-11 holds without exceptions.
- **Rationale.** Section 8 of `REQUIREMENTS.md` lists four caps that are not
  reported: 500 symbols per file, 40 names in a body, title and body
  clipping, and dropped short sentences.
- **Acceptance.** The scan result gains `caps.symbols_capped` (files, with
  counts) and counts of clipped titles, clipped bodies and dropped short
  sentences; module and test-file items carry the true count in `extra`;
  README lists them.
- **Kind.** both.

### WO-18 — Validate `kind`; settle the path rule *(open)*

- **Goal.** A typo is an error, not an empty answer.
- **Rationale.** R-GAP-5, R-IF-8. Observed: `gaps --kind declared_untestd`
  returns `ok` with no items and `complete: true`.
- **Acceptance.** `kind` is an enum in the schema and is validated in the
  service (`invalid`, listing the kinds); the CLI offers the choices. For
  paths, either keep R-IF-8 and add `resolved_from` (the working directory
  used) to results that take a relative path, or reject relative paths over
  MCP: the owner chooses (A9).
- **Kind.** both (tightening under R-COMPAT-6).

### WO-19 — Knowledge scope and partial reads *(open)*

- **Goal.** No surprise about which document was returned, and no need to
  fetch 2 MB to read one section.
- **Rationale.** R-KNOW-8. Observed: with the same key in the workspace and a
  project, `knowledge get KEY` returns the workspace document and says
  nothing of the other. Survey K: caller-chosen size budgets.
- **Acceptance.** `grove_knowledge_get` returns `other_scopes` (names of
  other scopes holding the key); takes optional `section` (heading title or
  line number from the outline) or `offset` with `max_chars`, and reports
  what was returned and what remains; `grove_knowledge_search` takes
  optional `include_workspace` (default false, R-KNOW-7).
- **Kind.** both.

### WO-20 — A leaner, more instructive MCP surface *(open)*

- **Goal.** Less context spent per session, and the working loop stated once.
- **Rationale.** R-GROK-3, R-GROK-6, R-COMPAT-7. Measured: `tools/list` is
  15.1 KB; the same 93-character sentence ends all sixteen descriptions
  (1.5 KB). Survey A: measure the cost of descriptions; example-first help.
- **Acceptance.** The local-only sentence moves to the server instructions
  (the test that requires it per description is changed to check the
  instructions and the annotations); instructions state the loop of R-GROK-6
  and that blueprint and finding ids are not stable; the three longest
  descriptions are tightened; the budget in R-GROK-3 drops to 12 KB;
  `grove_project_list` rows omit `last_scan` unless `full` is asked;
  every page carries `next_offset` (or `null`); `idempotentHint` is set where
  true.
- **Kind.** both.

### WO-21 — CLI ergonomics for agents *(open)*

- **Goal.** Claude Code can do everything from a shell without temporary
  files in the project, from any directory.
- **Rationale.** R-CC-4, R-CC-5, R-GROK-1. Observed: `knowledge write
  --file -` fails with `not_found`. Survey 2: `-` for stdin is the
  convention.
- **Acceptance.** `knowledge write` accepts `--file -` (stdin) and
  `--body TEXT` (exactly one of the three); `ingest-map` and
  `grove_ingest_map` take `author`; the README documents installing `grove`
  on `PATH`; an `AGENTS.md` that points to the same rules as `CLAUDE.md`
  exists if WO-11 shows Grok Bot reads one.
- **Kind.** both.

### WO-22 — Requirement files and explicit ids in the declared layer *(open)*

- **Goal.** The strongest claims a project makes are the ones Grove reads,
  and an explicit link beats a guess.
- **Rationale.** A7. Grove does not read `REQUIREMENTS.md`, its own most
  normative file (blueprint 6). Survey C: reference documentation is the
  kind that makes claims; a requirement id named in a test is a real trace.
- **Acceptance.** `REQUIREMENTS*`, `SPEC*`, `SPECIFICATION*` and `SECURITY*`
  files join the declared layer (changelog entry, R-COMPAT-7). A declared
  item whose text carries an id of the form `R-AREA-n` (pattern configurable
  per project later) records it in `extra.requirement_id`. A test whose name
  or file mentions that id (`test_r_home_2_...`) counts as covering it
  regardless of token overlap, and the finding evidence says which rule
  matched. Agent instruction files stay out.
- **Kind.** both. Best after WO-10.

### WO-23 — Measure the heuristics and the search *(open)*

- **Goal.** Know how often a finding is right, and notice when a change makes
  it worse.
- **Rationale.** R-QUAL-10. `BUILD_NOTES.md`: precision and recall were never
  measured. Survey G: documents, queries, judgments.
- **Acceptance.** A fixture corpus of small projects with a hand-labelled
  list of true gaps; a test that reports precision and recall per finding
  kind and fails below a recorded floor; twenty or more search queries with
  the documents that should be found, tested as known-item checks; the
  numbers recorded in `BUILD_NOTES.md` or a results file, with the date.
- **Kind.** code (tests and fixtures only).

### WO-24 — Property and fuzz tests for the parsers *(open)*

- **Goal.** The extractors never raise, never hang and never differ between
  runs, whatever the input.
- **Rationale.** R-SCAN-7, R-INV-3. This survey found three superlinear paths
  by hand; a generator would have found them sooner. Survey E.
- **Acceptance.** A property-based testing library in the `dev` group only;
  properties for `extract_declared`, `extract_symbols`,
  `extract_test_names`, `parse_map`, `classify`, `tokens`, the FTS query
  builder and `clean_inline`: no exception, time within a bound that is
  linear in input size, same output twice; a corpus of awkward strings run
  through keys, titles, bodies and queries; README states which Markdown
  constructs are read (headings, paragraphs, lists, tables, fences, front
  matter) and which are not.
- **Kind.** code.

### WO-25 — Protocol coverage and structured results *(open)*

- **Goal.** Both protocol eras are tested, and the question of structured
  results is decided.
- **Rationale.** R-QUAL-7, D-11. Observed by hand: the server answers
  `server/discover`, `tools/list` and `tools/call` without a handshake;
  responses to calls still running when stdin closes are dropped. No test
  covers either. Survey 2.
- **Acceptance.** A stdio test for the `2026-07-28` revision; a stored
  snapshot of the sixteen input schemas that a test compares; a differential
  test that the CLI and `call_tool` return the same `data` for the same
  operation; the shutdown behaviour documented; a decision row on
  `structuredContent` and `outputSchema` (recommended: add both, keep the
  text block, as the specification advises for compatibility).
- **Kind.** both.

### WO-26 — Harden and test the publish check *(open)*

- **Goal.** The last guard before a public push is itself tested and covers
  every commit pushed.
- **Rationale.** R-SEC-6, R-INV-15. The hook checks only the tip of each
  ref, so a secret added and removed within one push passes; the script has
  no tests; the shell linter reports an unused variable. Survey I: pushed
  commits stay retrievable.
- **Acceptance.** The hook checks every new commit in the pushed range (the
  remote SHA it already receives gives the range); tests (from pytest, in a
  temporary repository) show a planted fake token, a forbidden file name and
  a private-path pattern are each caught and a clean tree passes; the shell
  linter is clean; a check for bidirectional control characters in tracked
  source; optionally a maintained secret scanner as a second layer in CI.
- **Kind.** code.

### WO-27 — Repository health *(waiting: a contact address for reports)*

- **Goal.** A newcomer, human or agent, knows how to contribute, how to
  report a vulnerability and how releases and dependency updates happen.
- **Rationale.** R-SEC-7, R-COMPAT-8. There is no `SECURITY.md` and no
  `CONTRIBUTING.md`; `CHANGELOG.md` starts with this change.
- **Acceptance.** `SECURITY.md` (how to report, the threat model from WO-13,
  what to do if a secret was pushed: rotate first); `CONTRIBUTING.md` (set
  up, test, hook, definition of done, what will be declined); a release
  checklist (version, changelog, tag); a dependency policy (who reviews a
  pin change; a periodic audit of the locked set, run outside the product).
- **Kind.** docs. **Needs the owner:** the address for reports.

## Later

### WO-28 — Stable finding keys, links and waivers *(open)*

- **Goal.** A finding can be referred to tomorrow.
- **Rationale.** R-REC-2. Ids change on every scan; `recommend` can keep
  suggesting a finding that already has a work item.
- **Acceptance.** Each finding has a `key` derived from kind, source path
  and normalised text; work items link to keys (WO-15); `recommend` skips
  findings with an open linked item; a finding can be marked accepted with a
  reason (stored as knowledge), and is then listed separately.
- **Kind.** both.

### WO-29 — Unfinished work in `recommend` *(waiting: A2)*

- **Goal.** A returning agent is reminded of what it left open.
- **Acceptance (default, non-breaking).** `grove_recommend_next` adds
  `open_work`: counts and the oldest ids of `in_progress` and `review` items
  with their age. If the owner prefers a tier, add `resume_work_item` at the
  top and update R-REC-1.
- **Kind.** both.

### WO-30 — Archive without deleting *(waiting: A3)*

- **Goal.** Test projects and wrong notes can be hidden.
- **Acceptance.** An `archived` flag on projects, knowledge documents and
  work items, set through optional parameters of existing tools; archived
  rows are left out of lists and search unless asked for; nothing is
  deleted; `destructiveHint` stays false.
- **Kind.** both.

### WO-31 — Test results in the tests layer *(open)*

- **Goal.** The tests layer knows whether a test ran and passed, not only
  that it has a name.
- **Acceptance.** A read-only ingest of a result file the project's own
  tools produced (JUnit XML first), stored with its time; test items gain
  `last_result`; skipped and expected-failure states are shown. Grove still
  never runs tests.
- **Kind.** both.

### WO-32 — Export and backup *(open)*

- **Goal.** The store can be read and saved without touching `grove.db` by
  hand.
- **Acceptance.** `grove export DIR` writes knowledge (one Markdown file per
  document, all revisions) and work items (JSON) to a directory outside any
  project; the README documents a WAL-safe backup.
- **Kind.** both. Note: export is a seventeenth CLI command but not an MCP
  tool (R-INV-9 concerns tool names).

### WO-33 — Text policy: Unicode, case, paths *(open)*

- **Goal.** Equality and tokenising behave as documented for non-ASCII text.
- **Acceptance.** Stated and tested: normal form for keys, names and stored
  paths; case folding for comparisons; the tokeniser's ASCII-only rule, with
  a count of skipped non-ASCII identifiers in the scan result; behaviour for
  file names that are not valid UTF-8.
- **Kind.** both.

### WO-34 — Verify macOS and Windows *(open)*

- **Acceptance.** The suite passes on both; path, case and SQLite
  differences found are recorded; R-QUAL-6 updated.
- **Kind.** verification (through WO-08's matrix if CI exists).

### WO-35 — Scanner precision, measured *(open)*

- **Goal.** Improve what the scanner sees where measurement says it matters.
- **Acceptance.** Only after WO-23: candidates are TypeScript class methods,
  Go `type ( ... )` blocks, `describe` blocks, parametrised tests. Each is
  adopted only with a measured gain on the corpus. A syntax-tree dependency
  stays rejected (D-17) unless the owner reverses it.
- **Kind.** code.
