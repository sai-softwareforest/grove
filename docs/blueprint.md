# Grove blueprint

How Grove is built, and how a change to it is traced. This document is meant
to last: it describes structure and decisions, not the state of any one
task. What Grove *must* do is in `REQUIREMENTS.md`; this file says how the
code is arranged to do it. Tests in `tests/test_docs_contract.py` and
`tests/test_invariants.py` fail when the parts marked *(tested)* drift from
the code.

## 1. Context

```text
   Grok Bot ──MCP stdio──┐
                         ├──►  grove mcp  ──┐
   Claude Code ──MCP─────┘                  │
                                            ├──►  service.Grove  ──►  $GROVE_HOME/grove.db
   Claude Code ──shell──►  grove <command> ─┘          │
   a person    ──shell──►  grove <command> --text      │ read only
                                                       ▼
                                             project root directories
```

- Grove is started by its client, on the machine that holds the code and the
  data directory. There is no daemon and no network endpoint.
- Every CLI call and every MCP tool call opens its own SQLite connection,
  does one operation, and closes it. Nothing is cached between calls.
- Grove reads project directories and the files named in `ingest-map` and
  `knowledge write --file`. It writes only inside the data directory, and
  refuses to register or scan a project whose root holds that directory
  (R-HOME-4).

## 2. Building blocks

| Module | Responsibility | May import (siblings) | Main tests |
|---|---|---|---|
| `errors.py` | `GroveError`, the envelope (`ok`, `fail`), the four error codes, paging helpers | — | `test_cli.py`, `test_invariants.py` |
| `tokens.py` | Words of prose and identifiers for the overlap heuristic: split, lower-case, stop words, four suffix rules | — | `test_extractors.py` |
| `claims.py` | Class of a declared sentence: `behaviour`, `limit`, `setup`, `prose` | — | `test_claims.py` |
| `scan.py` | Read-only walk (`.gitignore`, skips, caps); the declared, actual and tests extractors; the line cap and the time check; the one definition of the Markdown line patterns (heading, fence, list marker, table separator, thematic break) and of the inline cleaning | `claims` | `test_extractors.py`, `test_scan_safety.py`, `test_scan_reporting.py`, `test_scan_robustness.py`, `test_parser_random.py` |
| `mapdoc.py` | Parser for architecture maps with evidence labels; legend rules. Its Markdown line patterns are imported from `scan` | `scan` | `test_map_ingest.py`, `test_parser_random.py` |
| `gaps.py` | Findings from token overlap between layers; the `actual_undocumented` cap | `claims`, `tokens` | `test_scan_gaps.py`, `test_claims.py`, `test_scan_reporting.py` |
| `db.py` | Data-directory resolution, connection set-up (WAL, busy timeout, foreign keys), forward-only migrations | `errors` | `test_db.py`, `test_status.py` |
| `service.py` | `Grove`: the sixteen operations, validation, row shapes, recommend order | `db`, `errors`, `gaps`, `mapdoc`, `scan` | all behaviour tests |
| `tools.py` | The tool table: name, description, input schema, handler, read-only flag; `run` and `call_tool` wrap results in the envelope | `errors`, `service` | `test_mcp_stdio.py`, `test_docs_contract.py` |
| `cli.py` | `grove` command: argument parsing, usage errors as envelopes, `--text` rendering | `errors`, `service`, `tools`, `mcp_server` (only for `mcp`) | `test_cli.py` |
| `mcp_server.py` | MCP stdio server over the tool table; server instructions; logs to stderr | `db`, `tools` | `test_mcp_stdio.py` |

**Layering rule *(tested)*.** The table's third column is enforced by
`test_invariants.py`. In words: the pure parts (`tokens`, `claims`, `scan`,
`mapdoc`, `gaps`) know nothing of storage; `service` is the only module that
combines them with the database; `tools` is the only description of the
operations; `cli` and `mcp_server` are thin adapters. Only `mcp_server`
imports the MCP SDK, and only `scan` imports `pathspec`.

**Import rules *(tested)*.** The only third-party modules `sf_grove` may
import are `mcp`, `mcp_types`, `anyio` and `pathspec`, each from one named
module. From the standard library, network modules, `subprocess`,
`importlib` and their like are forbidden, as are `eval` and `exec`; anything
else in the standard library is free. Adding a third-party module in
`test_invariants.py` is a decision to record in section 8.

## 3. Data model

One SQLite file, `grove.db`. `PRAGMA user_version` holds the number of
applied migrations. The table names below are compared with the real schema
by a test.

| Table | Holds | Key columns and rules |
|---|---|---|
| `projects` | One row per registered codebase | `name` unique; `root_path`; `last_scanned_at`; `last_scan` (JSON summary of the last scan: caps, warnings, skipped files, long lines, the exclude list it used); `findings_cap` (JSON: what the findings cap left out); `exclude` (JSON list of gitignore-style patterns kept out of the blueprint; NULL when none) |
| `blueprint_items` | The three layers | `layer` in `declared`/`actual`/`tests`; `title`, `body`; `source_path`, `source_line`; `origin` in `scan`/`map`; `origin_ref` (knowledge key of the map); `extra` (JSON: kind, class, language, ...) |
| `findings` | Gap findings | `kind`; `summary`; `evidence` (JSON); `confidence` (always `heuristic`); `origin`, `origin_ref`; `created_at` |
| `knowledge` | Every revision of every document | `project_id` (NULL = workspace); `key`; `title`; `body`; `revision`; `author`; unique on (scope, key, revision) |
| `knowledge_fts` | FTS5 index over `knowledge` (`title`, `body`), tokenizer `porter unicode61` | External-content table kept in step by insert and delete triggers |
| `work_items` | Local work items | `project_id`; `title`; `issue_url` (text, never fetched); `status` (checked against the five statuses); `plan`; `notes`; `author`; `created_at`, `updated_at` |
| `work_events` | The history of work items: one row per status change or note | `work_item_id`; `created_at`; `author` (NULL when none); `old_status`, `new_status` (equal when only a note was added); `note` (NULL when none); index on (`work_item_id`, `id`) |

**Row lifecycles.**

- `blueprint_items` and `findings` with `origin = 'scan'` are deleted and
  re-inserted by every scan, in one transaction. Their ids are therefore
  not stable and may even be reused.
- Rows with `origin = 'map'` are replaced only when the same map (same
  `origin_ref`) is ingested again. Scans keep them.
- `knowledge` rows are only ever inserted.
- `work_items` rows are inserted and updated in place.
- `work_events` rows are only ever inserted, by `work_update`, in the same
  transaction as the update they record and after reading the item's
  status inside it. No code path updates or deletes one.
- Nothing is ever deleted from `projects`, `knowledge`, `work_items` or
  `work_events`.

**Migrations** (`db.MIGRATIONS`, forward-only):

| Version | Adds |
|---|---|
| 1 | All tables, the FTS5 index and its triggers |
| 2 | `projects.findings_cap`, `work_items.author`, `knowledge.author` |
| 3 | `projects.exclude` |
| 4 | `work_events` and its index |

**Concurrency.** WAL mode; `busy_timeout` 5 s; every write runs in
`BEGIN IMMEDIATE`; migrations take the write lock before re-reading the
version; the switch to WAL is retried while another connection holds the
file. Readers never block writers.

## 4. Operation map

Sixteen operations. Each is one method of `service.Grove`, one row of
`tools.TOOLS` and one CLI command. *(Tool names tested against this table.)*

| MCP tool | CLI | `Grove` method | Reads | Writes |
|---|---|---|---|---|
| `grove_status` | `status` | `status` | `projects` | — |
| `grove_project_create` | `project create` | `project_create` | `projects` | `projects` |
| `grove_project_list` | `project list` | `project_list` | `projects` | — |
| `grove_project_get` | `project get` | `project_get` | `projects`, counts of the others | — |
| `grove_scan` | `scan` | `scan` | the project tree; `blueprint_items` | `blueprint_items`, `findings`, `projects` |
| `grove_blueprint_get` | `blueprint` | `blueprint_get` | `blueprint_items` | — |
| `grove_gaps` | `gaps` | `gaps` | `findings`, `projects` | — |
| `grove_ingest_map` | `ingest-map` | `ingest_map` | the map file | `knowledge`, `blueprint_items`, `findings`, `projects` |
| `grove_knowledge_write` | `knowledge write` | `knowledge_write` | the body file (CLI) | `knowledge` |
| `grove_knowledge_get` | `knowledge get` | `knowledge_get` | `knowledge` | — |
| `grove_knowledge_search` | `search` | `knowledge_search` | `knowledge`, `knowledge_fts` | — |
| `grove_work_create` | `work create` | `work_create` | `projects` | `work_items` |
| `grove_work_list` | `work list` | `work_list` | `work_items` | — |
| `grove_work_get` | `work get` | `work_get` | `work_items`, `work_events` | — |
| `grove_work_update` | `work update` | `work_update` | `work_items` | `work_items`, `work_events` |
| `grove_recommend_next` | `recommend` | `recommend_next` | `findings`, `work_items`, `projects` | — |

## 5. How the main flows work

**A call.** `cli.main` or `mcp_server.on_call_tool` → `tools.run` /
`tools.call_tool` (unknown and missing arguments rejected here) →
`Grove(home)` → one method → plain data → `errors.ok` or `errors.fail`. Any
exception becomes an envelope; `internal` means a bug.

**A scan.** `scan.scan_tree` walks the root (outside any transaction), skips
ignored paths, passes over files that match the project's exclude list
(counted, never read), classifies each remaining file as document, changelog,
test file, source module or other, and extracts items line by line. The time cap is
checked before each file and each line; lines over 5000 characters are
counted and skipped. Then, in one write transaction, `service.scan`
replaces the scan-derived items, stores the scan summary on the project
(and the exclude list, when the call gave one), and runs the gap pass.

**The gap pass.** `gaps.compute_findings` streams the stored items twice. It
builds three token sets (test names, code names, declared text), then for
each `behaviour` or `limit` sentence emits `declared_untested` when it
shares no token with any test name and `declared_unseen` when it shares none
with any code name. Modules whose file name the docs never mention become
`actual_undocumented`, shallowest first, at most 25 stored.

**Map ingest.** The file is stored whole as a knowledge revision. Its
labelled blocks seed `declared` items (`documented`), `actual` items
(`observed-in-code`) and `map_untested` findings (`untested`). The gap pass
runs again if the project has been scanned.

**Recommend.** A fixed sequence of queries, first hit wins; the order is
R-REC-1 in `REQUIREMENTS.md` and the constant `service.RECOMMEND_ACTIONS`.

## 6. Grove seen through its own three layers

Grove can scan its own repository. The picture is useful, shows what
excludes are for, and shows one known weakness.

| Layer | What it is in this repository |
|---|---|
| declared | `README.md` and the Markdown files under `docs/`. `REQUIREMENTS.md`, `CLAUDE.md`, `BUILD_NOTES.md` and `CHANGELOG.md` are **not** read: their names match no document pattern (changelogs are skipped by design). |
| actual | The modules in section 2, plus `fixtures/tiny`, which is a pretend project used by the tests. |
| tests | `tests/test_*.py`, plus the fixture's one test. |

Fixtures and non-normative documents (the survey, the analysis, the work
orders) enter the blueprint unless the project excludes them (R-SCAN-9):

```sh
grove scan grove --exclude 'fixtures/' --exclude 'docs/' --exclude '!docs/blueprint.md'
```

Measured on this repository (2026-11-13): without the list, 1613 declared
items and 254 findings; with it, 360 declared items and 31 findings, 9 files
excluded. The list is stored, so later scans need no flag.

The weakness that remains: the requirements document, the one file whose
sentences are all claims, is invisible to the declared layer. Reading it was
considered and deferred: its tables would add noise until measurement exists
(WO-22). Earlier figures are in `docs/analysis.md`.

## 7. Change traceability

A change to Grove follows one chain, and each link leaves something to check:

```text
requirement (R-…)  →  work order (WO-…)  →  change (branch, pull request)
        ↑                                          │
        └────── status updated ◄── tests ◄─────────┘──►  CHANGELOG.md entry
```

0. **Argument.** Before anything is written down, the change is debated
   (D-28). Most candidates end here, with a line saying why.
1. **Requirement.** A stable id in `REQUIREMENTS.md` with a status (tested,
   held, manual, open).
2. **Work order.** An entry in `docs/work-orders.md` naming the requirement
   ids it will make true, with acceptance criteria.
3. **Change.** One reviewable pull request per work order where possible.
   Its description names the work order and requirement ids.
4. **Tests.** The acceptance criteria as tests. When they pass, the
   requirement's status changes from open to tested, naming the test file.
5. **Changelog.** One line under "Unreleased" in `CHANGELOG.md`.
6. **Decision.** If the change settles a question, a row in section 8.

**Where each requirement area lives** (the full, per-id mapping is the
status column of `REQUIREMENTS.md`):

| Area | Code | Tests |
|---|---|---|
| R-INV (invariants) | whole package | `test_invariants.py`, `test_scan_safety.py`, `test_mcp_stdio.py`, `test_db.py` |
| R-COMPAT, R-IF (interface) | `tools.py`, `cli.py`, `errors.py` | `test_cli.py`, `test_mcp_stdio.py`, `test_docs_contract.py` |
| R-HOME (data directory) | `db.py`, `service.status` | `test_status.py`, `test_cli.py`, `test_db.py`, `conftest.py` |
| R-PROJ, R-SCAN | `scan.py`, `claims.py`, `service.scan` | `test_extractors.py`, `test_claims.py`, `test_scan_safety.py`, `test_scan_reporting.py`, `test_scan_robustness.py` |
| R-GAP, R-REC | `gaps.py`, `tokens.py`, `service.recommend_next` | `test_scan_gaps.py`, `test_claims.py`, `test_work.py` |
| R-KNOW, R-MAP | `service.knowledge_*`, `mapdoc.py` | `test_knowledge.py`, `test_map_ingest.py` |
| R-WORK | `service.work_*` | `test_work.py` |
| R-GROK, R-CC (clients) | `tools.py` descriptions, `mcp_server.py`, `CLAUDE.md`, README | `test_docs_contract.py`, `test_mcp_stdio.py` |
| R-SEC | `scan.py`, `service.py`, `scripts/check-publish` | `test_invariants.py`, `test_scan_safety.py`, `test_gates.py` |
| R-SCAN-7 (no exception, the same output twice and linear time on any text; one definition of each pattern) | the patterns in `scan.py` and `claims.py`; `mapdoc.py` and the outline in `service.py` import theirs from `scan.py` | `test_parser_random.py`, `test_scan_robustness.py`, `test_invariants.py` (a pattern is written in one module only), `test_extractors.py` (the README's list of Markdown constructs) |
| R-QUAL-8 (the linter, the one check script) | `pyproject.toml` (the `dev` group, `[tool.ruff.lint]`), `scripts/check` | `test_gates.py` |
| R-QUAL-9 (the CI gate) | `.github/workflows/ci.yml` | `test_gates.py` |

## 8. Decision log

One row per decision. A decision is changed by adding a row that supersedes
it, not by editing it. Rows D-06 to D-12 were first recorded in
`BUILD_NOTES.md` ("Decisions that the spec left open").

| Id | Date | Decision | Why | Status |
|---|---|---|---|---|
| D-01 | 2026-11-12 | Local only: no network, MCP over stdio only | The data and the code stay on one machine; nothing to secure or operate | accepted (owner) |
| D-02 | 2026-11-12 | No model inside the product | Deterministic, explainable, free to run; the model is the client | accepted (owner) |
| D-03 | 2026-11-12 | Sixteen tool names frozen; optional parameters and new result fields allowed | Clients keep working across versions | accepted (owner) |
| D-04 | 2026-11-12 | One SQLite file, WAL, FTS5, forward-only migrations by `user_version` | Standard library only; safe for several processes | accepted |
| D-05 | 2026-11-12 | One service class; one tool table drives MCP; the CLI calls the same methods | The two surfaces cannot drift | accepted |
| D-06 | 2026-11-12 | Knowledge keys are unique per scope; without a project the workspace document wins | `map` can exist in every project | accepted |
| D-07 | 2026-11-12 | Search covers the latest revision only; words quoted and ANDed; `porter unicode61` | Predictable; caller text cannot break the query | accepted |
| D-08 | 2026-11-12 | Gap findings only for scanned projects; map items take part in the gap pass | Otherwise every map line reads as untested | accepted |
| D-09 | 2026-11-12 | Recommend order as in R-REC-1; `declared_unseen` never recommended | Explicit statements before overlap guesses | accepted |
| D-10 | 2026-11-12 | `limit` above 200 is clamped, not rejected | Forgiving to agents; the result shows the clamp | accepted |
| D-11 | 2026-11-12 | Tool results are one text block holding the envelope; unknown tool is a `not_found` envelope | Same shape on both surfaces | accepted; see D-29 |
| D-12 | 2026-11-12 | Project names may not be all digits | A name is never mistaken for an id | accepted |
| D-13 | 2026-11-12 | Changelogs add no declared items; 1000 declared items per document, claims kept first | History is not a promise (team trial) | accepted |
| D-14 | 2026-11-12 | `knowledge get` returns a 4000-character excerpt with an outline unless `full` | Bounded results (team trial) | accepted |
| D-15 | 2026-11-12 | Authors are recorded and never guessed | A wrong name is worse than none (team trial) | accepted |
| D-16 | 2026-11-13 | `REQUIREMENTS.md` is the single requirements source; `BUILD_NOTES.md` is a historical record | One place to implement against | accepted (this change) |
| D-17 | 2026-11-13 | The scanner stays a set of per-line patterns; no syntax-tree or language-server dependency in v0 | Small, dependency-free, explainable. Revisit when WO-23 can measure what precision a parser would buy | accepted (survey) |
| D-18 | 2026-11-13 | Scan time is bounded by a 5000-character line cap and a time check between lines, not by a linear-time regex engine | No compiled dependency; the cap is reported | accepted (this change) |
| D-19 | 2026-11-13 | The switch to WAL is retried on a lock, instead of a lock file or a single-writer rule | Smallest fix for the concurrent first open | accepted (this change) |
| D-20 | 2026-11-13 | Knowledge is listed through `grove_knowledge_search` with no query, not through a new tool | D-03 | accepted (this change) |
| D-21 | 2026-11-13 | Invariants are enforced by standard-library tests (AST import checks), not by a lint dependency | R-INV-14 | accepted (this change) |
| D-22 | 2026-11-13 | The default data directory stays `~/.grove`; the XDG layout is not adopted | The default is part of the interface | accepted (survey) |
| D-23 | 2026-11-13 | One shared data directory per machine for all agents | Shared knowledge and work items; `author` tells agents apart | assumed default (A4) |
| D-24 | 2026-11-13 | All work-item transitions stay allowed | Grove records, it does not police; the history records what happened (WO-14) | assumed default (A5) |
| D-25 | 2026-11-13 | Nothing is deleted in v0 | Append-only is simple and safe; archive later (WO-30) | assumed default (A3) |
| D-26 | 2026-11-13 | `recommend` order unchanged; unfinished work is not a tier | The order is tested and documented; a hint is proposed (WO-29) | assumed default (A2) |
| D-27 | 2026-11-13 | Decisions are rows in this table, not one file each | Keeps the document set small; split if the table passes about forty rows | accepted (this change) |
| D-28 | 2026-11-13 | Every proposed change is argued before it is carried forward: parsimony, efficiency, unintended consequences. What was left out is recorded with its reason | A resource existing, or a feature being possible, is not a reason; additions are permanent under D-03 | accepted (owner's instruction, relayed during this change) |
| D-29 | 2026-11-13 | No `structuredContent` or `outputSchema` for now | Output schemas would enlarge the tool list and structured results would double result payloads, with no shown client need. Revisit after Grok Bot is verified (WO-11) | accepted (this change; see WO-25) |
| D-30 | 2026-11-13 | Work-item progress is an append-only history, not an appendable `notes` field or optimistic locking | One mechanism removes lost updates and records who did what | accepted (built in WO-14) |
| D-31 | 2026-11-13 | Scan excludes will be one stored list per project, set through `grove_scan` | No file inside the project, no silent default skips, one way to set it | accepted (built in WO-10) |
| D-32 | 2026-11-13 | A data directory inside a project root is an `invalid` error at `project_create` and `scan`, not a warning and not a silent skip; every other operation on a project registered that way still works | An invariant that only warns is not one; the data must stay reachable so it can be moved out | accepted (WO-09) |
| D-33 | 2026-11-13 | Exclude patterns are matched against each file's path; excluded directories are walked, not pruned, and one total is reported | The count of removed files is exact, so a pattern that matches nothing shows as 0; the walk reads nothing and stays under the time cap. Known difference from git: a later `!pattern` re-includes a file under an excluded directory | accepted (WO-10) |
| D-34 | 2026-11-12 | Continuous integration is allowed on the public repository: one job, read-only token, no secrets, pinned actions. It is a visible check, not a required one; no branch protection | A gate that is not the author's machine (R-QUAL-9). Visible first, so that a job which fails without a defect is noticed before it can block a merge | accepted (owner; answers A8; built in WO-08) |
| D-35 | 2026-11-13 | The CI workflow's rules are enforced by a text test with the standard library, not by a workflow linter; the workflow expands no expression at all | D-21 applied to the workflow: a rule that is only prose is broken by the next edit. "No expression" is stricter than the rule needs and is one substring to check | accepted (WO-08) |
| D-36 | 2026-11-13 | `scripts/check-publish` refuses agent session ids and reads the commit message as well as the files. Machine paths stay in the uncommitted local pattern file | R-INV-15 named session ids and nothing checked them; a commit message is published like a file. A private path written into a public script would be published by the script | accepted (WO-08; part of WO-26 done early) |
| D-37 | 2026-11-13 | A history event is written only by a status change or a `note`; creating an item and replacing `plan`, `notes` or `title` write none. Only `work_get` returns the history: the newest 20 events and the true total, with no paging. A note is at most 1000 characters | The order's acceptance, kept literal. Creation is already on the item (`created_at`, `author`). The history rides on one read, not on every list row or write result, and its worst case is bounded (R-GROK-4). Paging would need two more described parameters with 18 bytes of description budget left | accepted (WO-14) |
| D-38 | 2026-11-13 | `work_events` is append-only by construction (one `INSERT`, no other statement), not by database triggers | The same rule as `knowledge`, which has none. A trigger would guard against editing `grove.db` by hand, which the brief already forbids, and would be one more object in every migration test | accepted (WO-14) |
| D-39 | 2026-11-13 | The linter is ruff with the pyflakes rules only, pinned in the `dev` group: no style rule, no formatter, no type checker. `scripts/check` runs the linter, shellcheck if it is installed, the tests and the publish check; it runs every step and reports a skipped one. CI runs the linter as one more step; shellcheck is neither a dependency nor a CI step | Mechanical mistakes are caught by a tool without touching the code's layout or `git blame`. A skipped check that is not reported reads as a passed one. The runner's shellcheck is not pinned, and a pinned copy would be a new dependency for three files. D-21 stands: the invariants stay in standard-library tests | accepted (WO-12) |
| D-40 | 2026-11-13 | A pattern that two modules need is written in one module and imported by the other; a test fails when one is written twice. The inline patterns (link, image, tag) never read past the next opener of their own kind, and an ATX heading's closing `#`s are removed in code, so cleaning takes linear time. The randomised test is seeded and uses only the standard library; besides its random documents, every piece of its alphabet gets one long paragraph | The same fix had to be made in two copies once (WO-06) and a third copy had no line cap. A paragraph of a map and a line of a knowledge document have no length cap, so there the cap cannot stand in for a linear pattern. Chance alone left most pieces without a long paragraph, and the first version of the test passed on the defective code. Left out: a sweep of every line start with every piece at the line cap (thirty-six megabytes of input on every run; the cases it found are fixed tests) | accepted (WO-24) |

## 9. How to extend Grove safely

Each recipe ends with the definition of done in `REQUIREMENTS.md`,
section 11.

- **A new optional parameter.** Add it to the `Grove` method with a default
  that keeps today's behaviour; add it to the tool's schema and description
  in `tools.py`; add the CLI flag; test the service method, `call_tool` and
  the CLI. Check the `tools/list` size budget (R-GROK-3).
- **A new result field.** First ask whether an existing field already says
  it: a field can never be removed once shipped. Then add it; never rename
  or retype an existing one.
  If it reports a cap, add the cap to section 8 of `REQUIREMENTS.md`.
- **A schema change.** Append a string to `db.MIGRATIONS`; never edit an
  earlier one. Add a test that builds a database at the previous version,
  opens it with the new code and reads old rows. Update section 3 here.
- **A new language or document pattern.** Add the patterns and file
  patterns to `scan.py` with extractor tests. Every pattern must be safe on
  a 5000-character line (see `test_scan_robustness.py`), and a pattern that
  is applied to a whole paragraph must be linear: nothing caps a paragraph.
  A quantifier that can read on to the end of the text from every opener is
  the usual mistake. If the pattern cares about a new character or word, add
  it to the alphabet in `test_parser_random.py`. Write a pattern once: a
  second module imports it (`test_invariants.py`). Expect the set of
  findings to change (R-COMPAT-7) and say so in the changelog.
- **A new finding kind or recommend action.** Extend `FINDING_KINDS` or
  `RECOMMEND_ACTIONS`, the tool descriptions, R-GAP-1 or R-REC-1, and the
  changelog (R-COMPAT-5).
- **A change to the CI workflow.** Keep the five rules of WO-08;
  `test_gates.py` fails when one is broken. A new action is pinned to a full
  commit SHA taken from the action's own repository, and a new action owner
  is a decision for section 8.
- **A new bash file, or a change to the linter.** Add the file to
  `SHELL_FILES` in `scripts/check`; `test_gates.py` fails until it is
  there. The linter's rule set and pin are held by the same test file: a
  new rule, an ignore list or a formatter setting is a decision for
  section 8 (D-39), not an edit. Silence one finding with a `# noqa` and
  its reason on the line.
- **A new import.** Standard-library modules need nothing. If
  `test_invariants.py` rejects an import, stop: that is a decision for
  section 8, and for a runtime dependency, for the owner.
