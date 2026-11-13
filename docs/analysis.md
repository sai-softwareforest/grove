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
ones. Running it, not only reading it, turned up defects that the documents
and the earlier review described as working: a race when several processes
first open a data directory; scan time that grows quadratically with line
length and with paragraph length; a time cap that was checked only between
files; and a byte order mark that hides a file's first line. Beyond defects,
the two largest gaps were that the requirements lived in no single place,
and that nothing enforced the invariants except prose.

**How the recommendations were filtered.** The survey offered far more than
Grove should take. On the owner's instruction, every candidate change was
argued against before being carried forward: is it the simplest thing that
serves Grove, what does it cost on every call, and what could it break or
make permanent. Section 6 records that argument. Of 35 first-draft work
orders, 3 were dropped, 15 narrowed, 1 redesigned and 2 moved down; several
things already built in this change were taken out again.

**What was changed** (one pull request):

- Documents: `REQUIREMENTS.md`, `docs/blueprint.md`, `docs/work-orders.md`,
  this file, `docs/industry-survey.md`, `CHANGELOG.md`; `CLAUDE.md` rewritten;
  README and `BUILD_NOTES.md` aligned.
- Code, all small and tested: the defects above fixed; `grove_status`
  reports `home_source` and a `hint`; knowledge can be listed without a
  query; the `grove_recommend_next` description corrected.
- Tests: from 117 to 184, including tests that make the invariants and the
  documents fail the build when they drift.

**The first work orders** (`docs/work-orders.md`): WO-01 to WO-07 are done in
this change. Next are WO-08 (a CI gate; needs the owner's approval), WO-09
(refuse a data directory inside a project), WO-10 (per-project excludes) and
WO-11 (verify Grok Bot for real). WO-08, WO-09, WO-10, WO-12, WO-14 and
WO-24 have since been done; see `CHANGELOG.md`.

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
- **Recommend** — a proposal that survived the filter of section 6; each one
  is a work order.

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
- **Restraint and candour.** Grove does four things and says plainly what it
  does not do; `BUILD_NOTES.md` lists what was not verified and where the
  heuristics are weak. Much of this analysis is about keeping that restraint
  while the tool grows.

## 3. Findings

### 3.1 Defects found by running the code *(fixed in this change)*

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

**Is the new line cap safe for ordinary documents?** A cap that protected
against hostile input by dropping real prose would be a bad trade, so it was
checked. *Tested:* in the 1115 Markdown files collected for the survey
(233 179 lines, from 50 unrelated repositories), 115 lines exceed 5000
characters, and every one is generated HTML (type signatures in the MCP
specification); none is prose or a table row. 400 lines exceed 2000
characters, so a tighter cap would have started to cost real text.

### 3.2 The requirements had no home *(fixed: documents)*

*Observed.* The rules a change must respect were spread over the README,
`BUILD_NOTES.md`, sixteen tool descriptions, one test and a "spec" that is
not in the repository. Examples: "migrations are forward-only" stood only in
a code comment; "optional parameters and new fields are allowed" stood
nowhere; "every tool description must contain 'read-only' and 'GitHub'" was
known only to a test. Contradictions followed: the `grove_recommend_next`
description listed five tiers where the code has six and two more actions;
`BUILD_NOTES.md` showed "117 tests" and "51 passed"; the README listed four
legend headings where the code recognises more; "every command prints one
JSON envelope" ignored `--help`, `--version` and `mcp`.

`REQUIREMENTS.md` now holds every rule once, with an id and a status that
says whether a test guards it. Every requirement marked *open* names the
work order that will close it. `tests/test_docs_contract.py` ties the
documents to the code so the contradictions above cannot quietly return.

### 3.3 Invariants were stated, not enforced

- *Observed, now fixed:* "no network, no model" was prose.
  `test_invariants.py` now fails on a network, process or code-loading
  import, on a third-party import outside four named modules, on `eval` and
  `exec`, and on a layering violation.
- *Tested, fixed since (WO-09):* with the data directory placed inside a
  project root, `project create` and `scan` both succeeded and `grove.db`
  was written inside the project. "Grove never writes inside a scanned
  project" depended on configuration, not on Grove. Both now refuse.
- *Tested, fixed since (WO-13):* `ingest-map` accepted any readable file up
  to 2 MB, whatever its type, and `knowledge get` returned its text. It now
  reads map-like file names only (R-SEC-5).
- *Observed, open (WO-17):* more than 500 symbols or tests in one file are
  dropped with no trace, against the "never silent" rule.

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
- *Observed:* a work item has no history (who moved it, when) and no way to
  point at the requirement, note or change it belongs to. The `review`
  status has nothing behind it.

For a workshop whose purpose is traceability from requirement to reviewed
change, this is the largest functional gap. *Recommend:* WO-14, an
append-only history of status changes and progress notes, and WO-15,
free-form references with a filter. Both were cut down hard from their first
drafts (section 6): one new table and four optional parameters in total,
about half of what was first proposed, and no locking.

### 3.6 Grove scanned by Grove

*Tested* with `grove scan` on this repository:

| | At `3ca2daa` | With this change |
|---|---|---|
| declared items | 128 (README 124, fixture README 4) | about 1600 (the survey alone over 500; the rest from work orders, analysis, README, blueprint) |
| actual items | 150 | 157 |
| tests items | 96 | 140 |
| findings (untested / unseen / undocumented) | 6 / 4 / 2 | about 75 / 190 / 0 |

Since WO-10 a project can exclude paths. Scanned with `fixtures/` and the
three non-normative documents excluded, this repository gives 360 declared
items and 31 findings instead of 1613 and 254 (*tested*, 2026-11-13).

Three things followed from the table.

1. **Fixtures count as product.** `fixtures/tiny` contributes declared
   claims, modules and a test, and at `3ca2daa` one of the two
   `actual_undocumented` findings was the fixture's `calc.py`. Any
   repository with examples or vendored code has the same problem. → WO-10.
2. **Non-normative documents flood the declared layer.** The documents added
   by this change sit under `docs/`, so every table row of the survey and
   every sentence of this analysis became a "declared" item: twelve times
   as many as before, and some 270 findings where there were twelve. None
   of them is a product promise. Recording the debates of section 6 made it
   worse, which is the point: more documentation must not mean a worse
   blueprint. → WO-10.
3. **The requirements file is invisible.** `REQUIREMENTS.md` matches no
   document pattern, so the one file made only of claims is not read. The
   tempting fix, reading it, was argued down (WO-22): its table rows would
   each become one long pseudo-sentence, adding more noise. Excludes and
   measurement come first.

### 3.7 Text from strangers reaches the model

*Observed.* Grove stores sentences from scanned READMEs, symbol names, map
text and notes written by other agents, and returns them verbatim inside MCP
tool results. A scanned repository can therefore put words in front of the
agent that reads Grove's output. The survey's security sources name this
channel indirect prompt injection (`docs/industry-survey.md`, section I), and
the MCP specification asks servers to sanitise outputs.

Grove's invariants already remove the worst outcome: it has no outbound
action for injected text to trigger, so the risk sits with the client.
*Recommend* (WO-13), and no more than this: one sentence in the server
instructions that returned text is data, and a file-type restriction on
`ingest-map`. Detecting or escaping hidden characters, trust markers and
filtering models were all considered and left out (section 6).

### 3.8 The MCP surface

- *Tested:* the serialised `tools/list` result was 15 102 bytes at `3ca2daa`
  and is 15 649 bytes with this change. Correct descriptions cost 547 bytes
  in every session; the first draft cost 715 and was shortened. The same
  93-character sentence ends all sixteen descriptions (1 488 bytes). There
  is now a tested budget of 16 384 bytes; WO-20 moves the repeated sentence
  into the server instructions.
- *Tested:* one page of the declared layer of this repository (128 items at
  `3ca2daa`) is 44 KB. → WO-16.
- *Tested by hand:* `grove mcp` answers `server/discover`, `tools/list` and
  `tools/call` of protocol revision `2026-07-28` with no `initialize`
  handshake. `BUILD_NOTES.md` listed this as not verified. No test covers it
  yet. → WO-25.
- *Tested by hand:* when stdin closes while tool calls are still running,
  their replies are not delivered (two of four pipelined requests were
  lost). Clients that keep the pipe open are unaffected. → WO-25 (document).
- *Observed:* an unknown tool name is answered with a `not_found` envelope;
  the specification treats it as a protocol error. This is a recorded
  decision (D-11) and harmless; no change proposed.
- *Observed:* the Grok Bot registration shape has never been tried against
  Grok Bot. → WO-11, which several other orders wait on.

### 3.9 Engineering gates

*Tested*, by running tools without changing the repository:

| Check | Result at `3ca2daa` |
|---|---|
| `uv run pytest -q` | 117 passed (with the intermittent failure of 3.1 A) |
| Branch coverage (`pytest-cov`) | 90 % overall (92 % with this change); `mcp_server.py` is mostly exercised in a child process the tool cannot see |
| Linter (`ruff check`) | 22 findings, mostly import order |
| Formatter (`ruff format --check`) | 22 of 24 files would change |
| Type checker (`mypy`) | 4 reports, all optional-string narrowing in `service.py`; each was read and none is a defect |
| Shell linter (`shellcheck`) | 3 warnings: one unused variable in `scripts/check-publish`, two in the hook |
| Security linter (`bandit`) | 11 medium reports of string-built SQL, 1 low. Each was read: the SQL text comes from fixed fragments and every value is bound |

*Observed:* there is no CI. The only gate is a pre-push hook that each clone
must enable by hand and that checks the tip commit only; the publish script
itself has no tests. *Recommend:* WO-08 (one small CI job, waiting for the
owner) and WO-26 (range check and tests for the publish script). The static
tools above were weighed and mostly declined (WO-12): a linter for
error-class rules, yes; reformatting, a type-checker gate and a coverage
floor, no.

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
  the other. Now written down (R-KNOW-3); the result now names the other
  scopes (`other_scopes`, built in WO-19).
- *Observed:* row ids of deleted scan rows can be reused by SQLite, so a
  stored finding id may later point at a different finding. → WO-20 (say so
  in the instructions), WO-28.
- *Observed:* the gap pass tests each module name against the whole declared
  text; its cost grows with modules times documentation size and is not
  under the time cap. About a second on the largest example in
  `BUILD_NOTES.md`. No change proposed; noted in R-SCAN-8.
- *Observed:* tokenising is ASCII-only. Checked: keys and names are ASCII by
  validation, so no normalisation is needed; the limit is now stated in the
  README, and the proposed text policy was dropped (WO-33).
- *Observed:* several patterns are defined twice (`scan.py`, `mapdoc.py`);
  the table-separator fix had to be made in both. → WO-24.
- *Observed:* there is no documented way to back up `grove.db`. → WO-27 (a
  paragraph). An export command was considered and dropped (WO-32).

## 4. Perspective by perspective

"Adopt" lists only what survived section 6. "Do not adopt" lists what was
considered and declined, from the survey and from the first draft.

| Perspective | Strong | Weak or missing | Adopt | Do not adopt |
|---|---|---|---|---|
| Architecture | One service, one tool table, two thin adapters; pure extractors | The layering was unwritten; patterns duplicated | Layering and import rules as tests (done); decision log (done) | A plugin system; an event bus; one file per decision |
| Requirements quality | Behaviour was documented honestly | No single source, no ids, no statuses | Ids with tested/held/open status (done); definition of done (done) | A requirements tool; typed requirement records |
| MCP design | Stdio purity, annotations, typed errors, deterministic order | 15.6 KB tool list; id instability not stated; second protocol era untested | Size budget (done); protocol test and schema snapshot (WO-25); shared sentence into instructions (WO-20) | HTTP transport; output schemas and structured results for now; `next_offset`; per-tool examples |
| CLI design | JSON by default, exit codes, usage errors as envelopes, no prompts | No stdin for bodies; `grove` not on `PATH` elsewhere | `--file -` (WO-21) | Colour, tables, a CLI framework, `--body` |
| Grok Bot ergonomics | Everything reachable over MCP; `author` parameters | Registration unverified; blueprint paging cost | Verify first (WO-11); summary and path filter (WO-16) | Per-client behaviour; a second result shape |
| Claude Code ergonomics | A brief exists and is loaded | It relied on `export`; nothing for other repositories | Rewritten brief, README snippet, tested commands (all done) | A long brief; an `AGENTS.md` without evidence it is read |
| Data model and migrations | WAL, immediate transactions, forward-only, refusal to downgrade | First-open race (fixed); no schema document (done) | A fresh-versus-migrated schema test with the next migration (WO-10) | An ORM; a migration framework |
| Knowledge and search | Revisions, scopes, excerpts with outlines, safe query quoting | No listing (fixed); scope surprise; relevance never tested | Listing (done); `other_scopes`, `from_line` (WO-19); judged queries (WO-23) | Embeddings, vector stores, a search server; a second size parameter |
| Work-item workflow | Simple, attributed, paged | Lost updates; no history; no references | History (WO-14); references (WO-15) | Enforced workflows; locks; evidence and reviewer fields; GitHub synchronisation |
| Scanning and gaps | Read-only, `.gitignore`, caps reported, claim classes | Unbounded line cost (fixed); no excludes; precision unknown | Excludes (WO-10); measurement (WO-23); randomised tests (WO-24) | A syntax-tree stack; a model to judge findings; default skip lists; ingesting test results |
| Testing and done | 117 tests incl. a real stdio child and tree hashing | One flaky test (fixed); no CI | Fitness tests (done); one CI job (WO-08) | Coverage gates and dashboards; a property-testing dependency for now |
| Security and supply chain | No network, pinned dependencies, bounded reads, no symlink following | Home-in-root unenforced; tip-only publish check; no security policy | WO-09, WO-13, WO-26, WO-27 | A guard model; hidden-character scanning; a second secret scanner; auto-merge |
| Documentation | Honest limits; build record | No requirements, architecture or changelog | Added here; a security policy (WO-27) | A documentation site; a contributing guide that copies the brief |
| Developer experience | `uv sync && uv run pytest -q` is the whole setup | Hook enabled by hand; no single check script | `scripts/check` with an error-only linter (WO-12) | Mass reformatting; a type-checker gate; a hook framework |
| Performance | Streams rows; scans in about a second | Quadratic paths (fixed) | Line cap and in-file time check (done) | A compiled regex engine |
| Observability | Logs on stderr; scan summary kept on the project | No record of work-item changes | History (WO-14) | Telemetry, metrics export |
| Factory practice | The three-layer idea is itself traceability | Requirement → work order → test → review was not connected | The chain in `docs/blueprint.md` section 7 (done); references on work items (WO-15) | Grove deciding what is done; warnings when an item closes without evidence |

## 5. The earlier review: agreement and corrections

The earlier review's main conclusions hold: the requirements were scattered,
the data-directory story was inconsistent, the tool description for
`recommend` was stale, knowledge could not be listed, fixtures pollute a
self-scan, and work-item notes can be lost. Its four questions for the owner
are answered with defaults in `REQUIREMENTS.md`, section 12.

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
5. **Not in the review at all:** the absence of CI; the invariants being
   untested; the data directory inside a project root; `ingest-map` as a
   general file reader; untrusted text reaching the model; the requirements
   file being invisible to Grove's own scan; the byte order mark; and that
   the second protocol era already works.
6. **Several of its recommendations did not survive the filter**, though
   each addresses something real: `append_notes` and an expected-timestamp
   check (replaced by an append-only history, WO-14); `--body` (stdin
   suffices, WO-21); a `class` filter and a compact switch on the blueprint
   (WO-16); a section parameter by title (WO-19); `next_offset` and compact
   project rows (WO-20); structured results (WO-25); requiring absolute
   paths (WO-18); reporting every small clip (WO-17); and putting unfinished
   work first in `recommend` (A2, WO-29). The reasons are in each order's
   debate.

## 6. The filter: what was argued, kept and cut

The survey and the first draft of the work orders both leaned towards "this
exists and could be added". The owner's instruction of 2026-11-13 was to
filter with judgement: debate each change as an expert engineer would,
weighing parsimony, efficiency and unintended consequences, carry forward
only what still looks wise, and record why the rest was left out. Three
questions were put to every candidate:

1. Is it the simplest thing that actually serves Grove? Can the need be met
   with no new parameter, field, table or dependency?
2. What does it cost on every call or in every session, and for whom?
3. What does it break, or make permanent? Under the compatibility policy
   nothing added can be removed, so every new field is a lasting commitment.

### 6.1 Applied to what this change had already built

| Built first | After the argument | Why |
|---|---|---|
| A `mode` field on every search and listing result | Removed | `query: null` already says it is a listing; a result field is permanent |
| `max_line_chars` reported under `caps` and under `long_lines` | Reported once, in `long_lines` | The same number twice |
| An allow-list of every standard-library module `sf_grove` may import | Replaced by a forbidden list (network, process, code loading) plus an allow-list of the four third-party modules | The invariant is "no network, no model", not "no `hashlib`"; a test people edit mechanically stops meaning anything |
| Longer descriptions for three tools (+715 bytes in every session) | Shortened (+547 bytes) | Correctness is worth bytes; padding is not |
| Tests that parsed the CLI through argparse internals, and string-presence checks on the documents | Removed or simplified | Brittle against Python versions; proved little |
| A line cap of 5000 characters | Kept, after checking it against 233 179 real Markdown lines (3.1) | The only way to bound an uninterruptible line; costs no real prose |

### 6.2 Applied to the work orders

| Candidate | Outcome | The deciding argument |
|---|---|---|
| Reformat the code; type-checker gate; typed dictionaries; coverage floor; spelling check (WO-12) | Cut | Churn in 22 of 24 files and permanent blame noise for no behaviour change; the four type reports are not defects; a coverage number invites tests written for the number |
| Count or escape invisible characters in results; trust markers; a guard model (WO-13) | Cut | Grove has no outbound action, so the risk is the client's; a new field on six tools; markers can be forged by the text; a model breaks an invariant |
| `append_notes`, an expected-timestamp check, claiming an item (WO-14) | Replaced by one append-only history | An append-only log removes the conflict the other mechanisms manage; locks outlive dead sessions |
| `acceptance`, `evidence`, `reviewer`, typed links, a warning on closing (WO-15) | Cut to free-form `refs` | Plan text, a history note and its author already carry these; Grove records and does not nag |
| `class` filter, compact switch (WO-16) | Cut | Summary plus path filter cover the walk; a second result shape taxes every client |
| Counters for clipped titles, bodies and short sentences (WO-17) | Cut | Clipping is already visible in the text; the rest is an extraction rule, not a cap |
| Reject relative paths; `resolved_from` (WO-18) | Cut | Results already echo the absolute path |
| `section` by title; `offset` with `max_chars`; `include_workspace` (WO-19) | Cut to `from_line` | Reuses the outline and the excerpt size; one integer |
| Compact project rows; `next_offset`; `idempotentHint`; an example per tool (WO-20) | Cut | Removing a field is forbidden; the others add bytes or fields for no known client need |
| `--body`; an `AGENTS.md` (WO-21) | Cut | Stdin covers it; a second brief only if Grok Bot is shown to read one |
| Read `REQUIREMENTS*` and `SPEC*` files into the declared layer (WO-22) | Deferred | Would add noise today; needs excludes and measurement first |
| A property-testing library; a corpus of awkward strings; a Markdown parser as oracle (WO-24) | Cut to a seeded generator in the standard library | Enough to find defects of the kind found here; a dependency must be earned |
| `structuredContent` and `outputSchema` on every tool; a CLI-versus-MCP differential test (WO-25) | Cut | Grows `tools/list` and doubles result payloads with no shown need; the two paths share one wrapper |
| A second secret scanner; a bidirectional-character check (WO-26) | Cut | Another tool to keep in step, for patterns the script already has; no incident |
| A contributing guide; a release checklist; a commit convention (WO-27) | Cut to a security policy | Copies of rules that already have a home; nothing consumes the convention |
| Waivers for findings (WO-28) | Cut | A second state machine; a closed work item says the same |
| Ingest test results (WO-31) | Left out | Results go stale at the next edit; a parser for untrusted files; the agent can run the tests |
| An export command (WO-32) | Left out | A CLI-only operation breaks "both surfaces"; `knowledge get --full` already reads everything |
| A Unicode and case policy (WO-33) | Left out | Keys, names and tokens are ASCII by construction; one README sentence was the whole gap |
| A CI matrix, lint job, coverage upload, audit schedule (WO-08) | Cut to one job | The smallest gate that is not the author's machine |
| A `.groveignore` file; default skip lists; excludes set in two places (WO-10) | Cut to one stored list set through `grove_scan` | Agents must not write in the project; default skips hide real code silently; one way to set a thing |

### 6.3 What the filter did not remove

Everything measured as broken stayed: the first-open race, the scan bounds,
the byte order mark, the wrong tool description. So did the orders with
evidence behind them: excludes (a twelvefold flood, measured), the data
directory guard (reproduced), verification against Grok Bot (never done),
measurement of the heuristics (never done), and a history for work items
(lost update reproduced). The pattern is the instruction itself: evidence
keeps an item; "it would be nice" does not.

## 7. Industry practice: what was taken and what was left

Taken up in this change: a single requirements document with ids; an
architecture document with invariants, a source map and a decision log;
tests that enforce architecture rules; documents checked against code; a
changelog; a bound on regular-expression cost; a context budget for tool
descriptions; a definition of done as a short checklist.

Proposed as work orders: one CI job hardened for a public repository;
measured heuristics; an append-only work history; a tested publish check
over the whole pushed range; a short security policy that names prompt
injection.

Left alone, with reasons in `docs/industry-survey.md` section 4 and in
section 6 above: models and embeddings; search servers and vector stores;
sync and hosted dashboards; GitHub automation; autonomous agent loops;
syntax-tree parser stacks; ORMs, CLI frameworks and logging libraries as
runtime dependencies; an HTTP surface; the XDG default directory; and, from
the first draft of this analysis, structured MCP results, typed work-item
links, property-testing and formatting tools, and a text-normalisation
policy.

## 8. How to reproduce the measurements

All with a temporary data directory (`export GROVE_HOME="$(mktemp -d)"` in
the same shell call, or `--home`).

| Fact | How |
|---|---|
| Test count and result | `uv run pytest -q` |
| Coverage | `uv run --with pytest-cov pytest -q --cov=sf_grove --cov-branch` |
| First-open race | eight threads calling `sf_grove.db.connect` on one fresh directory, repeated; see `test_many_fresh_homes_survive_a_concurrent_first_open` |
| Line-length cost | call `sf_grove.scan.extract_declared("README.md", line)` with the inputs of 3.1 B; see `test_scan_robustness.py` |
| Long lines in real Markdown | count lines longer than 5000 characters in any collection of Markdown files |
| Tool-list size | `test_the_tool_list_stays_within_its_context_budget` |
| Self-scan | `grove project create grove --root .`, `grove scan grove`, `grove gaps grove` |
| Stateless protocol | send `server/discover`, `tools/list`, `tools/call` with `_meta` carrying `io.modelcontextprotocol/protocolVersion: "2026-07-28"` to `grove mcp`, without `initialize` |
| Lint, types, shell, security | `uvx ruff check src tests`, `uvx ruff format --check src tests`, `uvx mypy --python-version 3.13 --ignore-missing-imports src/sf_grove`, `uvx --from shellcheck-py shellcheck scripts/check-publish .githooks/pre-push`, `uvx bandit -q -r src` |
