# Build notes — Grove v0 (0.1.0)

Written last, on 2026-11-12, on the target machine (Debian 13, x86_64,
Python 3.13.5, uv 0.13.7, SQLite 3.46.1).

**Status of this file.** This is the record of the first build and of what
was verified then. It is kept as history. What Grove must do is now in
`REQUIREMENTS.md`, which replaces "the spec" mentioned below; where the two
differ, `REQUIREMENTS.md` wins. Later changes are listed in `CHANGELOG.md`,
and the section "After the requirements review" at the end corrects two
statements made here.

## What was built

| Piece | Where |
|---|---|
| Storage: one `grove.db`, WAL, FTS5, forward-only migrations run on open | `src/sf_grove/db.py` |
| Read-only scan: walk, `.gitignore`, caps, declared / actual / tests extraction | `src/sf_grove/scan.py` |
| Gap findings by token overlap | `src/sf_grove/gaps.py`, `src/sf_grove/tokens.py` |
| Declared-sentence classes (behaviour / limit / setup / prose) | `src/sf_grove/claims.py` |
| MAP.md parser (evidence labels) | `src/sf_grove/mapdoc.py` |
| All sixteen operations, validation, recommend-next | `src/sf_grove/service.py` |
| Tool table (names, descriptions, schemas) and the JSON envelope | `src/sf_grove/tools.py`, `src/sf_grove/errors.py` |
| CLI (`grove`, console script) | `src/sf_grove/cli.py` |
| MCP stdio server (`grove mcp`), official Python SDK `mcp==2.3.0`, low-level `Server` | `src/sf_grove/mcp_server.py` |
| Fixtures | `fixtures/tiny/`, `fixtures/map_sample.md` |
| Tests (117 after the team trial; run `uv run pytest -q` for the current count) | `tests/` |

Runtime dependencies, pinned exactly: `mcp==2.3.0`, `pathspec==1.1.1`
(`.gitignore` matching). Dev: `pytest==9.2.0`. Everything else is the standard
library. `uv.lock` pins the full tree. No Linux-only calls are used; nothing
was run on macOS (see "Not verified").

## How it was verified

```
uv sync && uv run pytest -q
...................................................                      [100%]
51 passed in 1.21s
```

Run six times in a row with the same result. (This block predates the
team-trial upgrades, which brought the suite to 117 tests.)
The seven required tests map to:

| # | Requirement | Test file |
|---|---|---|
| 1 | Scan + gaps on `fixtures/tiny` (greet is `declared_untested`, both functions in `actual`) | `tests/test_scan_gaps.py` |
| 2 | Knowledge write, revision bump, FTS search | `tests/test_knowledge.py` |
| 3 | Work item lifecycle | `tests/test_work.py` |
| 4 | MAP ingest on `fixtures/map_sample.md` | `tests/test_map_ingest.py` |
| 5 | MCP stdio smoke: real `grove mcp` child, initialize + tools/list + tool calls, 16 tools, stdout purity | `tests/test_mcp_stdio.py` |
| 6 | Scan does not write inside the fixture tree (mtime, size and SHA-256 of every file and directory, before and after) | `tests/test_scan_safety.py`, also `tests/test_cli.py` |
| 7 | Caps set low are honoured, reported and recorded on the project | `tests/test_scan_safety.py` |

Also covered: CLI exit codes and envelopes (including usage errors), `--home`
beating `GROVE_HOME`, paging limits (default 50, clamp at 200), `.gitignore` and
always-skipped directories, the per-language regexes, migrations (reopen,
refusing a newer schema), and eight threads opening a fresh database and
writing the same knowledge key at once (40 writes, revisions 1..40, none lost).

Every test uses a temporary `GROVE_HOME`; an autouse fixture also points the
ambient `GROVE_HOME` at a temp directory so nothing can reach `~/.grove`.

**How stdout purity is proven.** The test speaks raw JSON-RPC to the child
over pipes, makes the server log (startup line plus two deliberately failing
tool calls), closes stdin, waits for exit code 0, then asserts that *every*
line the child wrote to stdout parses as a JSON-RPC 2.0 message and that the
log lines are present on stderr and absent from stdout.

### Manual checks (not part of pytest)

- **Official SDK client.** `mcp.ClientSession` over `stdio_client` against
  `grove mcp`: negotiated protocol `2025-11-25`, listed 16 tools, ran
  create / scan / recommend, and saw `isError` with a `not_found` envelope
  for a missing work item.
- **Startup.** Spawn to `initialize` reply, five runs: 0.43–0.50 s.
  `uv run --project . grove mcp`, invoked from another directory, also
  answered `initialize`.
- **Memory.** `grove mcp` after a tool call: 69 MB resident, almost all of it
  the MCP SDK and its imports. A CLI scan of the largest example repo
  (1750 files, 32 694 blueprint items) peaked at 37 MB and took 1.9 s
  end to end. The first version of that path peaked at 92 MB; the gap pass
  now streams rows from SQLite instead of holding them.
- **Real repositories, read-only.** Scanned four shallow clones of public
  repositories (Octomind, rueidis, the MCP Rust SDK, and MCP Memory Service)
  and ingested each project's `MAP.md` into a temporary home. Scans took 0.13–0.98 s; no cap was hit. `git status
  --porcelain` was empty in all four clones afterwards and no `MAP.md` was
  modified.

  | Project | Files seen | declared / actual / tests | Map blocks seeded (declared / actual / `map_untested`) |
  |---|---|---|---|
  | octomind | 740 | 9453 / 4961 / 5372 | 5 / 27 / 7 |
  | rueidis | 299 | 501 / 11220 / 959 | 12 / 68 / 17 |
  | rust-sdk | 305 | 1464 / 4650 / 1513 | 4 / 78 / 5 |
  | mcp-memory-service | 1750 | 20295 / 5363 / 7036 | 32 / 92 / 9 |

  I read a sample of the output by eye. I did not measure precision or
  recall of any finding kind.

## Not verified

- **Grok Bot.** The README gives `command`, `args` and `env` for AddMcpServer.
  I did not register Grove with Grok Bot or any other account (by
  instruction), so the exact shape AddMcpServer expects is not confirmed
  against the real thing. The values themselves were exercised: that command,
  with that argument and environment variable, starts a working server.
- **macOS.** Not run. The code uses only the standard library and the two
  pinned dependencies, with no Linux-specific calls.
- **The newer MCP protocol era.** SDK 2.3.0 also serves a per-request
  protocol (`2026-07-28`) without an `initialize` handshake. Only the
  handshake era (`2025-11-25`) was tested. (Both are tested since WO-25:
  `tests/test_mcp_stdio.py`.)

## Upgrades after the team trial

Schema migration 2 adds `projects.findings_cap`, `work_items.author` and
`knowledge.author`; older databases are upgraded in place on open. No tool
was renamed and no field removed.

1. Map legends no longer become findings (rules under "Map ingest" below).
2. Changelogs add no declared items; the per-document cap is 1000 with
   claims kept first, and capped documents are named.
3. Findings caps report the true total (`findings_cap`, `true_total`).
4. Skipped files are named.
5. `knowledge get` returns a 4000-character excerpt with a heading outline
   unless `full` is true.
6. Work items and knowledge revisions record an optional `author`.

## Decisions that the spec left open

- **Knowledge keys are unique per scope**, a scope being one project or the
  workspace. `MAP.md` therefore becomes key `map` in each project without
  clashing. `knowledge get KEY` without a project returns the workspace-level
  document if there is one, else the only project's document, else an
  `invalid` error asking for a project. `grove_knowledge_get` and
  `grove_knowledge_search` take an optional `project` for this reason.
- **Search covers the latest revision of each document only.** Older
  revisions stay retrievable by number. Query words are quoted and ANDed, so
  FTS5 operators typed by a user are treated as words; a trailing `*` is a
  prefix match. The tokenizer is `porter unicode61`.
- **Gap findings are computed only once a project has been scanned.** A map
  ingested into an unscanned project stores its items and `map_untested`
  findings, and the response says the token-overlap pass was skipped.
  Otherwise every `documented` line of the map would be reported as untested.
- **Map-seeded items take part in the gap pass** after a scan: a `documented`
  block is a declared claim like any README sentence.
- **Recommend-next tiers.** `map_untested`; then `declared_untested` whose
  words also appear in code names (my reading of "clearly untested confirmed
  gaps"); then other `declared_untested`; then the oldest `ready` work item;
  then `actual_undocumented`. Since the claim classes were added, the two
  `declared_untested` tiers only consider class `behaviour` (map blocks always
  count as `behaviour`); class `limit` gets its own tier
  (`check_documented_limit`) after ready work items, and `setup`/`prose`
  sentences produce no finding at all. `declared_unseen` is reported by `gaps` but
  never recommended, since the spec's order does not include it.
- **`limit` above 200 is clamped**, not rejected; `limit < 1` and
  `offset < 0` are `invalid`.
- **MCP tool results are one text block** holding the envelope, with
  `isError` mirroring `ok`. No `structuredContent` and no output schemas.
  An unknown tool name returns a `not_found` envelope rather than a protocol
  error.
- **CLI additions beyond the listed synopsis**, so that it offers the same
  operations as the MCP tools: `work get ID`; `--plan`, `--notes`, `--title`
  on `work`; `--query`, `--limit`, `--offset`, `--project`, `--revision`,
  `--max-files`, `--max-seconds` where the matching tool has them; `-` as the
  project name in `knowledge write` for a workspace-level note. `--text` is
  implemented as a generic key/value rendering.
- **Project names** may not be all digits, so a name can never be mistaken
  for an id.
- Resources and prompts are not implemented.

## Limits

### Scanner

- Regex per line, not a parser. Definitions inside strings or block comments
  are recorded; multi-line signatures can be missed.
- Not recorded: TypeScript/JavaScript class methods and object-literal
  functions; Go types inside `type ( ... )`; Rust `impl` blocks as such
  (their `fn`s are recorded, flagged `nested`); Python nesting is known only
  as "indented or not".
- Tests: names only. A file counts as a test file by name pattern; Rust
  `#[test]`, `#[tokio::test]`-style, `#[rstest]` and `#[test_case]`
  functions are found in any `.rs` file. Parametrised cases, `describe`
  blocks, `proptest!` bodies, Go subtests, benchmarks and doctests are not
  seen. JavaScript test names built from variables or template expressions
  are missed.
- A file keeps its first 500 symbols, or its first 500 test names if it is a
  test file. The scanner used to stop reading the file there and say
  nothing. It now reads on to count, names the file in
  `caps.symbols_capped` with the numbers found and kept, and puts the number
  found on the file's own blueprint item (`symbols_found`, `tests_found`).
  Counting costs time: a file at the size limit that holds nothing but
  one-line definitions (40 000 of them) took 4 ms before and takes 45 ms
  now; the time cap still ends it. Two things are as they were and are now
  visible: in a Rust file the cap counts every definition, so inline tests
  share the 500 with the symbols and a Rust test file with many helpers
  keeps fewer than 500 tests.
- Docs: Markdown-shaped text only (the README lists the constructs under
  "Which Markdown is read"). README*, CHANGELOG*, CHANGES*, HISTORY*,
  CONTRIBUTING*, ARCHITECTURE*, DESIGN* anywhere, plus `.md`/`.markdown`/
  `.mdx`/`.rst` under any `docs/` or `doc/` directory. reStructuredText gets
  underline headings and nothing else. Indented (four-space) code blocks are
  read as prose. Sentence splitting is a regex and breaks on "e.g. Foo".
  Sentences with fewer than three words are dropped. Changelogs and release
  notes (see `is_changelog_file` in `scan.py`) are walked and listed under
  `changelog_files` but add no declared items. Each other document keeps at
  most 1000 items (it was 400; a config reference of 499 and an RFC of 447
  items were cut in the team trial). Over the cap, headings and
  `behaviour`/`limit` sentences are kept before `setup`/`prose` ones; the
  scan names the file in `caps.declared_capped` with kept and dropped counts.
- `.gitignore`: each file is applied relative to its own directory through
  `pathspec`. A negation in a deeper file does not re-include something a
  shallower file ignored. `.git/info/exclude` and global ignores are not read.
- Symlinks are not followed. Files over 512 KB or containing a NUL byte in
  the first 4 KB are counted but not read; they are named in
  `skipped_files` (first 50, with `total` and `omitted`) with a reason.
- **The caps bound the walk, not the whole operation.** Storing the items
  and computing gaps happens afterwards and is not timed; on the largest
  example it took about one second. (Since the requirements review the time
  cap is also checked between the lines of a file, and lines over 5000
  characters are skipped and reported.)
- A rescan deletes and re-inserts scan-derived rows, so blueprint item ids
  and finding ids change on every scan. Do not store them in notes.

### Gap heuristic

- One shared token silences a finding. On real projects with thousands of
  tests almost every sentence shares some word with some test, so
  `declared_untested` is sparse and what remains is often non-claims
  (greetings, platform tables). On `fixtures/tiny` it is exact; that fixture
  was written to be easy.
- The stemmer is four suffix rules. "named" and "name" do not meet.
- Stop words include `test`, `src`, `lib`, `main`, `mod`, `index` and file
  extensions, so modules called `main.py` or `index.ts` are never reported as
  undocumented.
- `actual_undocumented` is capped at 25 stored findings. The cap, the number
  of candidates and the number omitted are kept on the project
  (`findings_cap`) and returned by scan, gaps and project get; `gaps` adds
  `complete`, `omitted` and `true_total`, while `total` stays the pageable
  count of stored findings.
- `actual_undocumented` asks only whether the file name or its stem words
  appear in the docs. `calc.py` is reported for the tiny fixture although its
  behaviour is documented, because the word "calc" is not.

### Map ingest

- Labels are matched as whole words anywhere in a block, case-insensitively,
  so ordinary prose that says "documented" is treated as the label.
- The legend is not seeded. A block is skipped when it sits under a legend
  heading, *begins* with a label, names two or more labels and defines them
  or uses legend words, says "the label X" / "X means", or is a short lead-in
  ending in ":" (at most four words besides labels). The rules are
  word-based: a claim that names two labels and happens to contain "means"
  is skipped as legend.
- A real finding written as "Untested: ..." is skipped too, because it begins
  with a label. Write the label after the claim.
- Labels are inherited from the nearest heading, from a table's header row,
  and from a short lead-in ("Missing — untested:") for the list items
  directly beneath it (deeper-indented items when the lead-in is itself a
  list item). A longer introductory paragraph passes nothing down.
- Nested list items are separate blocks and do not inherit from their parent
  item. HTML and reference-style footnotes are not understood.
- The knowledge key is the file name's stem. Two maps with the same file
  name ingested into one project are treated as revisions of one document,
  and the later one replaces what the earlier one seeded.
- Files over 2 MB are rejected.

## Still rough

- `--text` output is generic and unpolished; JSON is the real interface.
- `blueprint --query` is a `LIKE` substring match, case-insensitive for
  ASCII only.
- Work items are not linked to findings, so `recommend` can keep suggesting a
  finding that already has a work item.
- `author` is a free-text label from `--author` or `GROVE_AUTHOR`, not an
  identity; anyone on the machine can type any name.
- There is no way to delete or rename a project, a knowledge document or a
  work item in v0.
- After independent verification, an initial local commit was made on `main`.
  Claude Code / Fable itself left the tree uncommitted.

## Claude Code sessions

How to resume a particular local Claude Code session is kept in `LOCAL.md`,
which is not committed. That file also holds machine-specific paths. No
`.claude/settings.json` was added: nothing conservative was needed, and
permission bypass must not be the default.

## After the requirements review (2026-11-13)

A review of the requirements, with a survey of industry practice, ran in a
cloud session on Linux (Python 3.13.18, SQLite 3.53.1). Its documents are
`REQUIREMENTS.md`, `docs/blueprint.md`, `docs/analysis.md`,
`docs/industry-survey.md` and `docs/work-orders.md`. Two statements above
needed correcting:

- **"Eight threads opening a fresh database ... none lost."** The writes were
  never lost, but the *open* was not reliable: in a stress run 15 of 400
  concurrent first opens failed with "database is locked" at
  `PRAGMA journal_mode = WAL`, and `test_concurrent_first_open_and_writes`
  failed about once in thirty runs. The switch to WAL is now retried; 1500
  stress runs passed afterwards.
- **"The caps bound the walk."** One file could outlast the time cap by
  itself: a 40 000-character line took 13.6 seconds to analyse, a paragraph
  of 20 000 lines 7.8 seconds, both growing quadratically. See the note under
  "Limits" above and `tests/test_scan_robustness.py`. The line cap of that
  fix did not cover text that has no lines to cap: a paragraph of a map
  (9 seconds for 40 000 characters) and a line of a knowledge document
  (11 seconds for one heading line of 40 000 characters). The patterns
  themselves are linear since WO-24, and `tests/test_parser_random.py`
  runs every extractor on generated input.

Also verified by hand in that session: `grove mcp` answers
`server/discover`, `tools/list` and `tools/call` of the per-request protocol
(`2026-07-28`) without an `initialize` handshake. Since WO-25 a test does
the same (`tests/test_mcp_stdio.py`). Replies to calls still running when
stdin closes are not delivered.

**When stdin closes (measured for WO-25, by hand; no test).** 150 runs of
`grove mcp`, in both protocol eras: 1, 4, 12 or 60 `tools/call` requests
written in one go (`grove_project_create` or `grove_status`), stdin closed
0 to 100 milliseconds later. In every run the exit code was 0, stdout held
only whole JSON-RPC lines, stderr held nothing but the two log lines, and
no reply was an error. With 1 to 12 requests no reply arrived at all: the
process is still starting when the input ends, so it reads the requests
and the end of input together. With 60 requests, 9 to 24 replies arrived.
Every `grove_project_create` was stored in every run, answered or not (75
runs). So: the reply to a call still running when stdin closes is lost
without an error in its place, and a call that has started still finishes.
It is not a test because which replies are lost is a race; the half that
is certain (every request is answered while stdin stays open) is in
`tests/test_mcp_stdio.py`.

**"I did not measure precision or recall of any finding kind."** They are
measured since WO-23 (2026-11-13), on a corpus of three small projects and
sixteen notes kept in `fixtures/measure/`, by `tests/test_measure.py`. In
short: a `map_untested` finding is nearly always right (13 of 14), a
`declared_unseen` finding nearly never (2 of 22), and about seven in ten
true `declared_untested` gaps are not reported (17 of 24), mostly because
one shared word silences a finding, as the limits above say. The table,
the search numbers and the weaknesses found are in `docs/work-orders.md`
under WO-23. The four public repositories named above were not measured:
nobody has listed their true gaps.

Still not verified: Grok Bot (WO-11), macOS and Windows (WO-34).
