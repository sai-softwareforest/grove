# Grove requirements

This is the single requirements document for Grove (`sf_grove`, CLI `grove`,
version 0.1.x). A coding agent must be able to implement a change against this
file without guessing. It replaces the external "spec" that `BUILD_NOTES.md`
refers to: where the two differ, this file wins, and `BUILD_NOTES.md` is a
historical build record.

Related documents: `docs/blueprint.md` (architecture, data model, operation
map, decision log), `docs/work-orders.md` (prioritised upgrades),
`docs/analysis.md` (why), `docs/industry-survey.md` (sources), `CHANGELOG.md`
(what changed).

## 0. How to read this file

- **MUST**, **MUST NOT**, **SHOULD**, **MAY** are used as in RFC 2119.
- Every requirement has a stable id (`R-AREA-n`). Ids are never renumbered or
  reused. A retired requirement keeps its id and is marked *retired*.
- Every requirement carries a status:
  - **tested** — a test in `tests/` fails if the requirement is broken (the
    test file is named);
  - **held** — true in the code today, but no test guards it;
  - **manual** — checked by hand once, recorded in `BUILD_NOTES.md`;
  - **open** — not yet true; the work order that will make it true is named.
- Work orders (`WO-nn`) are defined in `docs/work-orders.md`.
- Section 12 lists the assumptions made where only the owner can decide. Each
  has a reversible default.

## 1. Purpose and scope

Grove is a local, deterministic workshop for coding agents. It maps a
codebase, records a three-layer blueprint (declared / actual / tests), stores
searchable knowledge, and tracks local work items. Agents (Grok Bot over MCP,
Claude Code over the CLI or MCP) do the work; Grove is where they look things
up and keep track.

| Id | Requirement | Status |
|---|---|---|
| R-SCOPE-1 | Grove offers exactly four capabilities: project scan into a three-layer blueprint with heuristic gap findings; revisioned, searchable knowledge (including ingested architecture maps); local work items; one deterministic next-step recommendation. | tested: `test_scan_gaps.py`, `test_knowledge.py`, `test_work.py`, `test_map_ingest.py` |
| R-SCOPE-2 | Grove is not an autonomous coder. It MUST NOT edit, generate, format or execute code of a scanned project, and MUST NOT run that project's tests or tools. | held (import test in `test_invariants.py` forbids `subprocess`) |
| R-SCOPE-3 | Grove is not a judge. Every finding and recommendation MUST be labelled `confidence: "heuristic"`. Grove records what agents report (status, notes); it does not verify it. | tested: `test_scan_gaps.py` |
| R-SCOPE-4 | v0 offers no delete, rename or archive operation for projects, knowledge or work items. An export deletes no file either (R-VIEW-3). | held; see A3 |
| R-SCOPE-5 | MCP resources and prompts are not implemented in v0. | held |
| R-SCOPE-6 | **Agent first.** Every agent reads all tool descriptions and schemas at the start of every conversation, so each byte there is a constant token and attention cost. Hence the tools/list budget (R-GROK-3, 15 000 bytes, enforced by the budget test). New features prefer zero new parameters or CLI-only surfaces. Humans get read-only views (`grove export`, `grove view`) that cost agents nothing. | held: R-GROK-3 budget test; WO-39 adds no MCP surface |

## 2. Invariants

These are decided. A change that breaks one is not a change to Grove; it is a
different product.

| Id | Invariant | Status |
|---|---|---|
| R-INV-1 | **Local only.** Product code MUST NOT open a network connection, start a listener, or send telemetry ("phone home"). No HTTP transport for MCP. One exception, decided by the owner with WO-39 (D-55): `grove view` listens on 127.0.0.1, and only there, to show a person the read-only pages of R-VIEW-2, within the limits of R-VIEW-5. It makes no outgoing connection, and no other command listens. | tested: `test_invariants.py` (network modules are forbidden imports; `view.py` alone may import `http.server`, and nothing else from that list), `test_view.py` (the loopback address only) |
| R-INV-2 | **No model.** No LLM, embedding or other model call, local or remote. | tested: `test_invariants.py` (third-party imports are limited to `mcp`, `mcp_types`, `anyio`, `pathspec`) |
| R-INV-3 | **Deterministic.** The same tree content, arguments, stored exclude list (R-SCAN-9) and Grove version produce the same blueprint items, findings and recommendation, in the same order. Only timestamps, row ids and `elapsed_seconds` may differ. | tested: `test_invariants.py`, `test_scan_exclude.py` |
| R-INV-4 | **Scans are read-only.** Grove MUST NOT create, modify or delete anything inside a scanned project. It writes only inside its data directory, and, for `grove export --out DIR`, inside the directory the caller names. That directory is refused when it is the root of any registered project or lies inside one (R-VIEW-3): the invariant has no exception. | tested: `test_scan_safety.py`, `test_cli.py`, `test_export.py` (a project's tree is unchanged by scans and by an export; every refusal) |
| R-INV-5 | **No GitHub mutation.** Grove itself never talks to GitHub or any other service. `issue_url` is stored as text and never fetched. | held (follows from R-INV-1) |
| R-INV-6 | **Storage.** One SQLite file `grove.db` in the data directory, WAL mode, FTS5 for knowledge search, foreign keys on. | tested: `test_db.py` |
| R-INV-7 | **Forward-only migrations.** A shipped entry of `db.MIGRATIONS` is never edited; schema changes are appended. A database with a newer schema is refused with an `io` error, never downgraded. | tested: `test_db.py` |
| R-INV-8 | **MCP over stdio only.** stdout carries MCP JSON-RPC and nothing else; logs go to stderr. | tested: `test_mcp_stdio.py` |
| R-INV-9 | **Sixteen tools.** The MCP tool names in section 6.3 are frozen: none renamed, none removed, none added in v0. Order is fixed. | tested: `test_mcp_stdio.py`; the sixteen input schemas are compared with a stored copy: `test_tool_schemas.py` |
| R-INV-10 | **One envelope.** Every operation result is `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message"}}`. | tested: `test_cli.py`, `test_mcp_stdio.py` |
| R-INV-11 | **Caps are never silent.** Any cap, clip, excerpt or omission MUST be reported in the result that it affects (section 8). | tested for the caps marked so in section 8; the symbols cap: `test_symbols_cap.py` |
| R-INV-12 | **Knowledge is append-only.** Writing an existing key adds a revision. No revision is ever overwritten or deleted. | tested: `test_knowledge.py`, `test_db.py` |
| R-INV-13 | **Authors are never guessed.** `author` is the explicit argument, else `$GROVE_AUTHOR`, else `null`. | tested: `test_work.py`, `test_knowledge.py` |
| R-INV-14 | **Few, pinned dependencies.** Runtime dependencies are `mcp` and `pathspec`, pinned exactly; `uv.lock` pins the tree. A new runtime dependency needs the owner's explicit approval. | held |
| R-INV-15 | **Clean public tree.** No secrets, credentials, data directories, agent session ids or machine-specific paths are committed, in a file or in a commit message. Every push passes `scripts/check-publish`; hooks are never skipped. Pull-request descriptions are outside what the script can see and are checked by their author. | held (pre-push hook on every new commit of a push, CI on the head commit); tested: `test_gates.py` (WO-26) |

## 3. Compatibility policy

The public interface is: MCP tool names, tool parameter names and types,
result field names and types, the envelope, the error codes, CLI command and
flag names, exit codes, the data-directory resolution order, and the database
schema as upgraded by migrations.

| Id | Requirement | Status |
|---|---|---|
| R-COMPAT-1 | Nothing in the public interface is renamed or removed in v0, and no existing field or parameter changes type or meaning. | held; a change to an input schema fails `test_tool_schemas.py` until the stored copy is changed with it, so it cannot happen unnoticed |
| R-COMPAT-2 | **Additive changes are allowed:** new optional parameters, new result fields, new CLI flags. A new optional parameter MUST default to the previous behaviour. Additive is not free: by R-COMPAT-1 nothing added can later be removed, so each addition needs a reason (section 11.1, item 1). | held |
| R-COMPAT-3 | Clients MUST ignore result fields they do not know. Grove MUST reject parameters it does not know (`invalid`). | tested: `test_mcp_stdio.py` |
| R-COMPAT-4 | The error codes are exactly `not_found`, `invalid`, `io`, `internal`. No code is added in v0. | tested: `test_invariants.py` |
| R-COMPAT-5 | Closed value sets returned in results (`layer`, work `status`, finding `kind`, recommend `action`, declared `class`, `home_source`) may gain a value only with a `CHANGELOG.md` entry and an updated tool description. | held |
| R-COMPAT-6 | Validation may be tightened only for input that could never have produced a meaningful result (for example an unknown finding kind). Each tightening is a `CHANGELOG.md` entry. | held |
| R-COMPAT-7 | **Not part of the interface:** which findings a scan produces, their order beyond the documented priority, the classification of a sentence, blueprint item ids and finding ids. These are heuristics and may improve between versions. Clients MUST NOT store blueprint or finding ids; they change on every scan. | held; said to clients in the `grove_status` description and in the server instructions, tested: `test_docs_contract.py` |
| R-COMPAT-8 | Versions follow Semantic Versioning. While the version is `0.x`: a PATCH release only fixes; a MINOR release may add (R-COMPAT-2) or change heuristics (R-COMPAT-7). Every release has a `CHANGELOG.md` section. | held (the changelog starts with this change; no release has been made since) |
| R-COMPAT-9 | Defaults that shape results (page size 50, page ceiling 200, excerpt 4000 characters, the caps in section 8) change only with a `CHANGELOG.md` entry. | held |

## 4. The data directory

| Id | Requirement | Status |
|---|---|---|
| R-HOME-1 | The data directory is resolved in this order: `--home DIR` (CLI flag), else `$GROVE_HOME`, else `~/.grove`. It is created on first use. | tested: `test_cli.py` |
| R-HOME-2 | `grove status` / `grove_status` MUST report `data_dir`, `db_path`, `project_count` and `home_source` (`flag`, `env` or `default`). When `project_count` is 0 the result carries a `hint` that this may be the wrong directory; otherwise `hint` is `null`. | tested: `test_status.py` |
| R-HOME-3 | **One home per machine.** All agents on a machine (Grok Bot, Claude Code, a person at a shell) SHOULD use the same data directory, so that knowledge and work items are shared. See A4. | held (documentation: README, `CLAUDE.md`) |
| R-HOME-4 | The data directory MUST be outside every scanned project root. `project create` and `scan` return `invalid` when the data directory is the project's root or inside it (both paths compared after resolving symlinks); the message names both paths and the remedy. A refused `project create` opens no database, so it creates nothing. A project registered that way by an earlier version keeps its data and stays readable; only scanning it is refused. | tested: `test_scan_safety.py` |
| R-HOME-5 | Tests and experiments MUST use a temporary data directory, never the real one. The test suite enforces this with an autouse fixture. | tested: `tests/conftest.py` |
| R-HOME-6 | Documentation MUST NOT rely on `export GROVE_HOME=...` persisting between agent shell calls. It MUST tell agents to pass `--home` on each call, or to have the variable set where the agent's processes are started (MCP server `env`, shell profile, agent settings), and to confirm with `grove status`. | held (README, `CLAUDE.md`) |
| R-HOME-7 | Machine-specific locations (the real home on a given machine) belong in the uncommitted `LOCAL.md`, never in tracked files. | held; checked by `scripts/check-publish.local` when present |
| R-HOME-8 | Several processes may use one data directory at once. Writes use `BEGIN IMMEDIATE` with a 5 second busy timeout; opening a fresh or existing database concurrently MUST NOT fail. | tested: `test_db.py` |

## 5. The envelope and common conventions

| Id | Requirement | Status |
|---|---|---|
| R-IF-1 | Every CLI command prints exactly one JSON envelope on stdout and exits 0 when `ok` is true, 1 otherwise. Exceptions, which are not envelopes: `grove --help` and `grove COMMAND --help` (usage text, exit 0), `grove --version` (one line, exit 0), `grove mcp` (speaks MCP until stdin closes), and `--text` (plain rendering for people; exit code unchanged). `grove view` prints its one envelope when it starts (the URL, or the error) and then serves until it is interrupted; it exits 0 after an interrupt. | tested: `test_cli.py` (envelope, exit codes, `--text`), `test_view.py` (`view`); held (help, version) |
| R-IF-2 | Usage mistakes (unknown command, missing argument, bad choice) are `invalid` envelopes with exit code 1, not argparse's exit code 2. | tested: `test_cli.py` |
| R-IF-3 | Every MCP tool result is the envelope as one text content block; `isError` equals `not ok`. An unknown tool name is a `not_found` envelope, not a protocol error. | tested: `test_mcp_stdio.py` |
| R-IF-4 | Error codes mean: `not_found` — the named thing does not exist; `invalid` — the request is wrong and the caller can fix it; `io` — the file system or database refused; `internal` — a bug in Grove. A traceback MUST never replace the envelope. | held (`tools.run`) |
| R-IF-5 | Error messages SHOULD say what to do next ("see the project list", "pass a project to choose one"). | held |
| R-IF-6 | **Paging.** Every list result has `items`, `total`, `offset`, `limit`. `limit` defaults to 50 and is clamped (not rejected) at 200. `limit < 1` and `offset < 0` are `invalid`. | tested: `test_cli.py`, `test_scan_gaps.py` |
| R-IF-7 | Timestamps are UTC, `YYYY-MM-DDTHH:MM:SSZ`. Order within a second is given by row id. | held |
| R-IF-8 | Path arguments are `~`-expanded and resolved to absolute paths against the working directory of the Grove process; results echo the resolved path. MCP clients SHOULD pass absolute paths, because the server's working directory is chosen by whoever started it. | held |
| R-IF-9 | The CLI never prompts, pages or colours its output. It is safe to run without a terminal. | held |
| R-IF-10 | Both surfaces offer every operation. A new parameter is added to the service method, the MCP schema and description, and the CLI flag in the same change, each with a test. | held; the map in section 6.3 is tested: `test_docs_contract.py`. `author` on `grove_ingest_map` closed the one recorded exception (WO-21): `test_map_ingest.py`, `test_mcp_stdio.py`. `grove export` and `grove view` are not operations in this sense: they are command-line only by decision (R-VIEW-6) |

## 6. Domain model

### 6.1 Projects and scans

| Id | Requirement | Status |
|---|---|---|
| R-PROJ-1 | A project is a unique name (1–100 characters of letters, digits, `.`, `_`, `-`; starts with a letter or digit; not only digits) plus an existing root directory. Projects are addressed by name or numeric id. | tested: `test_cli.py`, `test_scan_safety.py` |
| R-SCAN-1 | A scan replaces the project's scan-derived blueprint items and findings in one transaction. It keeps knowledge, work items and map-seeded items and findings. | tested: `test_scan_gaps.py`, `test_map_ingest.py` |
| R-SCAN-2 | The walk honours `.gitignore` files (each relative to its own directory; a deeper file cannot re-include), always skips `.git`, `node_modules`, `target`, `venv`, `.venv`, `dist`, `build`, `__pycache__`, `.mypy_cache`, `.pytest_cache`, and does not follow symlinks. It never enters a directory that holds a `.grove-export` entry, the marker `grove export` leaves in every directory it writes to (R-VIEW-3): this is decided during the walk, before any file in that directory is read, so exported pages never come back as declared items. | tested: `test_scan_safety.py`, `test_export.py` (the marker) |
| R-SCAN-3 | Layers: `declared` — headings and sentences from README*, CONTRIBUTING*, ARCHITECTURE*, DESIGN* and Markdown/reStructuredText under `docs/` or `doc/`; `actual` — one item per source module plus symbol names (Python, Rust, TypeScript/JavaScript, Go); `tests` — test files and test names. Other files are counted only. | tested: `test_extractors.py` |
| R-SCAN-4 | Changelogs and release notes are walked and listed under `changelog_files` but add no declared items. | tested: `test_scan_reporting.py` |
| R-SCAN-5 | Each declared sentence gets one class (`behaviour`, `limit`, `setup`, `prose`) by the fixed rules in `claims.py`, first match wins. The class and its reason are stored on the item. | tested: `test_claims.py` |
| R-SCAN-6 | The scan result is a summary (counts, caps, warnings, skipped files, up to 5 sample findings), never the full blueprint. | tested: `test_scan_reporting.py` |
| R-SCAN-7 | Scan analysis time MUST be bounded by input size. Lines longer than 5000 characters are not analysed; they are counted and reported (section 8). Below that length every pattern applied to scanned text MUST stay cheap on worst-case input (tested at the cap). Text that has no length cap (a paragraph of a map, a line of a knowledge document) MUST be read in time linear in its length. On any text the extractors (documents, maps, symbols and test names of the four languages, the claim classes, the tokeniser, the knowledge outline) MUST NOT raise and MUST give the same output twice. A leading byte order mark is ignored. | tested: `test_scan_robustness.py` (fixed worst cases), `test_parser_random.py` (seeded random input: no exception, same output twice, time within a linear bound) |
| R-SCAN-8 | The file cap is checked before each file; the time cap before each file and each line, so a scan overruns it by at most the analysis of one line. A partial scan keeps what it has and says so in the result and on the project (`caps_hit`, `cap_warnings`). Storing and the gap pass run after the walk and are not timed. | tested: `test_scan_safety.py`, `test_scan_robustness.py` |
| R-SCAN-9 | A project can exclude paths (fixtures, examples, vendored code, non-normative docs) from the blueprint without writing inside the project. The exclude list is a list of gitignore-style patterns relative to the project root, stored on the project. `scan` takes optional `exclude`: a list with at least one pattern replaces the stored list, in the same transaction as the blueprint it produced; when it is omitted or empty (no entries, or only blank ones) the stored list applies and is not changed; exactly one list, `["!"]` (CLI `--exclude '!'`), clears it. A lone `!` is not a gitignore pattern, and beside other patterns it is `invalid`. Each pattern is matched against the path of every file the walk reaches (so, unlike git, a later `!pattern` can bring back a file under an excluded directory). A matching file is never read, is not part of `files_seen` and does not use up the file cap; the time cap still applies. Every scan result reports `excluded` (`patterns`: the list in effect; `files`: how many files it removed; after `["!"]` the list is empty, after an empty `exclude` it is the stored list), and the project keeps it in `last_scan`. | tested: `test_scan_exclude.py`, `test_db.py` |
| R-SCAN-10 | Every scan result says what the scan changed in the scan-derived findings, as `delta`, compared by finding key (R-REC-2) with the findings the scan replaced. The keys are read inside the scan's transaction, before the findings are replaced. Map findings are not part of it. On a project's first scan `delta` is `{"first_scan": true}` and nothing else. On every later scan: `first_scan` false; `added` and `resolved`, the true counts; `added_keys`, the keys of findings that are new; `resolved_items`, the findings that are gone, each as `key`, `kind`, `summary` (a resolved finding can no longer be paged with `gaps`); `list_cap`; `complete`; `note`. `complete` is false, and `note` says why, when a findings cap left findings out of either of the two scans (a key can then come or go without a change in the project) or when a list was cut (section 8). Nothing is stored for it: a delta is reported once, by the scan that found it. | tested: `test_scan_delta.py` (WO-37, D-51) |

### 6.2 Findings and the recommendation

| Id | Requirement | Status |
|---|---|---|
| R-GAP-1 | Finding kinds are `declared_untested`, `declared_unseen`, `actual_undocumented` (from scans) and `map_untested` (from ingested maps). | tested: `test_scan_gaps.py`, `test_map_ingest.py` |
| R-GAP-2 | Only `behaviour` and `limit` sentences produce findings; `setup` and `prose` are counted in `gap_notes.declared_skipped`. | tested: `test_claims.py` |
| R-GAP-3 | Overlap is token overlap as defined in `tokens.py`: one shared token silences a finding. The heuristic errs towards silence. | tested: `test_extractors.py`, `test_scan_gaps.py` |
| R-GAP-4 | Gap findings are computed only for a scanned project. A map ingested before any scan stores its items and `map_untested` findings and says the overlap pass was skipped. | tested: `test_map_ingest.py` |
| R-GAP-5 | `gaps` filtered by an unknown `kind` returns an `invalid` error that lists the kinds. A missing or blank `kind` is no filter. | tested: `test_gaps_kind.py`, `test_mcp_stdio.py`. The service checks it, so both surfaces refuse alike; the MCP schema of `kind` carries no `enum` yet (WO-18: the tool list has no room for it, R-GROK-3) |
| R-GAP-6 | `gaps` takes an optional `query`: text looked for anywhere in a finding's summary, in the `source_path` of its evidence or in its key, ignoring the case of ASCII letters, with `%` and `_` read as themselves. It combines with `kind`. `total` and the page follow both filters; `counts` follows `query` and stays per kind, whatever `kind` is; `complete`, `omitted` and `true_total` follow `kind` as before, because candidates a cap left out were never stored and cannot be searched (under a `query`, `true_total` is an upper bound). A missing or blank `query` is no filter; one that is not a string or is longer than 200 characters is `invalid`. | tested: `test_gaps_query.py`, on the service, the CLI and the MCP tool (WO-38, D-52) |
| R-REC-1 | `recommend` returns one step by this fixed order: (1) a `map_untested` finding → `cover_untested_behaviour`; (2) a `behaviour` `declared_untested` finding whose words appear in code names → `cover_untested_behaviour`; (3) another `behaviour` `declared_untested` finding → `check_declared_claim`; (4) the oldest `ready` work item → `start_work_item`; (5) a `limit` `declared_untested` finding → `check_documented_limit`; (6) an `actual_undocumented` finding → `document_module`; (7) `scan` if the project was never scanned; (8) `none`. `declared_unseen` is never recommended. | tested: `test_scan_gaps.py`, `test_claims.py`, `test_work.py`; description tested: `test_docs_contract.py` |
| R-REC-2 | Findings can be referenced durably (a key that survives rescans), linked from work items, and skipped by `recommend` once they have open work. A work item links a finding by writing `finding:KEY` in its `title`, `plan` or `notes` (R-WORK-6). `recommend` passes over every finding whose key is in the `refs` of a work item of the same project that is not `done`, in each step of R-REC-1, and takes the next finding or the next step instead; when the item is `done`, or the reference leaves its text, the finding is recommended again. The result says how many stored findings were passed over, as `skipped_findings`, and its `rationale` says so when the number is not 0. The finding itself is unchanged: `gaps` and `scan` still list it. | tested: `test_finding_keys.py` (the key: every finding in `scan`, `gaps` and `recommend` results has `key`, which an unchanged rescan and a moved line keep and an edited statement changes; WO-28, D-50), `test_work_refs.py` (the link, the skip and the return; WO-15, D-53) |

### 6.3 Operations: MCP tool ↔ CLI command

This table is the contract for R-INV-9 and R-IF-10. "Writes" means writes to
Grove's own database; nothing writes to a project.

| MCP tool | CLI command | Writes |
|---|---|---|
| `grove_status` | `grove status` | no |
| `grove_project_create` | `grove project create NAME --root PATH` | yes |
| `grove_project_list` | `grove project list` | no |
| `grove_project_get` | `grove project get NAME` | no |
| `grove_scan` | `grove scan NAME [--max-files N] [--max-seconds S] [--exclude PATTERN]...` | yes |
| `grove_blueprint_get` | `grove blueprint NAME [--layer L] [--query TEXT] [--summary] [--source-path PATH]` | no |
| `grove_gaps` | `grove gaps NAME [--kind KIND] [--query TEXT]` | no |
| `grove_ingest_map` | `grove ingest-map NAME PATH [--author NAME]` | yes |
| `grove_knowledge_write` | `grove knowledge write NAME --key KEY --title TITLE --file PATH [--author NAME]` | yes |
| `grove_knowledge_get` | `grove knowledge get KEY [--project NAME] [--revision N] [--full] [--from-line N]` | no |
| `grove_knowledge_search` | `grove search [QUERY] [--project NAME]` | no |
| `grove_work_create` | `grove work create NAME --title TITLE [--issue URL] [--plan TEXT] [--author NAME]` | yes |
| `grove_work_list` | `grove work list NAME [--status STATUS]` | no |
| `grove_work_get` | `grove work get ID` | no |
| `grove_work_update` | `grove work update ID [--status S] [--plan T] [--notes T] [--title T] [--note T] [--author NAME]` | yes |
| `grove_recommend_next` | `grove recommend NAME` | no |

Parameter spellings that differ: MCP `root_path` ↔ CLI `--root`; `issue_url` ↔
`--issue`; `body` ↔ `--file PATH` (`--file -` reads the body from standard
input); `project` ↔ positional `NAME` (or `-` for a
workspace-level note in `knowledge write`); `exclude` (a list) ↔ `--exclude
PATTERN`, repeated, where `--exclude ''` is the empty list and `--exclude '!'`
is `["!"]`, the list that clears (R-SCAN-9). List commands
take `--limit` and `--offset`. `--author` is `author` on every tool that
writes a name, `grove_ingest_map` included.

Two commands have no row, because they have no tool: `grove export NAME
[--out DIR]` and `grove view [NAME] [--port N]` (section 6.6). They change
nothing in the database, and the sixteen tools are as they were.

### 6.4 Knowledge

| Id | Requirement | Status |
|---|---|---|
| R-KNOW-1 | A knowledge document is identified by a slug key (lower-case letters, digits, `.`, `_`, `-`; at most 120 characters) within a scope. A scope is one project, or the workspace (no project). | tested: `test_knowledge.py` |
| R-KNOW-2 | Each scope numbers its revisions from 1. Concurrent writers of one key each get their own revision; none is lost. | tested: `test_db.py` |
| R-KNOW-3 | `knowledge get KEY` without a project returns the workspace document if one exists; else the only project's document; else `invalid`, naming the projects to choose from. | tested: `test_knowledge.py` |
| R-KNOW-4 | `knowledge get` returns at most the first 4000 characters of a longer body, cut at a line break, with `excerpted`, `body_chars`, an `outline` of up to 60 headings, `outline_total` and `more`, and with `next_line` when a line is left to read on from (R-KNOW-8). `full=true` returns the whole body. | tested: `test_knowledge.py` |
| R-KNOW-5 | Search covers the latest revision of each document only. Query words are quoted and ANDed; a trailing `*` is a prefix match; FTS5 operators typed by a caller are treated as words. Hits are ranked by BM25 and carry a snippet but no body. A query with no word is `invalid`. | tested: `test_knowledge.py` |
| R-KNOW-6 | **Listing.** `grove_knowledge_search` / `grove search` without a query lists the latest revision of every document (optionally of one project), newest first, without bodies and with `body_chars`; `query` is `null` in the result. | tested: `test_knowledge.py` |
| R-KNOW-7 | A search or listing limited to a project returns that project's documents only; workspace documents are not included. | tested: `test_knowledge.py`; see A6 |
| R-KNOW-8 | `knowledge get` tells the caller when the same key also exists in another scope, and can start its excerpt at a line taken from the outline. **Other scopes:** when at least one other scope holds the key, the result carries `other_scopes`, one entry `{"project": NAME}` per such scope, the workspace first as `{"project": null}`, then projects by name, at most 20; and `other_scopes_total`, the true count. The scope of the returned document is never listed, a scope counts once whatever its revisions, and both fields are absent when no other scope holds the key. Which document is returned is still decided by R-KNOW-3 alone. **Start line:** an optional `from_line` (`--from-line N`) is a line number, counted from 1 as the `outline` counts lines. The body then starts at that line and is cut as every excerpt is (R-KNOW-4): the same 4000 characters, no second size. Such a result carries no `outline`: the caller holds the one the line came from. `excerpted` is true whenever the body is not the whole document, so also for a document of 4000 characters or fewer read from a later line; from line 1 such a document comes whole, as without the parameter. **Reading on:** every excerpt that stops before the end of the document, with or without `from_line`, carries `next_line`: the first line it does not hold whole, to be passed as `from_line`. It is absent when no line is left. When an excerpt is part of one line longer than 4000 characters, `next_line` is the line after it and `more` names the line that was cut; only `full=true` returns the rest of that line. **Refused** with `invalid`: a line past the end (the message gives the number of lines), a line below 1 or not an integer, and `from_line` together with `full=true`. | tested: `test_knowledge.py` (both halves, service, MCP tool and CLI) |
| R-MAP-1 | `ingest-map` stores the file's full text as a knowledge revision (key: slug of the file stem) and seeds `declared` items from `documented` blocks, `actual` items from `observed-in-code` blocks and `map_untested` findings from `untested` blocks. Re-ingesting replaces what the same map seeded. The file is only read. | tested: `test_map_ingest.py` |
| R-MAP-2 | The legend is never seeded. Legend headings are "Legend", "Evidence labels", "Labels", "Notation", "Key", "Evidence" and "How to read ...". The full rules are in the `mapdoc.py` docstring, which is the reference. | tested: `test_map_ingest.py` |

### 6.5 Work items

| Id | Requirement | Status |
|---|---|---|
| R-WORK-1 | A work item belongs to one project and has `title`, optional `issue_url`, `status`, `plan`, `notes`, `author`, `created_at`, `updated_at`. It starts as `ready`. | tested: `test_work.py` |
| R-WORK-2 | Statuses are `ready`, `in_progress`, `review`, `done`, `blocked`. Their meaning: `ready` — specified and not started; `in_progress` — someone is working on it; `review` — the change exists and waits for a review by someone other than its author; `done` — reviewed and finished; `blocked` — cannot proceed, and `notes` SHOULD say why. | held (meanings are convention; Grove does not check them) |
| R-WORK-3 | **Any status may follow any other.** This is deliberate in v0: Grove records what agents report and does not police a workflow. The expected path is `ready → in_progress → review → done`. | tested: `test_work.py` (path); held (free transitions); see A5 |
| R-WORK-4 | `work update` replaces each of `status`, `plan`, `notes` and `title` that it is given and leaves the others. At least one of those or a `note` (R-WORK-5) is required. | tested: `test_work.py` |
| R-WORK-5 | A work item keeps an append-only history of status changes and progress notes, each with author and time, so two agents can log progress on one item without erasing each other. `work update` takes an optional `note` (at most 1000 characters; a blank one is no note) and an optional `author` (as in R-WORK-1, else `GROVE_AUTHOR`, else `null`). Every update that changes the status or carries a note appends exactly one event: `id`, `created_at`, `author`, `old_status`, `new_status` (equal when only a note was added) and `note` (`null` when none). Nothing else adds an event: not creating the item, and not replacing `plan`, `notes` or `title`. Events are never changed or deleted. `work get` returns `history`: `events`, the newest 20, newest first, and `total`, the true count. Lists and the results of `work create` and `work update` do not carry the history. | tested: `test_work.py`, `test_db.py` |
| R-WORK-6 | A work item can carry references (requirement ids, knowledge keys, finding keys, change URLs; text, never fetched) and be listed by one. References are not a field: they are read, on every read, from the item's `title`, `plan` and `notes` (not from history notes, and not from `issue_url`), and every work item row carries them as `refs`. Four forms are read: a requirement id (`R-HOME-2`: `R-`, capital letters, `-`, digits); `knowledge:KEY`; `finding:KEY`, with a finding key as R-REC-2 gives it; and a URL that starts with `https://`. A full stop that ends the sentence, and punctuation or a closing bracket after a URL, do not belong to the reference. `refs` is sorted, holds each reference once, and holds at most 50 references of at most 200 characters each; a longer one is left out, not cut, and `refs_omitted` counts what was left out (the field is absent when nothing was). Nothing is stored and there is no parameter. | partly. `refs` is tested: `test_work_refs.py` (WO-15, D-53). Open: listing by a reference (a `ref` filter on `work list`), deferred from WO-15 |

### 6.6 Export and view (for people)

Agents come first: they read and change a workshop through the sixteen
operations. A person gets a read-only copy, as Markdown pages (`grove
export`) and as a web page on the same machine (`grove view`). Neither adds
a capability (R-SCOPE-1): both show what the four capabilities store.

| Id | Requirement | Status |
|---|---|---|
| R-VIEW-1 | **Export.** `grove export NAME [--out DIR]` writes one project as Markdown pages: `index.md`; `requirements.md` (the declared items, grouped by source file); `blueprint/SLUG.md` for every source file (its items in the three layers, and the findings about it); `knowledge/SLUG.md` for every document of the project (the latest revision, with its number out of how many); `findings.md` (by kind, each finding under an anchor `<a id="KEY">`, a numbered key `abc#2` as `abc-2`); `work/index.md` and `work/ID.md` (plan, notes, the whole history, the references). Workspace notes belong to no project and are not exported. Every link is relative: a work item's references link the requirement (when a declared statement states that id), the knowledge document and the finding they name, and a finding links the page of its source file. A page name is a slug of lower-case letters, digits and dashes, at most 80 characters, never a raw path or key; when two names give the same slug, the first in sorted order keeps it and the other gets eight hexadecimal digits of a hash. The default DIR is `exports/SLUG` inside the data directory. The result reports `out`, `pages`, `written` and `stale` (each `total`, `items`, `omitted`), `unchanged` and `redactions`. | tested: `test_export.py` |
| R-VIEW-2 | **View.** `grove view [NAME] [--port N]` (default port 8765; 0 takes a free one) serves the same pages as HTML until it is interrupted, and prints the URL. It answers on fixed routes only: `/` (projects and workspace notes), `/p/ID`, `/p/ID/requirements`, `/p/ID/findings`, `/p/ID/blueprint/SLUG`, `/k/ID` (one revision of a knowledge document), `/w/ID` (a work item) and `/search?q=TEXT[&p=ID]`. Every page of a project has a sidebar: requirements, findings, blueprint files, knowledge, work items. Search runs on the server: knowledge by the full-text search of R-KNOW-5, blueprint items and findings by the text filters of `blueprint` and `gaps` (R-GAP-6). The view is read-only: every request opens the database with `mode=ro` and closes it, nothing is created or migrated, and a database of another schema version is refused with the remedy. | tested: `test_view.py` |
| R-VIEW-3 | **An export is deterministic and writes only where it may.** The same stored data gives the same bytes: pages and their parts are sorted by stable fields, line ends are LF, the encoding is UTF-8, each page ends in one newline, no page says when it was generated, and no row id appears where a key or a slug exists (work items have only their id). A page whose bytes are already on disk is not rewritten. An export writes only inside DIR, and every refusal (`invalid`) is decided before the first byte is written: DIR is the root of any registered project or inside one, both paths compared after resolving symlinks (R-INV-4); DIR is the data directory itself, or holds a `grove.db`; DIR is inside Grove's own source tree and the project's root is not that tree; DIR is not empty and holds no `.grove-export` marker (unknown files are never replaced); the marker names another project; DIR, the marker, a page or one of the three page directories is a symbolic link or not the kind of file it should be (no link is followed, and pages are opened without following one). Nothing is ever deleted: a page of an earlier export that is no longer produced is listed under `stale` and left in place. | tested: `test_export.py` |
| R-VIEW-4 | **No path of this machine in a page.** A source path is shown relative to the project root; the data directory, the database path and the project root are never shown; a map that was ingested from outside the root is shown by its file name only. Before a page is written, the exact text of the data directory and of the project root, and everything the patterns of `scripts/check-publish` look for (tokens of the services it names, database URLs with a password, agent session ids of the form `session_` and 20 or more letters and digits), and the user part of a home-directory path (`/home/NAME`, `/Users/NAME`, `C:\Users\NAME`), are replaced by `[redacted]` and counted in `redactions`. This is a net for what a note may hold, not a guarantee: exported pages are the user's data, whether to commit them is the user's choice, and the publish check of the repository they go to still applies. `grove view` shows stored text as it is; it leaves out the same paths Grove itself would supply. | tested: `test_export.py` |
| R-VIEW-5 | **The view is safe to leave running on one's own machine.** It binds 127.0.0.1 and nothing else; there is no option for another address. A request whose `Host` header is not exactly `127.0.0.1:PORT` or `localhost:PORT` (or is missing, or given twice) gets 403, so a page of another site cannot reach it under a name of its own (DNS rebinding). Only GET and HEAD are answered; every other method gets 405. No request names a file and none is opened: ids are digits, a slug must be one the project has, anything else is 404. All stored text is untrusted (R-SEC-4): it is HTML-escaped first, and only then a small Markdown subset is applied (headings, lists, emphasis, code, links); no HTML written in a note is passed on, and a link is followed only to `http://`, `https://` or a relative address, anything else stays text. No page carries a script, and every response, errors included, carries `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`. There is no login: any user of the same machine can read the pages while the command runs, and the README says so. | tested: `test_view.py` |
| R-VIEW-6 | **Command line only.** `grove export` and `grove view` have no MCP tool, by decision (D-54): the tool names, the input schemas and the bytes of `tools/list` are unchanged (R-INV-9, R-GROK-3), and an agent needs neither, since every page shows what the sixteen tools already return. | tested: `test_export.py`, `test_tool_schemas.py`, `test_docs_contract.py` (the tool-list limit) |

## 7. Quality requirements

| Id | Requirement | Status |
|---|---|---|
| R-QUAL-1 | `uv sync && uv run pytest -q` passes, repeatably. A test that fails intermittently is a defect of the same rank as a failing test. | tested (suite); held (repeatability) |
| R-QUAL-2 | The CLI does not import the MCP SDK unless the command is `mcp`, so ordinary commands start quickly. | tested: `test_invariants.py` |
| R-QUAL-3 | Module layering (see `docs/blueprint.md`): `scan`, `gaps`, `claims`, `tokens`, `mapdoc` and `errors` do not import `db`, `service`, `tools`, `cli` or `mcp_server`; only `mcp_server` imports the MCP SDK. | tested: `test_invariants.py` |
| R-QUAL-4 | A scan streams rows for the gap pass rather than holding the blueprint in memory. | manual (`BUILD_NOTES.md`: 37 MB peak on 32 694 items) |
| R-QUAL-5 | Targets on the reference machine: `grove mcp` answers `initialize` within 1 second of start; a scan of 2000 files finishes inside the default caps. | manual (`BUILD_NOTES.md`) |
| R-QUAL-6 | Supported platform: Linux with Python 3.13. macOS and Windows are unverified. | manual; open: WO-34 |
| R-QUAL-7 | The MCP server works with clients of the handshake era (`2025-11-25`) and of the per-request era (`2026-07-28`). The client's first request decides the era of a connection; a request of the other era is refused with a JSON-RPC error. Results are one text block; structured results are not offered (D-11, D-29). The server stops when stdin closes: the reply to a call still running at that moment is not delivered, and a call that has started still finishes (README, "Closing the connection"). | tested (both eras; one era per connection): `test_mcp_stdio.py`; manual (the behaviour when stdin closes: `BUILD_NOTES.md`) |
| R-QUAL-8 | A linter for error-class rules and a shell linter run clean, and one script runs every check. The linter is ruff with the pyflakes rules only (undefined and unused names, unused imports), pinned in the `dev` group; it judges no style and nothing is reformatted. `scripts/check` runs the linter, shellcheck on the bash files if it is installed, the tests with a temporary `GROVE_HOME` and `scripts/check-publish` on `HEAD`; it runs every step, reports each as passed, failed or skipped, and exits 1 if any failed. | tested (the linter's pin and rule set, the script's steps and exit code): `test_gates.py`; held (the linter runs clean: `scripts/check`, CI; the shell linter runs clean where it is installed, and is reported as skipped elsewhere) |
| R-QUAL-9 | Every change is checked by an automated gate that does not depend on the author's machine: one CI job on every pull request and every push to `main` installs the locked dependencies, runs the linter (R-QUAL-8), runs the tests and runs `scripts/check-publish` on the head commit. The job has a read-only token and no secrets, its actions are pinned to full commit SHAs, and no expression is expanded in the workflow. The check is visible, not required (A8). | tested (the workflow's rules): `test_gates.py`; held (the job itself runs on GitHub) |
| R-QUAL-10 | The precision of each finding kind and of search is measured on a small labelled corpus kept in the repository. The corpus is `fixtures/measure/`: three projects with their true gaps listed by hand, and notes with judged queries. Precision and recall of each of the four finding kinds, and recall, precision and reciprocal rank of search, are each held to a recorded floor, the value last measured cut to two decimals; a floor that a number has risen above fails too. The numbers and their date are in `docs/work-orders.md` (WO-23). They describe that corpus, not other projects. | tested: `test_measure.py` |

## 8. Caps (never silent)

Each cap names where it is reported. "Error" means the request is rejected
with `invalid`, which is also not silent.

| Cap | Value | Reported as | Status |
|---|---|---|---|
| Files walked per scan | 4000 (`max_files`) | `caps.hit`, `warnings`, project `caps_hit` | tested |
| Scan walk time | 8 s (`max_seconds`) | `caps.hit`, `warnings`, project `caps_hit` | tested |
| File size read | 512 KB | `skipped_files` (`too_large`, with `bytes`) | tested |
| Binary or unreadable file | — | `skipped_files` (`binary`, `unreadable`) | tested |
| Skipped/changelog paths listed, and files over the symbols cap | 50 | `total`, `omitted` next to `items` | tested |
| Line length analysed | 5000 characters | scan: `long_lines` (`max_line_chars`, `lines`, `files`), a warning, and on the project; ingest: `long_lines` (`max_line_chars`, `lines`) | tested |
| Declared items per document | 1000 | `caps.declared_capped` (`total`, `kept`, `dropped`, `dropped_by_class`), a warning | tested |
| `actual_undocumented` findings stored | 25 | `findings_cap`; `gaps`: `complete`, `omitted`, `true_total` | tested |
| Sample findings in a scan result | 5 | `more` points to `gaps`; counts are complete | tested |
| Keys and findings listed in a scan's `delta` | 50 added keys, 50 resolved findings | `delta`: `added` and `resolved` are the true counts, `list_cap`, `complete` is false, `note` | tested |
| Knowledge excerpt | 4000 characters, from the first line or from `from_line` | `excerpted`, `body_chars`, `more`; `next_line` when a line is left to read on from | tested |
| A line longer than a knowledge excerpt | 4000 characters | reading on by `next_line` passes over the rest of the line: `more` names the line; `full=true` returns it | tested |
| Outline headings | 60 | `outline_total` | tested |
| Other scopes named by `knowledge get` | 20, the workspace first, then projects by name | `other_scopes_total` is the true count | tested |
| Page size | 200 | `limit` in the result shows the clamped value | tested |
| Files kept out by a project's exclude list | — (chosen by the caller) | scan: `excluded` (`patterns`, `files`); project: `last_scan.excluded` | tested |
| `query` of `blueprint` and `gaps` | 200 characters | error | tested for `gaps` (`test_gaps_query.py`); held for `blueprint` |
| Exclude list size | 50 patterns, each one line of at most 200 characters | error | tested |
| Text argument size (`body`, `plan`, `notes`, map file) | 2 MB | error | held; tested for a body from standard input (`test_cli.py`), where reading stops one byte past the cap |
| Title | 300 characters | error | held |
| Author | 64 characters, one line | error | tested |
| History note (`note` on `work update`) | 1000 characters | error | tested |
| References listed on a work item (`refs`) | 50, the first in sorted order; a reference longer than 200 characters is left out, not cut | `refs_omitted` on the item counts both; absent when nothing was left out. `recommend` reads the same list, so a `finding:KEY` that was left out skips nothing | tested |
| History events returned by `work get` | 20, the newest | `history.total` is the true count; older events stay stored and are not returned by any operation | tested |
| Pages named in an export result | 50 written, 50 stale, in sorted order | `written` and `stale`: `total` is the true count, `omitted` the rest | tested |
| Entries in a list of the view's sidebar | 100 per list | the page says how many more there are; the project page lists every one | held |
| Hits shown by the view's search | 20 per kind and project; 20 projects when none is named | the page shows the true number of hits, and says when projects were left out | held |
| Symbols or test names per file | 500 | scan: `caps.symbols_capped` (per file: `path`, `kind`, `found`, `kept`, `dropped`), `caps.max_symbols_per_file`, a warning, and on the project; blueprint: `symbols_found` or `tests_found` in the `extra` of the module or test-file item | tested |
| Names listed in a module or test-file body | 40 | `(+N more)` at the end of the body text | held |
| Item title / body length | 160 / 2000 characters | the text ends in `…` | held |

Not caps: sentences with fewer than three words, and claims with fewer than
two tokens, are left out by the extraction rules (R-SCAN-3, R-GAP-3). They
are documented, not counted. Nor is the `commit` in a status `build`: it is
12 digits by definition, whatever the length of the full id (R-GROK-9).

## 9. Security

Grove runs with the permissions of whoever starts it and trusts that person.
It does not trust the *content* it reads.

| Id | Requirement | Status |
|---|---|---|
| R-SEC-1 | Content of scanned projects, map files and knowledge bodies is untrusted data. Grove MUST NOT execute, import or evaluate it. | tested: `test_invariants.py` (no `subprocess`, `importlib`, `eval`, `exec` in `sf_grove`) |
| R-SEC-2 | SQL values are always bound parameters. SQL text is built only from fixed fragments in the source. | held (reviewed; `bandit` B608 reports are fixed fragments) |
| R-SEC-3 | Reads are bounded (section 8) and symlinks are not followed, so a scan cannot leave the project root. | tested: `test_scan_safety.py` |
| R-SEC-4 | Text returned by Grove may have been written by a third party (a scanned README, a map, another agent's note). The server instructions MUST say that such text is data to weigh, never instructions to follow. A client may show its model the tool descriptions and not the instructions, so the descriptions of `grove_blueprint_get`, `grove_gaps`, `grove_knowledge_get` and `grove_knowledge_search`, the four tools that page such text, MUST say it too, in a clause. Grove returns the text verbatim and marks its provenance only in fields Grove sets (`origin`, `source_path`, `author`). | tested (the sentence, in the instructions a client receives): `test_mcp_stdio.py`; (the clause on the four descriptions): `test_docs_contract.py`; held otherwise |
| R-SEC-5 | `ingest-map` reads only a map-like file: one whose name ends in `.md`, `.markdown`, `.mdx`, `.rst` or `.txt` (in any case) or has no extension. Any other name is `invalid`, and the message lists what is accepted. A name that is only a dot and a word (`.env`) counts as an extension, not as a file without one. The name judged is that of the file itself, after symlinks are resolved, and it is judged before the file is looked for or read. The list is the one the scanner reads as documents. This narrows the file type and is not a guard against secrets: a file without an extension is still read (up to 2 MB) and stored as knowledge. | tested: `test_map_ingest.py`, `test_cli.py`, `test_mcp_stdio.py` |
| R-SEC-6 | `scripts/check-publish` blocks forbidden file names, secret-like content, agent session ids and local private-path patterns on the revision it is given. Secret-like content and session ids are looked for in the tracked files and in the revision's commit message. Private-path patterns come from the uncommitted `scripts/check-publish.local`, so they are checked only on a machine that has that file (not in CI). A check that cannot be made (a revision that does not exist, a search that does not run) fails. The pre-push hook runs the script on every commit a push adds to the remote: an update, a new branch, or a branch whose remote commit the clone does not have; a deletion is skipped. | tested: `test_gates.py` (WO-26). CI checks the head commit only (R-QUAL-9) |
| R-SEC-7 | The repository states how to report a vulnerability, what to do if a secret was pushed, and how a dependency pin is changed. | tested: `test_docs_contract.py` (`SECURITY.md`: one contact address, the four parts, the pins it names) |

## 10. Client fitness

### 10.1 Grok Bot (MCP)

| Id | Requirement | Status |
|---|---|---|
| R-GROK-1 | Everything Grove offers is usable through the sixteen MCP tools alone, with no shell access and no environment variables (hence `author` and `body` parameters). | held; tested for `author` on `grove_ingest_map`: `test_mcp_stdio.py`, `test_map_ingest.py` |
| R-GROK-2 | Tool descriptions are the documentation an MCP client reads. Each MUST say what the tool does, when to use it, and which caps and heuristics apply; each MUST agree with the code. | tested for the recommend order, the listing mode and what a client without server instructions must still read (R-GROK-6, R-SEC-4): `test_docs_contract.py`; held otherwise |
| R-GROK-3 | **Context budget.** The serialised `tools/list` result MUST stay at or below 15 000 bytes (16 384 until WO-20). | tested: `test_docs_contract.py` (14 985 bytes today, which leaves 15; it was 16 366 before WO-20, 14 946 before WO-16, 14 895 before `from_line`, WO-19, 14 934 before `delta`, WO-37, and 14 933 before `query` on `grove_gaps`, WO-38) |
| R-GROK-4 | No default result is unbounded: lists are paged, scans are summarised, long documents are excerpted. Only an explicit `full=true` returns up to 2 MB. | tested: section 8 |
| R-GROK-5 | `grove_status` is enough to notice a wrong data directory (R-HOME-2). | tested: `test_status.py` |
| R-GROK-6 | Server instructions describe the working loop: status first; search or list knowledge before starting; list `in_progress` and `review` work to resume; ids change on rescan; pass absolute paths; findings are hints. A client may show its model the tool descriptions and input schemas and nothing else (no instructions, no annotations), so the description of `grove_status` states the loop in one short line, and carries, once, the sentence that Grove is local only. | tested: `test_docs_contract.py` (the instructions in full; the loop line and the local-only sentence on `grove_status`), `test_mcp_stdio.py` (what a client receives, and the annotations) |
| R-GROK-7 | The registration shape that Grok Bot's AddMcpServer accepts is verified against Grok Bot and recorded. | held in part: on 2026-11-12 three Grok Bots listed and ran the sixteen tools on the machine that holds the data directory (README, "Grok Bot"). The exact shape they registered, the Grok Bot version and the protocol revision were not recorded; that part is open: WO-11 |
| R-GROK-8 | Navigating a large blueprint does not require paging the whole declared layer. `blueprint` takes two optional parameters. `summary` returns, instead of items, a page of source files in path order: each row is a `source_path` with its number of items in `declared`, `actual` and `tests`, and `total` counts the files. `source_path` keeps the items of one path, or, when it ends in `/`, of every path that starts with it. It is compared exactly, case included, with the path as items show it (relative to the project root for scanned files; the map file's own path for items a map seeded); a path that matches nothing is an empty page. `layer`, `query` and `source_path` narrow a summary as they narrow the items. Without the two parameters the result is unchanged. | tested: `test_blueprint_navigation.py` (service, MCP tool, CLI) |
| R-GROK-9 | `grove status` / `grove_status` MUST report `build`, which names the build that is running: `version`, and `commit` when Grove runs from a git checkout of its source (the first 12 hexadecimal digits of the checked-out commit, as `git rev-parse --short=12 HEAD` prints them). `commit` is left out, and the call still succeeds, when the source is not such a checkout or the commit cannot be read. The build is read once, when the process starts, so a server that was not restarted after an upgrade reports the commit it started from. No value in `build` is a path. Uncommitted changes are not reported. | tested: `test_build.py`, `test_status.py`, `test_mcp_stdio.py` |

### 10.2 Claude Code (CLI or MCP)

| Id | Requirement | Status |
|---|---|---|
| R-CC-1 | `CLAUDE.md` is the working brief for an agent in this repository: how to call Grove without relying on shell state, the rules of the house, and how to change Grove safely (pointing here). It MUST agree with this file. | held |
| R-CC-2 | The README documents how to use Grove from another repository: a snippet for that project's or the user's `CLAUDE.md`, and an MCP registration that sets `GROVE_HOME`. | held (README "Claude Code") |
| R-CC-3 | A returning session can find its unfinished work: `grove work list NAME --status in_progress` and `--status review`. | held (documented); a recommend hint is open: WO-29 |
| R-CC-4 | Knowledge can be written without creating a file inside the scanned project: `knowledge write --file -` reads the body from standard input. A terminal on standard input is refused with `invalid`, not waited on (R-IF-9). | tested: `test_cli.py` |
| R-CC-5 | The `grove` command is available outside the repository directory: the README documents a link on `PATH` to the command `uv sync` installs. | tested: `test_cli.py` (the link, run by name from another directory); README "`grove` from any directory" |

## 11. Definition of done

### 11.1 For a change to Grove

A change is done when all of these hold:

1. **Argued.** Before it was built, the change was weighed as an engineer
   would weigh it in review: is it the simplest thing that actually serves
   Grove (parsimony); what does it cost on every call and in every session
   (efficiency); what could it break or make permanent (unintended
   consequences). A resource or a possibility is not a reason. What was
   considered and left out is recorded with the work order.
2. **Traced.** It names the requirement ids it implements and the work order
   it closes. If behaviour changes, this file changed first or in the same
   change, and the requirement's status is updated.
3. **Tested.** Each new behaviour has a test that fails without it.
   `uv run pytest -q` passes with a temporary `GROVE_HOME`.
4. **Both surfaces.** Service method, MCP schema and description, CLI flag
   (R-IF-10).
5. **Compatible.** Additive only (section 3). No rename, no removal, no new
   error code.
6. **Caps reported.** Any new cap or truncation appears in the result and in
   section 8.
7. **Migrated.** A schema change is a new entry in `db.MIGRATIONS` with a test
   that upgrades a database from the previous version.
8. **Documented.** README for users, the tool description for MCP clients,
   `docs/blueprint.md` when structure or the data model changes,
   `CHANGELOG.md` always.
9. **Within the invariants.** No network, no model, no new runtime dependency.
10. **Publishable.** `scripts/check-publish` passes on the commit. No hook is
   skipped.
11. **Reviewed.** Someone other than the author (a person or a different
    agent) has read the change. The authoring agent does not merge its own
    pull request.

`scripts/check` runs the mechanical part of this list in one command: the
linters of R-QUAL-8, the tests of item 3 and the publish check of item 10.
It does not replace the other items.

### 11.2 For work tracked in Grove on another project

Grove records status; it cannot prove it. By convention a work item moves to
`review` only when the change and its tests exist, and to `done` only when a
reviewer other than the author accepted it. The project's own definition of
done SHOULD be kept as a knowledge document with the key `definition-of-done`
in that project's scope, so that every agent finds it with one call.

## 12. Assumptions and open decisions

Each default is reversible. An owner decision replaces the default and is
recorded in the decision log in `docs/blueprint.md`.

| Id | Question | Default taken | To reverse |
|---|---|---|---|
| A1 | Is "sixteen tool names frozen; optional parameters and new result fields allowed" the official rule? | **Yes.** It is stated as decided in the owner's brief of 2026-11-12 and is now R-INV-9 and R-COMPAT-2. | Edit section 3. |
| A2 | Should `recommend` put the agent's own unfinished work first? | **No change to the order in v0.** The tier order is tested and documented. A non-breaking hint about open work is proposed instead (WO-29). | Add a tier; update R-REC-1 and the tool description. |
| A3 | Is deletion or archiving in scope for v0? | **No.** Nothing is deleted. A non-destructive archive flag is a later work order (WO-30). | Schedule WO-30 earlier. |
| A4 | Do Grok Bot and Claude Code share one data directory? | **Yes**, one per machine, with `author` telling the agents apart (R-HOME-3). | Give each agent its own `GROVE_HOME`. |
| A5 | Should Grove enforce work-item transitions? | **No.** All transitions are allowed (R-WORK-3); a history records them instead (R-WORK-5, built in WO-14). | Add validation under R-COMPAT-6. |
| A6 | Should a project-scoped search include workspace notes? | **No** (current behaviour, R-KNOW-7). An opt-in parameter was considered and left out: a second call does it (WO-19). | Change the default under R-COMPAT-9. |
| A7 | Are agent instruction files (`CLAUDE.md`, `AGENTS.md`) and requirement files part of the declared layer? | **No.** They are not read. Matching explicit requirement ids is a later order that waits for measurement (WO-22). | — |
| A8 | May continuous integration be added to the public repository? | **Decided by the owner: yes** (2026-11-12), in the shape of WO-08: one job, read-only, no secrets. The check is **visible, not required**: no branch protection and no required status check, until the owner has seen it stay green (D-34). | Delete `.github/workflows/ci.yml`. To make it required instead, the owner adds a branch-protection rule; nothing in the repository changes. |
| A9 | Should relative paths be rejected over MCP? | **No**; they resolve against the server's working directory and the result shows the absolute path (R-IF-8). | Add the rule under R-COMPAT-6. |

## 13. Glossary

- **Blueprint** — the stored items of a project in three layers.
- **Declared / actual / tests** — what the docs say / what the code appears to
  contain / what the tests appear to prove (by name).
- **Finding** (gap) — a place where two layers disagree, by token overlap.
- **Map** — a Markdown architecture description whose blocks carry the
  evidence labels `documented`, `observed-in-code`, `untested`.
- **Knowledge document** — a keyed, revisioned note in a scope.
- **Scope** — one project, or the workspace.
- **Work item** — a locally tracked unit of work for a project.
- **Home / data directory** — the directory holding `grove.db`.
- **Envelope** — the `{ok, data}` / `{ok: false, error}` result shape.
- **Work order** — a planned upgrade of Grove itself (`docs/work-orders.md`).
