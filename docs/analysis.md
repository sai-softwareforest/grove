# Grove analysis

An analysis of Grove at commit `3ca2daa` as a software-factory workshop for
Grok Bot and Claude Code, made on 2026-11-12 and 2026-11-13 together with
the survey in `docs/industry-survey.md`.

## Summary

**What was surveyed.** All 671 lists linked from
[sindresorhus/awesome](https://github.com/sindresorhus/awesome) were
classified; 48 were read in full, 803 of their entries judged one by one,
and two primary sources (the MCP specification and the Command Line
Interface Guidelines) read directly. The whole Grove repository was read:
every source file, test, script and document.

**What was found.** Grove's design is sound and its invariants are the right
ones. Running it, not only reading it, turned up four defects that the
documents and the earlier review described as working: a race when several
processes first open a data directory; scan time that grows quadratically
with line length and with paragraph length; a time cap that was checked only
between files; and a byte order mark that hides a file's first line. Beyond
defects, the two largest gaps were that the requirements lived in no single
place, and that nothing enforced the invariants except prose.

**What was changed** (one pull request):

- Documents: `REQUIREMENTS.md`, `docs/blueprint.md`, `docs/work-orders.md`,
  this file, `docs/industry-survey.md`, `CHANGELOG.md`; `CLAUDE.md` rewritten;
  README and `BUILD_NOTES.md` aligned.
- Code, all small and tested: the four defects above fixed; `grove_status`
  reports `home_source` and a `hint`; knowledge can be listed without a
  query; the `grove_recommend_next` description corrected.
- Tests: from 117 to 185, including tests that make the invariants and
  the documents fail the build when they drift.

**The first work orders** (`docs/work-orders.md`): WO-01 to WO-07 are done in
this change. Next are WO-08 (a CI gate; needs the owner's approval), WO-09
(refuse a data directory inside a project), WO-10 (per-project excludes),
WO-11 (verify Grok Bot for real) and WO-12 (lint, types, coverage floor).

**What was not done.** No CI was added. No lint or format change was applied
to the code. Grok Bot was not contacted. No tool was renamed, no result field
removed, no dependency added. The should and later work orders are specified
but not started. Linked websites other than GitHub were not opened (network
policy of the session). Nothing was merged.

## 1. Method

Every statement below is one of three kinds:

- **Tested** — produced by running something in this session; the command or
  test is named. All runs used a temporary data directory.
- **Observed** — read in the code or the documents.
- **Recommend** — a proposal; each one is a work order.

The earlier review of the same commit (by another model, for Grok Bot and
Claude Code fitness) was used as one perspective. Section 5 says where this
analysis agrees with it and where it does not.

## 2. What is already strong

- **One operation table drives both surfaces** (*observed*: `tools.py`,
  `service.py`). Grok Bot and Claude Code get the same behaviour; only the
  argument spelling differs.
- **A predictable envelope with four error codes** (*tested*: `test_cli.py`,
  `test_mcp_stdio.py`). Usage mistakes are envelopes too. Messages say what
  to do next.
- **stdout purity over stdio** (*tested*: `test_mcp_stdio.py` starts a real
  child process). The protocol specification requires exactly this.
- **Scans are read-only, proven by hashing the tree** (*tested*:
  `test_scan_safety.py`).
- **Honesty about truncation** (*tested*: `test_scan_reporting.py`,
  `test_knowledge.py`): capped documents are named, the findings cap reports
  the true total, skipped files are listed, excerpts say they are excerpts.
- **Append-only knowledge with per-scope revisions** (*tested*). Forty
  concurrent writes of one key give revisions 1 to 40.
- **Forward-only migrations with a refusal to downgrade** (*tested*:
  `test_db.py`).
- **Two runtime dependencies, pinned exactly** (*observed*: `pyproject.toml`,
  `uv.lock`).
- **The newest protocol revision already works** (*tested by hand*, section
  3.8).
- **Candour.** `BUILD_NOTES.md` lists what was not verified and where the
  heuristics are weak. That habit is worth more than any single feature and
  the new documents keep it.

## 3. Findings

### 3.1 Four defects found by running the code *(fixed in this change)*

**A. Concurrent first open fails about one time in twenty-five.**
*Tested:* eight threads opening one fresh data directory, 400 runs: 15 runs
failed with `database is locked` at `PRAGMA journal_mode = WAL`
(SQLite 3.53.1). The existing test `test_concurrent_first_open_and_writes`
failed 1 time in 30 plain runs and 1 in 6 under coverage. `BUILD_NOTES.md`
says the suite ran "six times in a row with the same result"; with a
3 to 4 % failure rate that is the likely outcome and proves little.
*Why it matters:* Grok Bot and Claude Code starting together on a new
machine is precisely this case. *Fix:* the switch to WAL is retried within
the busy budget (`db.enable_wal`). *Tested after:* 1500 runs, no failure.

**B. Scan time is quadratic in line length.** *Tested* on the extractors
directly, before the fix:

| Input (one line in a README) | 5 000 chars | 20 000 chars | 40 000 chars |
|---|---|---|---|
| spaces followed by a letter | 0.21 s | 3.4 s | 13.6 s |
| repeated `[` | 0.14 s | 2.3 s | 9.0 s |
| repeated `![` | 0.08 s | 1.3 s | 5.0 s |
| repeated `<` | 0.01 s | 0.16 s | 0.68 s |

A file may be 512 KB, so one line could take tens of minutes. The cause is
ordinary backtracking: the table-separator pattern had two adjacent `\s*`
runs, and the link, image and HTML patterns rescan to the end of the line
from every opener. *Fix:* the table pattern is rewritten to an equivalent
linear form; lines over 5000 characters are not analysed and are reported
(`long_lines`). *Tested after:* each of those inputs at 200 000 characters
completes in milliseconds (`test_scan_robustness.py`).

**C. The time cap was checked only between files.** *Observed* in
`scan_tree`; *tested* with a file of worst-case lines just under the new line
cap: the scan now stops inside the file (`max_seconds=0.2` returns in well
under 3 s; before, the file ran to its end). The MCP server runs each call in
a worker thread that cannot be cancelled, so before the fix a hostile or
merely odd repository could occupy the server far past the cap.

**D. A paragraph of many lines took quadratic time**, in Grove's own Python,
not in a pattern. *Tested:* 20 000 consecutive one-sentence lines took 7.8 s;
after the fix the same input is linear and the reported line numbers are
unchanged (`test_scan_robustness.py`).

**E. A byte order mark hid line 1.** *Tested:* a README starting with a BOM
lost its first heading entirely, and a Python file its first `def`. *Fix:*
files are decoded with the BOM removed; maps are parsed from a BOM-free copy
while the stored knowledge document keeps the file's exact text.

### 3.2 The requirements had no home *(fixed: documents)*

*Observed.* The rules a change must respect were spread over the README,
`BUILD_NOTES.md`, sixteen tool descriptions, one test and a "spec" that is
not in the repository. Examples: "migrations are forward-only" stood only in
a code comment; "optional parameters and new fields are allowed" stood
nowhere; "every tool description must contain 'read-only' and 'GitHub'" was
known only to a test. Contradictions followed: the `grove_recommend_next`
description listed five tiers where the code has six and two more actions;
`BUILD_NOTES.md` showed "117 tests" and "51 passed"; the README listed four
legend headings where the code recognises more; "every command prints
one JSON envelope" ignored `--help`, `--version` and `mcp`.

`REQUIREMENTS.md` now holds every rule once, with an id and a status that
says whether a test guards it. Every requirement marked *open* names the
work order that will close it. `tests/test_docs_contract.py` ties the documents to
the code so the contradictions above cannot quietly return.

### 3.3 Invariants were stated, not enforced

- *Observed, now fixed:* "no network, no model" was prose. `test_invariants.py`
  now fails on any import outside an allow-list, on `eval`, `exec` and
  process calls, and on a layering violation.
- *Tested, open (WO-09):* with the data directory placed inside a project
  root, `project create` and `scan` both succeed and `grove.db` is written
  inside the project. "Grove never writes inside a scanned project" therefore
  depends on configuration, not on Grove.
- *Tested, open (WO-13):* `ingest-map` accepts any readable file up to 2 MB,
  whatever its type, and `knowledge get` returns its text. The agent that
  calls it could usually read the file anyway, but an MCP-only client gains a
  general file reader from a tool named for maps.
- *Observed, open (WO-17):* four caps are silent (500 symbols per file, 40
  names per body, clipped titles and bodies, dropped short sentences), against
  the "never silent" rule.

### 3.4 The data-directory story *(fixed: documents and status)*

*Observed.* The README called `~/.grove` "the usual choice"; `CLAUDE.md` told
agents to `export GROVE_HOME=~/.grove`, which is the default and, for an
agent whose shell calls share no state, does not persist anyway; the README's
Grok Bot registration set no `env`. Two agents following the documents could
each end up in a different, empty workshop and nothing would tell them.

*Now:* one rule (R-HOME-1 to R-HOME-8); `grove_status` says how the directory
was chosen and hints when it is empty (*tested:* `test_status.py`); both
registrations in the README set `GROVE_HOME`; `CLAUDE.md` no longer relies on
`export`.

### 3.5 Work items are too thin for a factory

- *Tested:* two writers of `notes` on one item; the second erases the first.
- *Tested:* every transition is accepted, including `done → ready`. That is
  defensible (Grove records, it does not police), but it was undocumented.
  It is now R-WORK-3, with the assumption recorded.
- *Observed:* a work item has no history (who moved it, when), no acceptance
  criteria, no link to a requirement, a finding, a note or a change, and no
  place for evidence or a reviewer. The `review` status has nothing behind
  it.

For a workshop whose purpose is traceability from requirement to reviewed
change, this is the largest functional gap. *Recommend:* WO-14 (history,
append, optimistic check), then WO-15 (acceptance, links, evidence,
reviewer). Grove would still record and not judge.

### 3.6 Grove scanned by Grove

*Tested* with `grove scan` on this repository:

| | At `3ca2daa` | With this change |
|---|---|---|
| declared items | 128 (README 124, fixture README 4) | 1355 (survey 536, work orders 242, analysis 227, README 175, blueprint 171, fixture 4) |
| actual items | 150 | 157 |
| tests items | 96 | 141 |
| findings (untested / unseen / undocumented) | 6 / 4 / 2 | 54 / 147 / 0 |

Three things follow.

1. **Fixtures count as product.** `fixtures/tiny` contributes declared
   claims, modules and a test, and at `3ca2daa` one of the two
   `actual_undocumented` findings was the fixture's `calc.py`. Any repository with examples or
   vendored code has the same problem. → WO-10.
2. **Non-normative documents flood the declared layer.** The documents added
   by this change sit under `docs/`, so every table row of the survey and
   every sentence of this analysis became a "declared" item: ten times as
   many as before, and 201 findings where there were 12. None of them is a
   product promise. The two undocumented-module findings disappeared only
   because the new documents happen to name every file. → WO-10 (excludes),
   WO-22 (which documents make claims).
3. **The requirements file is invisible.** `REQUIREMENTS.md` matches no
   document pattern, so the one file made only of claims is not read, while
   the survey is. → WO-22, which also proposes that a requirement id named
   in a test counts as a real link, stronger than token overlap.

This is the clearest evidence for the next must-do work order after CI.

### 3.7 Text from strangers reaches the model

*Observed.* Grove stores sentences from scanned READMEs, symbol names, map
text and notes written by other agents, and returns them verbatim inside MCP
tool results. A scanned repository can therefore put words in front of the
agent that reads Grove's output. The survey's security sources name this
channel indirect prompt injection (`docs/industry-survey.md`, section I), and
the MCP specification asks servers to sanitise outputs.

Grove's invariants already remove the worst outcome: it has no outbound
action for injected text to trigger. What is missing is small: say in the
tool descriptions and server instructions that returned text is data; keep
provenance in fields Grove sets (it already has `origin`, `source_path`,
`author`); and decide what to do with characters a person cannot see.
*Recommend:* WO-13. A filtering model is explicitly rejected.

### 3.8 The MCP surface

- *Tested:* the serialised `tools/list` result was 15 102 bytes at `3ca2daa`
  and is 15 817 bytes with this change (the two corrected descriptions
  and the listing note added about 700 bytes). The same 93-character sentence
  ends all sixteen descriptions (1 488 bytes). There is now a tested budget
  of 16 384 bytes; WO-20 proposes to move the repeated sentence into the
  server instructions and lower the budget to 12 KB.
- *Tested:* one page of the declared layer of this repository (128 items at
  `3ca2daa`) is 44 KB. → WO-16.
- *Tested by hand:* `grove mcp` answers `server/discover`, `tools/list` and
  `tools/call` of protocol revision `2026-07-28` with no `initialize`
  handshake. `BUILD_NOTES.md` listed this as not verified. No test covers it
  yet. → WO-25.
- *Tested by hand:* when stdin closes while tool calls are still running,
  their replies are not delivered (two of four pipelined requests were
  lost). Clients that keep the pipe open are unaffected; one-shot scripts are
  not. → WO-25 (document and test).
- *Observed:* an unknown tool name is answered with a `not_found` envelope;
  the specification treats it as a protocol error. This is a recorded
  decision (D-11) and harmless; no change proposed.
- *Observed:* the Grok Bot registration shape has never been tried against
  Grok Bot. → WO-11.

### 3.9 Engineering gates

*Tested*, by running tools without changing the repository:

| Check | Result at `3ca2daa` |
|---|---|
| `uv run pytest -q` | 117 passed (with the intermittent failure of 3.1 A) |
| Branch coverage (`pytest-cov`) | 90 % overall; `cli.py` 81 %, `tools.py` 78 %, `mcp_server.py` 0 % (it runs in a child process) |
| Linter (`ruff check`) | 22 findings, mostly import order |
| Formatter (`ruff format --check`) | 22 of 24 files would change |
| Type checker (`mypy`) | 4 errors, all optional-string narrowing in `service.py` |
| Shell linter (`shellcheck`) | 3 warnings: one unused variable in `scripts/check-publish`, two in the hook |
| Security linter (`bandit`) | 11 medium reports of string-built SQL, 1 low. Each was read: the SQL text comes from fixed fragments and every value is bound |

*Observed:* there is no CI. The only gate is a pre-push hook that each clone
must enable by hand and that checks the tip commit only; the publish script
itself has no tests. *Recommend:* WO-08 (CI, waiting for the owner), WO-12
(static gates in their own change), WO-26 (publish check).

### 3.10 The heuristics have never been measured

*Observed* (`BUILD_NOTES.md`): "I did not measure precision or recall of any
finding kind." One shared token silences a finding, the stemmer is four
suffix rules, and on real projects `declared_untested` is sparse and noisy.
Nobody knows how often a finding is right, so nobody can tell whether a
change to a pattern helps. *Recommend:* WO-23 before any scanner
improvement (WO-35), and D-17 keeps a syntax-tree parser out until then.

### 3.11 Smaller observations

- *Tested:* `gaps --kind` with a misspelt kind returns an empty page with
  `complete: true`. → WO-18.
- *Tested:* `knowledge write --file -` fails with `not_found`. → WO-21.
- *Tested:* with one key in the workspace and in a project,
  `knowledge get KEY` returns the workspace document and does not mention
  the other; a project-scoped search leaves out workspace notes. Both are now
  written down (R-KNOW-3, R-KNOW-7); a hint and an opt-in are WO-19.
- *Observed:* row ids of deleted scan rows can be reused by SQLite, so a
  stored finding id may later point at a different finding, not merely at
  nothing. The tool descriptions do not warn about ids. → WO-20, WO-28.
- *Observed:* the gap pass tests each module name against the whole declared
  text; its cost grows with modules times documentation size and is not
  under the time cap. It took about a second on the largest example in
  `BUILD_NOTES.md`. No change proposed; noted in R-SCAN-8.
- *Observed:* tokenising is ASCII-only and comparison uses lower-casing, not
  case folding or normalisation. → WO-33.
- *Observed:* several patterns are defined twice (`scan.py` and `mapdoc.py`);
  the table-separator fix had to be made in both. A small refactor for
  WO-24.
- *Observed:* there is no backup or export path for `grove.db`. → WO-32.

## 4. Perspective by perspective

| Perspective | Strong | Weak or missing | Adopt | Do not adopt |
|---|---|---|---|---|
| Architecture | One service, one tool table, two thin adapters; pure extractors | The layering was unwritten; patterns duplicated | Layering and import rules as tests (done); decision log (done) | A plugin system; an event bus |
| Requirements quality | Behaviour was documented honestly | No single source, no ids, no statuses | Ids with tested/held/open status (done); definition of done (done) | A heavyweight requirements tool |
| MCP design | Stdio purity, annotations, typed errors, deterministic order | 15.8 KB tool list; ids instability not stated; no output schemas; second protocol era untested | Size budget (done); schema snapshot, structured results (WO-25); leaner descriptions (WO-20) | An HTTP transport; resources or prompts for their own sake |
| CLI design | JSON by default, exit codes, usage errors as envelopes, no prompts | No stdin for bodies; `grove` not on `PATH` outside the repository | `-` for stdin, `--body` (WO-21) | Colour, tables, a new CLI framework |
| Grok Bot ergonomics | Everything reachable over MCP; `author` parameters | Registration unverified; blueprint paging cost; no working loop in the instructions | Verify (WO-11); navigation (WO-16); instructions (WO-20) | Per-client behaviour |
| Claude Code ergonomics | A brief exists and is loaded | It relied on `export`; it said little about changing Grove; nothing for other repositories | Rewritten brief (done); snippet and `.mcp.json` (done); commands in the brief are tested (done) | A long brief that repeats the requirements |
| Data model and migrations | WAL, immediate transactions, forward-only, refusal to downgrade | First-open race (fixed); no schema document (done); one upgrade test | A test per migration; fresh-versus-migrated schema test (WO-12) | An ORM; a migration framework |
| Knowledge and search | Revisions, scopes, excerpts with outlines, safe query quoting | No listing (fixed); no partial read; scope surprises; relevance never tested | Listing (done); sections and scope hints (WO-19); judged queries (WO-23) | Embeddings, vector stores, a search server |
| Work-item workflow | Simple, attributed, paged | Lost updates; no history, links, acceptance, evidence, reviewer | WO-14, WO-15 | Enforced workflows; GitHub synchronisation |
| Scanning and gaps | Read-only, `.gitignore`, caps reported, claim classes | Unbounded line cost (fixed); no excludes; fixtures as product; precision unknown | Excludes (WO-10); measurement (WO-23); property tests (WO-24) | A syntax-tree stack in v0; a model to judge findings |
| Testing and done | 117 tests incl. a real stdio child and tree hashing | One flaky test (fixed); no CI; no property tests; no coverage floor | Fitness tests (done); CI (WO-08); floor (WO-12) | Hosted coverage dashboards |
| Security and supply chain | No network, pinned dependencies, bounded reads, no symlink following | Untrusted text unmarked; home-in-root unenforced; tip-only publish check; no security policy | WO-09, WO-13, WO-26, WO-27 | A guard model; auto-merge of dependency updates |
| Documentation | Honest limits; build record | No requirements, architecture, changelog or contributing files | Added here except contributing and security policy (WO-27) | A generated documentation site |
| Developer experience | `uv sync && uv run pytest -q` is the whole setup | Hook must be enabled by hand; no single check script | `scripts/check` (WO-12) | A hook framework dependency |
| Performance | Streams rows; scans in about a second | Quadratic paths (fixed); gap pass untimed | Line cap and in-file time check (done) | A compiled regex engine |
| Observability | Logs on stderr; scan summary kept on the project | No record of work-item changes | History (WO-14) | Telemetry, metrics export |
| Factory practice | The three-layer idea is itself traceability | Requirement → work order → test → review was not connected anywhere | The chain in `docs/blueprint.md` section 7 (done); links on work items (WO-15); requirement ids in tests (WO-22) | Grove deciding what is done |

## 5. The earlier review: agreement and corrections

The earlier review's main conclusions hold: the requirements were scattered,
the data-directory story was inconsistent, the tool description for
`recommend` was stale, knowledge could not be listed, fixtures pollute a
self-scan, and work-item notes can be lost. Its must-do list is, with one
addition (CI) and three more found here, the must-do list of
`docs/work-orders.md`. Its four questions for the owner are answered with
defaults in `REQUIREMENTS.md`, section 12.

Where this analysis differs:

1. **"Storage is robust when several agents share it. Tested."** Not for the
   first open. The test it cites was itself failing about once in thirty
   runs (3.1 A). The writes were safe; the open was not.
2. **"Safety properties are tested: caps are honoured."** The file cap, yes.
   The time cap was honoured only between files, and line cost was unbounded
   (3.1 B, C). The review read the tests and trusted them; these needed
   inputs the tests did not contain.
3. **"One page of 200 declared items is 44 KB."** The repository had 128
   declared items; a page of 200 returns those 128. The point stands, the
   per-item cost is higher than stated.
4. **"The 98-character suffix ... about 1.6 KB."** Measured: 93 characters,
   1 488 bytes.
5. **Validation of `kind` and path rules as must or should.** Kept at should
   (WO-18): they are tightenings, and R-COMPAT-6 asks for a changelog entry
   and a deliberate step.
6. **Not in the review at all:** the absence of CI; the invariants being
   untested; the data directory inside a project root; `ingest-map` as a
   general file reader; untrusted text reaching the model; the requirements
   file being invisible to Grove's own scan; the state of lint, types and
   coverage; the byte order mark; and that the second protocol era already
   works.
7. **The review's suggestion to put an agent's unfinished work first in
   `recommend`.** Not taken as a default: the order is tested and documented,
   and a non-breaking hint does the job (A2, WO-29).

## 6. Industry practice: what to take and what to leave

Taken up in this change: a single requirements document with ids; an
architecture document with invariants, a source map and a decision log;
tests that enforce architecture rules; documents checked against code; a
changelog; a bound on regular-expression cost; a context budget for tool
descriptions; a definition of done as a short checklist.

Proposed as work orders: CI hardened for a public repository; static gates;
property tests; measured heuristics; structured MCP results; work-item
history and typed links; a threat model that names prompt injection; a
tested publish check over the whole pushed range.

Left alone, by name and with reasons in `docs/industry-survey.md` section 4:
models and embeddings; search servers and vector stores; sync and hosted
dashboards; GitHub automation; autonomous agent loops; syntax-tree parser
stacks; ORMs, CLI frameworks and logging libraries as runtime dependencies;
an HTTP surface; the XDG default directory.

## 7. How to reproduce the measurements

All with a temporary data directory (`export GROVE_HOME="$(mktemp -d)"` in
the same shell call, or `--home`).

| Fact | How |
|---|---|
| Test count and result | `uv run pytest -q` |
| Coverage | `uv run --with pytest-cov pytest -q --cov=sf_grove --cov-branch` |
| First-open race | eight threads calling `sf_grove.db.connect` on one fresh directory, repeated; see `test_many_fresh_homes_survive_a_concurrent_first_open` |
| Line-length cost | call `sf_grove.scan.extract_declared("README.md", line)` with the inputs of 3.1 B; see `test_scan_robustness.py` |
| Tool-list size | `test_the_tool_list_stays_within_its_context_budget` |
| Self-scan | `grove project create grove --root .`, `grove scan grove`, `grove gaps grove` |
| Stateless protocol | send `server/discover`, `tools/list`, `tools/call` with `_meta` carrying `io.modelcontextprotocol/protocolVersion: "2026-07-28"` to `grove mcp`, without `initialize` |
| Lint, types, shell, security | `uvx ruff check src tests`, `uvx ruff format --check src tests`, `uvx mypy --python-version 3.13 --ignore-missing-imports src/sf_grove`, `uvx --from shellcheck-py shellcheck scripts/check-publish .githooks/pre-push`, `uvx bandit -q -r src` |
