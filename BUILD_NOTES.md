# Build notes — Grove v0 (0.1.0)

Written last, on 2026-11-12, on the target machine (Debian 13, x86_64,
Python 3.13.5, uv 0.13.7, SQLite 3.46.1).

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
| Tests (51) | `tests/` |

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

Run six times in a row with the same result. The seven required tests map to:

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
  handshake era (`2025-11-25`) was tested.

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
- Docs: Markdown-shaped text only. README*, CHANGELOG*, CHANGES*, HISTORY*,
  CONTRIBUTING*, ARCHITECTURE*, DESIGN* anywhere, plus `.md`/`.markdown`/
  `.mdx`/`.rst` under any `docs/` or `doc/` directory. reStructuredText gets
  underline headings and nothing else. Indented (four-space) code blocks are
  read as prose. Sentence splitting is a regex and breaks on "e.g. Foo".
  Sentences with fewer than three words are dropped. Each document keeps its
  first 400 items; the scan warns when it truncates (changelogs do).
- `.gitignore`: each file is applied relative to its own directory through
  `pathspec`. A negation in a deeper file does not re-include something a
  shallower file ignored. `.git/info/exclude` and global ignores are not read.
- Symlinks are not followed. Files over 512 KB or containing a NUL byte in
  the first 4 KB are counted but not read.
- **The caps bound the walk, not the whole operation.** Storing the items
  and computing gaps happens afterwards and is not timed; on the largest
  example it took about one second.
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
- `actual_undocumented` asks only whether the file name or its stem words
  appear in the docs. `calc.py` is reported for the tiny fixture although its
  behaviour is documented, because the word "calc" is not.

### Map ingest

- Labels are matched as whole words anywhere in a block, case-insensitively,
  so ordinary prose that says "documented" is treated as the label.
- A block that *begins* with a label is taken to be the legend and skipped.
  A real finding written as "Untested: ..." is therefore skipped too.
- Labels are inherited from the nearest heading and from a table's header
  row only; not from an introductory paragraph above a list.
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
- There is no way to delete or rename a project, a knowledge document or a
  work item in v0.
- After independent verification, an initial local commit was made on `main`.
  Claude Code / Fable itself left the tree uncommitted.

## Claude Code sessions

How to resume a particular local Claude Code session is kept in `LOCAL.md`,
which is not committed. That file also holds machine-specific paths. No
`.claude/settings.json` was added: nothing conservative was needed, and
permission bypass must not be the default.
