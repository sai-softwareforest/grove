# Grove

Grove is Software Forest's open-source workshop for coding agents. It runs on
your own machine and does four things:

1. **Maps a codebase.** A read-only scan walks a project directory and records
   what it finds.
2. **Keeps a three-layer blueprint** of that project:
   - `declared` — what the docs say (headings and sentences from README,
     CHANGELOG and `docs/`),
   - `actual` — what the code appears to contain (modules and symbol names),
   - `tests` — what the tests appear to prove (test files and test names).

   Where the layers disagree, Grove records a *finding*, for example "the README
   says it greets a user by name, and no test mentions greeting".
3. **Stores lasting knowledge.** Notes and ingested architecture maps are kept
   with full revision history and are full-text searchable.
4. **Tracks local work items** from `ready` through `in_progress` and `review`
   to `done`.

Agents such as Grok Bot and Claude Code do the work. Grove is the workshop
they use: a place to look things up, see what is unproven, and keep track.

## What Grove is not

- **Not an autonomous coder.** It never edits your code, and it does not
  implement changes.
- **It does not open pull requests.** It does not talk to GitHub or to any other
  network service. An issue URL on a work item is stored as text and never
  fetched.
- **Not an AI.** v0 calls no model and no embeddings API. Everything is
  deterministic: regular expressions, token overlap and SQLite.
- **Not a judge.** Every finding is labelled `heuristic`. Treat findings as
  places to look, then read the code.

## Install

```sh
uv sync
```

This creates `.venv/` with the `grove` command at `.venv/bin/grove`. Requires
Python 3.13 and [uv](https://docs.astral.sh/uv/). Dependencies are pinned in
`pyproject.toml` and `uv.lock`.

Run the tests with `uv run pytest -q`.

## Data directory and `GROVE_HOME`

Grove keeps everything in one SQLite file, `grove.db`, inside its data
directory:

1. `--home DIR` on the command line, if given;
2. otherwise the `GROVE_HOME` environment variable, if set;
3. otherwise `~/.grove`.

The directory is created on first use. The usual choice is the default,
`~/.grove`. You can point `GROVE_HOME` at another directory if you prefer.

Grove writes only inside its data directory. Keep the data directory outside
the projects you scan.

## A first walk

The repository ships a tiny pretend project in `fixtures/tiny`. Its README
claims two behaviours (adding two integers, greeting a user by name); both are
implemented, and only the first has a test.

```sh
alias grove=.venv/bin/grove      # or: uv run grove

grove project create tiny --root fixtures/tiny
grove scan tiny
grove gaps tiny --text
grove recommend tiny --text
```

`grove gaps tiny --text` prints:

```
items:
  - 1 declared_untested No test name overlaps this declared statement: "Greets a user by name." (README.md:6)
  - 2 actual_undocumented Module src/tiny/calc.py is not mentioned in the declared layer
total: 2
```

and `grove recommend tiny` points at finding 1: the greeting behaviour exists
in the code and nothing tests it.

## CLI

Every command prints one JSON envelope on stdout and exits `0` on success or
`1` on error. Add `--text` for a plain-text rendering.

```
grove --home DIR status
grove --home DIR project create NAME --root PATH
grove --home DIR project list
grove --home DIR project get NAME
grove --home DIR scan NAME [--max-files N] [--max-seconds S]
grove --home DIR blueprint NAME [--layer declared|actual|tests] [--query TEXT]
grove --home DIR gaps NAME [--kind KIND]
grove --home DIR ingest-map NAME PATH
grove --home DIR knowledge write NAME --key KEY --title TITLE --file PATH
grove --home DIR knowledge get KEY [--project NAME] [--revision N]
grove --home DIR search QUERY [--project NAME]
grove --home DIR work create NAME --title TITLE [--issue URL] [--plan TEXT]
grove --home DIR work list NAME [--status STATUS]
grove --home DIR work get ID
grove --home DIR work update ID [--status STATUS] [--plan TEXT] [--notes TEXT] [--title TEXT]
grove --home DIR recommend NAME
grove mcp
```

`--home DIR` is optional and wins over `GROVE_HOME`. List commands accept
`--limit` (default 50, maximum 200) and `--offset`. For `knowledge write`, use
`-` as NAME to write a workspace-level note that belongs to no project.

More examples:

```sh
grove blueprint tiny --layer actual --text
grove ingest-map tiny fixtures/map_sample.md
grove gaps tiny --kind map_untested
grove knowledge write tiny --key greet-plan --title "Greet test plan" --file notes.md
grove search "greet plan"
grove work create tiny --title "Add a test for greet"
grove work update 1 --status in_progress
```

### The JSON envelope

```json
{"ok": true, "data": {"...": "..."}}
{"ok": false, "error": {"code": "not_found", "message": "..."}}
{"ok": true, "data": {"items": [], "total": 0, "offset": 0, "limit": 50}}
```

Error codes are `not_found`, `invalid`, `io` and `internal`. Usage mistakes
(an unknown command, a missing argument) are reported as `invalid` too.

## MCP server

`grove mcp` serves the same operations to an agent over MCP stdio. stdout
carries MCP JSON-RPC only; logs go to stderr. It offers exactly sixteen tools:

`grove_status`, `grove_project_create`, `grove_project_list`,
`grove_project_get`, `grove_scan`, `grove_blueprint_get`, `grove_gaps`,
`grove_ingest_map`, `grove_knowledge_write`, `grove_knowledge_get`,
`grove_knowledge_search`, `grove_work_create`, `grove_work_list`,
`grove_work_get`, `grove_work_update`, `grove_recommend_next`.

Each tool result is the JSON envelope above, as one text block; `isError` is
set when `ok` is false.

### Grok Bot

Add Grove as a **local** (stdio) server with AddMcpServer. Replace
`/path/to/grove` with the directory where you cloned this repository.
`env` is optional; without it Grove uses `~/.grove`.

```json
{
  "name": "grove",
  "command": "uv",
  "args": ["run", "--quiet", "--project", "/path/to/grove", "grove", "mcp"]
}
```

If you would rather point at the virtualenv directly, set `command` to
`/path/to/grove/.venv/bin/grove` and `args` to `["mcp"]`.

A remote URL will not work for this server. Grove speaks MCP over stdio only:
the agent must start the process itself, on the machine that holds the code
and the data directory. There is no HTTP endpoint to connect to.

### Claude Code and other MCP clients

Any client that launches stdio servers can use the same `command`, `args` and
`env`. See `CLAUDE.md` for how Claude Code is expected to use Grove.

## Honest limits

**The scanner is not a parser.** It reads one line at a time with
language-specific regular expressions.

- Languages: Python, Rust, TypeScript/JavaScript and Go. Other languages are
  counted as files and otherwise ignored.
- Text inside a string or block comment that looks like a definition is
  recorded as one. Definitions split across lines can be missed. Class methods
  in TypeScript/JavaScript and types inside a Go `type ( ... )` block are not
  recorded.
- Test names come from pytest-style functions and classes, Rust `#[test]`
  attributes and `fn test_*`, JavaScript `test(`/`it(` calls with a literal
  name, and Go `func Test*`. Test *bodies* are not read: Grove knows a test's
  name, not what it asserts.
- Docs are read as Markdown: headings and sentences, with code fences, badges
  and licence text skipped. At most 400 items are kept per document.
- The scan honours `.gitignore` files (a deeper file cannot re-include what a
  shallower one ignored), always skips `.git`, `node_modules`, `target`,
  `venv`, `.venv`, `dist`, `build`, `__pycache__`, `.mypy_cache` and
  `.pytest_cache`, does not follow symlinks, and skips files over 512 KB.
- Caps: 4000 files and 8 seconds by default. When a cap is hit the scan stops,
  keeps what it has, and says so in the result and on the project.

**The gap heuristic is token overlap, nothing more.** Words are lower-cased,
split on punctuation and camelCase, stripped of a few English suffixes and
compared as sets.

Before comparing, each declared sentence gets a `class` by fixed rules, first
match wins (see `src/sf_grove/claims.py`):

1. `prose`: a lead-in ending with ":", or a fragment of six words or fewer
   with no verb-like word ("Not a judge.").
2. `limit`: under a heading about limits, caveats or known issues, or phrased
   as "can be missed" / "not supported".
3. `behaviour`: promise words such as never, always, must, only, does not,
   will not, cannot, "no" plus a noun, refuses or rejects.
4. `prose`: positioning in the form "Name is a/the/someone's ...".
5. `setup`: under an Install, Setup, Requirements, Development, Testing or
   Examples heading; starts with an instruction verb ("Run", "Install",
   "See"); or names a path, file name, version number or dependency.
6. `behaviour`: everything else.

`setup` and `prose` sentences produce no finding. They stay in the declared
blueprint with `extra.class` and `extra.class_reason`, and the scan's
`gap_notes.declared_skipped` counts them. Every declared finding carries
`evidence.class` and `evidence.class_reason`. `limit` findings are listed
after `behaviour` findings and their summary starts with `[limit]`.

- `declared_untested`: a `behaviour` or `limit` sentence shares *no* word with
  any test name or test file name. One shared word is enough to stay silent,
  so on a large project with many tests this finds little.
- `declared_unseen`: the same comparison against module paths and symbol names.
- `actual_undocumented`: a module whose file name is not mentioned in the
  docs; at most 25 per scan, shallowest paths first.
- `map_untested`: a block of an ingested map that carries the label `untested`.
  This is the map author's statement, copied; Grove did not check it.

A finding is a reason to go and read, not a result. `grove recommend` ranks by
fixed rules, not by understanding: `map_untested`, then untested `behaviour`
seen in code, then other untested `behaviour`, then the oldest ready work
item, then an untested `limit`, then `actual_undocumented`. The classes are
word rules, not grammar: a real promise with no promise word can land in
`setup` because it names a path, and an install note that uses "never" stays
`behaviour`.

**Map ingest is simple.** It recognises the labels `documented`,
`observed-in-code` and `untested` in paragraphs, list items and table rows.
See `BUILD_NOTES.md` for what it misses.

## Licence

MIT; see `LICENSE`. Grove is a Software Forest project. It is not affiliated
with, endorsed by, or derived from any other product or company.
