# Grove work orders

The orders for upgrading Grove as a software-factory workshop, in priority
order. Each order names the requirements it makes true (`REQUIREMENTS.md`),
where the need comes from (`docs/analysis.md`, `docs/industry-survey.md`),
and how to tell it is done. The definition of done in `REQUIREMENTS.md`,
section 11, applies to every order and is not repeated.

## How these orders were filtered

The survey produced far more suggestions than Grove should take. On the
owner's instruction (2026-11-13), every candidate was argued against before
it was written down, the way an engineer would argue in review, on three
questions:

1. **Parsimony.** Is this the simplest thing that actually serves Grove? Is
   there a way to meet the need with no new parameter, field, table or
   dependency?
2. **Efficiency.** What does it cost on every call or in every session
   (bytes of tool description, bytes of result, scan time), and for whom?
3. **Unintended consequences.** What breaks, drifts or becomes permanent?
   Under the compatibility policy a new field or parameter can never be
   removed, so "it is only additive" is a cost, not an excuse.

A resource existing is not a reason. Only what still looked wise after the
argument is an order. Each order below carries its **Debate**: what was
considered, what was cut, and why. Orders that did not survive keep their id
and are marked *left out*, so a later reader can see they were weighed and
does not propose them again without new evidence.

The first version of this list had 35 orders. After the filter: 3 are left
out entirely, 15 are narrower, 1 was redesigned, 2 moved down in priority,
and several things already built in this change were removed again (see
WO-03, WO-04, WO-06, WO-07).

## Priorities and status

- **Must** — before more feature work.
- **Should** — makes Grove good at its job for Grok Bot and Claude Code.
- **Later** — worth doing, not yet urgent, or waiting for evidence or a
  decision.

Sizing rule: one order is one reviewable change.

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
| WO-12 | A linter and one check script | should | code | open (narrowed) |
| WO-13 | Untrusted text: say so, and narrow map ingest | should | both | open (narrowed) |
| WO-14 | Work-item history | should | both | open (redesigned) |
| WO-15 | References on work items | should | both | open (narrowed) |
| WO-16 | Cheap blueprint navigation | should | both | open (narrowed) |
| WO-17 | Report the symbols cap | should | both | open (narrowed) |
| WO-18 | Validate `kind` | should | both | open (narrowed) |
| WO-19 | Knowledge: other scopes, read from a line | should | both | open (narrowed) |
| WO-20 | A leaner, more instructive MCP surface | should | both | open (narrowed) |
| WO-21 | CLI ergonomics for agents | should | both | open (narrowed) |
| WO-22 | Explicit requirement ids as a trace | later | both | open (narrowed, moved down) |
| WO-23 | Measure the heuristics and the search | should | code | open |
| WO-24 | Randomised tests for the parsers | should | code | open (narrowed) |
| WO-25 | Protocol coverage | should | code | open (narrowed) |
| WO-26 | Harden and test the publish check | should | code | open (narrowed) |
| WO-27 | A security policy | should | docs | waiting (contact address) |
| WO-28 | Stable finding keys | later | both | open (narrowed) |
| WO-29 | Unfinished work in `recommend` | later | both | waiting (A2) |
| WO-30 | Archive without deleting | later | both | waiting (A3) |
| WO-31 | Test results in the tests layer | — | — | left out |
| WO-32 | Export command | — | — | left out |
| WO-33 | Unicode and case policy | — | — | left out |
| WO-34 | Verify macOS and Windows | later | verification | open |
| WO-35 | Scanner precision, measured | later | code | open |

## Must

### WO-01 — Requirements, blueprint and decision log in the repository *(done)*

- **Goal.** One document to implement against, one to understand the
  structure, one list of decisions.
- **Rationale.** The rules for changing Grove were spread over README,
  `BUILD_NOTES.md`, tool descriptions, one test and a spec outside the
  repository (analysis 3.2).
- **Acceptance.** `REQUIREMENTS.md` with stable ids and a status per
  requirement; `docs/blueprint.md` with module map, data model, operation
  map, traceability and decision log; README, `CLAUDE.md` and
  `BUILD_NOTES.md` contradict none of it; a test ties the documents to the
  code.
- **Debate.** Kept to three documents. *Cut:* one file per decision (a table
  is enough at this size); a separate architecture-template structure; a
  contributing guide (it would be a third copy of `CLAUDE.md` and section 11).
  The risk taken knowingly: five Markdown files under `docs/` now pollute
  Grove's scan of itself, which is the evidence for WO-10.
- **Kind.** docs (+ `tests/test_docs_contract.py`).

### WO-02 — One data-directory rule, and a status that shows it *(done)*

- **Goal.** No agent works in an empty `~/.grove` by accident.
- **Rationale.** R-HOME-2, R-HOME-3, R-HOME-6 (analysis 3.4).
- **Acceptance.** `grove_status` returns `home_source` and a `hint` when the
  directory has no projects; both registrations in the README set
  `GROVE_HOME`; `CLAUDE.md` does not rely on `export`.
- **Debate.** Two fields, on the one call an agent makes first; the hint is
  present only when the directory is empty, so it costs nothing in normal
  use. *Cut:* a warning on every tool result (cost on every call); a config
  file for the home (a second source of truth beside flag and variable);
  moving the default to the XDG layout (breaks every existing setup).
- **Kind.** both. Tests: `tests/test_status.py`.

### WO-03 — Tool descriptions as a tested contract *(done)*

- **Goal.** What an MCP client reads about a tool is true.
- **Rationale.** R-GROK-2, R-GROK-3, R-REC-1. The `grove_recommend_next`
  description listed five tiers; the code has six and two more actions.
- **Acceptance.** The description names every action in
  `service.RECOMMEND_ACTIONS` in order; a test fails if one is missing; the
  `tools/list` payload has a tested size budget.
- **Debate.** Correct descriptions cost bytes in every session: this change
  took `tools/list` from 15 102 to 15 649 bytes. The first draft added 715;
  the additions were then shortened. Accepted because a wrong description
  costs more than a longer one, and WO-20 recovers about 1.5 KB. *Cut:* a
  linter for natural-language instructions (a dependency to check sixteen
  strings that one focused test covers).
- **Kind.** both. Tests: `tests/test_docs_contract.py`.

### WO-04 — List knowledge without a query *(done)*

- **Goal.** An agent can see what is known without inventing a search.
- **Rationale.** R-KNOW-6. `search "*"` was an error and there was no list.
- **Acceptance.** `grove_knowledge_search` and `grove search` without a query
  return the latest revision of every document, newest first, without
  bodies, with `body_chars`; a project filter and paging work; an empty
  query string is still `invalid`.
- **Debate.** Done inside the existing tool (the sixteen names are frozen),
  by making one parameter optional. *Cut after it was built:* a `mode` field
  on every search result. `query: null` already says it is a listing, and a
  result field can never be removed once shipped.
- **Kind.** both. Tests: `tests/test_knowledge.py`.

### WO-05 — Reliable concurrent first open *(done)*

- **Goal.** Two agents starting on a fresh data directory never see
  "database is locked".
- **Rationale.** R-HOME-8, R-QUAL-1. Measured: 15 of 400 concurrent first
  opens failed (analysis 3.1 A).
- **Acceptance.** The switch to WAL is retried within the busy budget; a
  deterministic test of the retry; a stress test; 1500 stress runs without a
  failure.
- **Debate.** Fifteen lines, no new state. *Cut:* a lock file (new failure
  modes: stale locks); skipping the pragma when the mode is already WAL (an
  optimisation that still leaves the race at creation). Consequence
  accepted: a truly stuck database now fails after up to 5 seconds instead
  of at once.
- **Kind.** code. Tests: `tests/test_db.py`.

### WO-06 — Scan time bounded by input size *(done)*

- **Goal.** No file can make a scan run far past its time cap.
- **Rationale.** R-SCAN-7, R-SCAN-8, R-INV-11. Measured: one 40 000-character
  line took 13.6 s, growing quadratically (analysis 3.1 B to E).
- **Acceptance.** The table-separator pattern is linear; lines over 5000
  characters are skipped and reported; the time cap is checked between
  lines; the paragraph line lookup is linear; a byte order mark no longer
  hides line 1; tests cover each.
- **Debate.** This is the one place a new cap was added, so it was argued
  hardest.
  - *Why a cap at all:* a single line cannot be interrupted, so only a
    length limit bounds it.
  - *Why 5000:* checked against 1115 real Markdown files (233 179 lines)
    collected for the survey: 115 lines exceed 5000 characters and every
    one is generated HTML; none is prose. A 2000 cap would have skipped 400
    lines. The cost of the cap on real text is therefore close to nothing,
    and it is reported when it applies.
  - *Why also a time check between lines:* the cap alone leaves an
    estimated worst case of about 14 s for one hostile file; with the check the overrun is
    one line (about 0.14 s).
  - *Cut:* a linear-time regex engine (a compiled dependency); rewriting
    the link and image patterns with bounded repeats (changes what ordinary
    documents yield, for the sake of hostile ones); a second copy of
    `max_line_chars` under `caps` (built, then removed: it is reported once,
    in `long_lines`).
- **Kind.** both. Tests: `tests/test_scan_robustness.py`.

### WO-07 — Invariants as fitness tests *(done)*

- **Goal.** A change that adds a network call, a model, a subprocess or a
  layering violation fails the suite.
- **Rationale.** R-INV-1, R-INV-2, R-INV-3, R-QUAL-2, R-QUAL-3, R-SEC-1,
  R-COMPAT-4. The invariants were prose only.
- **Acceptance.** Third-party imports restricted to an allow-list of four,
  each to one module; network, process and code-loading modules of the
  standard library forbidden; layering table tested; no `eval`/`exec`; error
  codes closed; ordinary commands do not load the MCP SDK; two scans of the
  same tree give identical results.
- **Debate.** Standard-library tests, no lint dependency. *Cut after it was
  built:* an allow-list of every standard-library module. It would have made
  a harmless `import hashlib` fail, and a test that people learn to edit
  mechanically stops meaning anything. The test now forbids what the
  invariants forbid and nothing else.
- **Kind.** code. Tests: `tests/test_invariants.py`.

### WO-08 — An automated gate for every change (CI) *(waiting: A8)*

- **Goal.** Every pull request is tested on a clean machine.
- **Rationale.** R-QUAL-9. The only gate is a local hook each clone must
  enable by hand. This session found a test that failed one run in thirty;
  a clean, repeated run is how that gets noticed.
- **Acceptance.**
  1. One workflow, one job, triggered by `pull_request` and by pushes to
     `main`, never by `pull_request_target`.
  2. `permissions: contents: read`; no secrets.
  3. Steps: check out; install uv; `uv sync --locked`; `uv run pytest -q`;
     `scripts/check-publish` on the head commit.
  4. Actions pinned to a full commit SHA; first-party actions plus the uv
     installer only.
  5. No value from the pull request is interpolated into a script.
- **Debate.** The smallest gate that is not the author's machine. *Cut:* an
  operating-system matrix (until WO-34 is wanted); a lint job (until WO-12);
  coverage upload to a hosted service (no network products around a
  local-only tool, and a number invites tests written for the number);
  scheduled dependency audits and auto-merge bots (they bypass the review
  the factory exists to keep); a required workflow linter (for twenty lines,
  reading it against rules 1 to 5 is enough).
- **Kind.** infrastructure. **Needs the owner.**

### WO-09 — Refuse a data directory inside a project root *(open)*

- **Goal.** "Grove never writes inside a scanned project" holds even when the
  home is misconfigured.
- **Rationale.** R-HOME-4, R-INV-4. Tested: with the home inside the root,
  `grove.db` is written inside the project (analysis 3.3).
- **Acceptance.** `project_create` and `scan` return `invalid` when the
  resolved data directory is the project root or inside it; the message
  names both paths and the remedy; paths are compared after resolving
  symlinks; tests for both. Projects already registered that way keep their
  data and can be read; only scanning is refused.
- **Debate.** A few lines that turn a documented rule into a guarantee.
  *Cut:* having the scan silently skip the data directory instead (the write
  inside the project would still happen); a warning instead of an error (an
  invariant that only warns is not one). Consequence weighed: someone who
  registered their whole home directory as a project will get an error; that
  registration was already a mistake, and the error says how to fix it.
- **Kind.** both (a tightening under R-COMPAT-6).

### WO-10 — Per-project scan excludes *(open)*

- **Goal.** Fixtures, examples, vendored code and non-normative documents stay
  out of a project's blueprint.
- **Rationale.** R-SCAN-9. Measured on Grove's own repository: the documents
  added by this change raise the declared layer from 128 to about 1600 items,
  nearly all of which are not product promises (analysis 3.6).
- **Acceptance.** Migration 3 adds `projects.exclude` (a list of
  gitignore-style patterns). `grove_scan` takes optional `exclude`: when
  given it replaces the stored list (an empty list clears it); when absent
  the stored list applies. Every scan result reports `excluded` (the
  patterns in effect and how many files they removed). An upgrade test from
  schema 2, and a test that a database migrated step by step has the same
  schema as a fresh one.
- **Debate.** The need is measured, so the question was only how.
  - *One way to set it, not two:* the first draft also added the parameter
    to `grove_project_create`. One place is enough.
  - *Stored, not per call:* a list that must be repeated on every scan will
    be forgotten, and the noise returns silently.
  - *Cut:* a `.groveignore` file in the project (agents would have to write
    inside the project to maintain it); skipping `fixtures/`, `examples/`
    and `vendor/` by default (silently hides real code in projects whose
    product lives there); keeping the list inside the `last_scan` report
    column to avoid a migration (a report that is also configuration).
  - *Consequence accepted:* a scan argument that changes stored state is
    unusual. It is the only route while the tool names are frozen, and the
    result always shows the list in effect.
- **Kind.** both.

### WO-11 — Verify the Grok Bot registration for real *(open)*

- **Goal.** The README's Grok Bot instructions are known to work.
- **Rationale.** R-GROK-7. Never tried against Grok Bot; the largest
  unverified assumption for one of the two clients.
- **Acceptance.** Someone with a Grok Bot account registers Grove with the
  README's shape, lists the sixteen tools, runs `grove_status` and sees
  `home_source: "env"`; the shape, the Grok Bot version and the protocol
  revision it spoke are recorded in the README.
- **Debate.** No code. It comes before several should-orders because their
  value depends on what Grok Bot actually does: whether it shows server
  instructions (WO-20), whether it reads structured results (WO-25),
  whether it reads an `AGENTS.md` (WO-21).
- **Kind.** verification.

## Should

### WO-12 — A linter and one check script *(open, narrowed)*

- **Goal.** Mechanical mistakes are caught by a tool, with one command.
- **Rationale.** R-QUAL-8. Observed without changing the repository: 22 lint
  findings (mostly import order), 4 type-checker reports, 3 shell-lint
  warnings (analysis 3.9).
- **Acceptance.** A linter pinned in the `dev` group, configured for the
  code's existing style and for error-class rules only (undefined and unused
  names, unused imports); the three shell warnings fixed; `scripts/check`
  runs the linter, the shell linter if present, the tests and
  `scripts/check-publish`.
- **Debate.** Most of the first draft did not survive.
  - *Cut: reformatting.* The formatter would rewrite 22 of 24 files with no
    change in behaviour; every later `git blame` pays for it.
  - *Cut: a type-checker gate and typed dictionaries for every row.* The
    four reports were read and none is a defect. Typing every dict-building
    function is boilerplate over code whose shapes the tests already pin.
  - *Cut: a coverage floor.* Coverage is 92 %; print it, do not gate on it.
  - *Cut: a spelling checker.* Low yield for a new dependency.
  - Moved from must to should: none of this blocks safe work.
- **Kind.** code.

### WO-13 — Untrusted text: say so, and narrow map ingest *(open, narrowed)*

- **Goal.** A client is told that text Grove returns may come from a third
  party, and the map tool reads only map-like files.
- **Rationale.** R-SEC-4, R-SEC-5 (analysis 3.7).
- **Acceptance.** (1) One sentence in the server instructions: text from
  scanned files, maps and notes is data to weigh, never an instruction.
  (2) `ingest-map` accepts `.md`, `.markdown`, `.mdx`, `.rst`, `.txt` and
  files without an extension; anything else is `invalid`.
- **Debate.** Grove has no outbound action, so injected text cannot make
  *Grove* do anything; the risk sits with the client. That bounds what is
  worth building here.
  - *Kept:* the sentence (bytes once per session, in the instructions, not
    sixteen times) and the extension list (three lines; least privilege for
    a tool named for maps).
  - *Cut: counting or escaping invisible characters in results.* A new
    field on six tools and a pass over all returned text, for a threat the
    client is better placed to handle. Grove's value as evidence is that it
    returns what the file says.
  - *Cut: a trust marker inside the text* (the stored text can forge it)
    *and a new trust field* (provenance is already in `origin`,
    `source_path` and `author`).
  - *Cut: a filtering model* (R-INV-2).
- **Kind.** both (the extension list is a tightening under R-COMPAT-6).

### WO-14 — Work-item history *(open, redesigned)*

- **Goal.** A work item shows who did what and when, and two agents can log
  progress on it without erasing each other.
- **Rationale.** R-WORK-5. Tested: the second writer of `notes` erases the
  first; nothing records status changes (analysis 3.5).
- **Acceptance.** Migration adds an append-only `work_events` table (item,
  time, author, old and new status, note). `grove_work_update` takes
  optional `note` and `author`; every update that changes status or carries
  a note adds one event. `grove_work_get` returns `history` (the newest 20
  events and the total). `notes` and `plan` keep their replace semantics.
  All transitions remain allowed (R-WORK-3).
- **Debate.** One mechanism for both problems: progress goes into `note`,
  which can only append, so there is nothing to lose.
  - *Cut: `append_notes`* (a second way to write the same field).
  - *Cut: `expected_updated_at`* (optimistic locking is machinery for a
    conflict that an append-only log removes).
  - *Cut: claiming or locking an item* (an agent session that dies would
    leave locks behind; the history already shows who touched it last).
  - *Cut: writing status changes into `notes` as text* (no migration, but a
    later replace of `notes` would erase the history).
- **Kind.** both.

### WO-15 — References on work items *(open, narrowed)*

- **Goal.** A work item can point at the requirement, note or change it
  belongs to, and be found by it.
- **Rationale.** R-WORK-6, section 11.2.
- **Acceptance.** `grove_work_create` and `grove_work_update` take optional
  `refs`, a list of short strings stored as given and never fetched
  (`R-HOME-2`, `knowledge:greet-plan`, a pull-request URL).
  `grove_work_list` takes optional `ref` to filter by an exact reference.
- **Debate.** The first draft had four new fields. One survived.
  - *Cut: `acceptance`.* It belongs in `plan`; a second free-text field
    would be filled inconsistently.
  - *Cut: `evidence` and `reviewer`.* A history event with a note and an
    author (WO-14) is exactly that record.
  - *Cut: typed link objects.* A prefix in the string carries the type
    without a schema to maintain.
  - *Cut: a warning when an item is closed without evidence.* Grove records;
    it does not nag (R-SCOPE-3).
- **Kind.** both. After WO-14 (same migration if done together).

### WO-16 — Cheap blueprint navigation *(open, narrowed)*

- **Goal.** An agent finds the part of a blueprint it needs without paging
  all of it.
- **Rationale.** R-GROK-8. Measured: one page of 128 declared items is 44 KB.
- **Acceptance.** `grove_blueprint_get` takes optional `summary` (per source
  file: counts by layer; no items) and `source_path` (an exact path, or a
  prefix ending in `/`). Paged; tested on both surfaces.
- **Debate.** Summary to choose a file, path to read it: two parameters
  cover the walk. *Cut:* a `class` filter (`gaps` already lists the claims
  that matter, and `query` exists); a `compact` or `fields` switch (a second
  result shape for every client to handle). Revisit either only with a
  measured case the two parameters do not serve.
- **Kind.** both.

### WO-17 — Report the symbols cap *(open, narrowed)*

- **Goal.** R-INV-11 holds for the one cap that silently loses data.
- **Rationale.** More than 500 symbols or tests in one file are dropped with
  no trace.
- **Acceptance.** The scan result names files where the cap applied, with the
  true count; module and test-file items carry the true count in `extra`.
- **Debate.** The first draft also counted clipped titles, clipped bodies and
  dropped short sentences. *Cut:* clipping is already visible (the text ends
  in `…`, and module bodies say `(+N more)`); dropping two-word fragments is
  an extraction rule, not a cap. Three counters that nobody would act on are
  noise in every scan result. Section 8 of `REQUIREMENTS.md` now classifies
  them that way.
- **Kind.** both.

### WO-18 — Validate `kind` *(open, narrowed)*

- **Goal.** A typo is an error, not an empty answer.
- **Rationale.** R-GAP-5. Tested: a misspelt kind returns `ok` with no items
  and `complete: true`.
- **Acceptance.** `kind` is an enum in the schema and validated in the
  service (`invalid`, listing the kinds); the CLI offers the choices.
- **Debate.** *Cut:* rejecting relative paths over MCP, and a
  `resolved_from` field. Results already echo the absolute path, and the
  rule is written down (R-IF-8); neither change would prevent a mistake the
  echo does not already reveal.
- **Kind.** both (tightening under R-COMPAT-6).

### WO-19 — Knowledge: other scopes, read from a line *(open, narrowed)*

- **Goal.** No surprise about which document was returned, and no need to
  fetch a whole document to read one section.
- **Rationale.** R-KNOW-8. Tested: with one key in the workspace and in a
  project, `knowledge get` returns the workspace document and says nothing
  of the other.
- **Acceptance.** `grove_knowledge_get` returns `other_scopes` when the key
  exists elsewhere, and takes optional `from_line` (a line number from the
  `outline`): the 4000-character excerpt then starts there.
- **Debate.** `from_line` reuses two things that exist, the outline and the
  excerpt size, so it adds one integer. *Cut:* `section` by heading title
  (titles repeat); `offset` with `max_chars` (a second size limit for
  clients to reason about); `include_workspace` on search (two calls do it;
  the default must not change, A6).
- **Kind.** both.

### WO-20 — A leaner, more instructive MCP surface *(open, narrowed)*

- **Goal.** Less context spent per session, and the working loop stated once.
- **Rationale.** R-GROK-3, R-GROK-6. Measured: `tools/list` is 15.6 KB; one
  93-character sentence ends all sixteen descriptions (1.5 KB).
- **Acceptance.** The local-only sentence moves to the server instructions
  (the test that requires it per description then checks the instructions
  and the annotations); the instructions state the loop of R-GROK-6 and that
  blueprint and finding ids are not stable; the budget in R-GROK-3 drops to
  14.5 KB, and lower if tightening the three longest descriptions allows.
- **Debate.** Only the changes that remove bytes or prevent a known mistake.
  - *Cut: compact rows in `grove_project_list`.* It would remove a result
    field, which the compatibility policy forbids.
  - *Cut: `next_offset` on every page.* The client can add two numbers; the
    field would ride on every list result for ever.
  - *Cut: `idempotentHint`.* No known client behaviour depends on it.
  - *Cut: a worked example in every description.* Sixteen examples cost
    more context than they save.
  - Do after WO-11: if Grok Bot does not show server instructions to the
    model, moving the sentence there would lose it.
- **Kind.** both.

### WO-21 — CLI ergonomics for agents *(open, narrowed)*

- **Goal.** Claude Code can write a note without a temporary file in the
  project, from any directory.
- **Rationale.** R-CC-4, R-CC-5, R-GROK-1. Tested: `knowledge write
  --file -` fails with `not_found`.
- **Acceptance.** `knowledge write --file -` reads the body from stdin;
  `ingest-map` and `grove_ingest_map` take `author`; the README documents
  installing `grove` on `PATH`.
- **Debate.** *Cut:* `--body TEXT` (stdin covers it; a third way to pass one
  value); an `AGENTS.md` (only if WO-11 shows Grok Bot reads one; otherwise
  it is a second brief to keep in step).
- **Kind.** both.

### WO-23 — Measure the heuristics and the search *(open)*

- **Goal.** Know how often a finding is right, and notice when a change makes
  it worse.
- **Rationale.** R-QUAL-10. `BUILD_NOTES.md`: precision and recall were never
  measured.
- **Acceptance.** Two or three small fixture projects with a hand-labelled
  list of true gaps; a test that computes precision and recall per finding
  kind and fails below a recorded floor; about twenty search queries with
  the documents that should be found; the numbers recorded with a date.
- **Debate.** This is the order that keeps the others honest: without it,
  every change to a pattern is an opinion. Kept small on purpose. *Cut:*
  public benchmark datasets and mined repositories (large, licence
  questions, and built for other tasks).
- **Kind.** code (tests and fixtures only).

### WO-24 — Randomised tests for the parsers *(open, narrowed)*

- **Goal.** The extractors never raise and never hang, whatever the input.
- **Rationale.** R-SCAN-7. Three superlinear paths were found by hand in this
  session.
- **Acceptance.** A test that builds random lines and documents from a small
  alphabet of the characters the patterns care about (seeded, standard
  library only) and asserts for each extractor: no exception, same output
  twice, time within a linear bound. The README states which Markdown
  constructs are read and which are not. The patterns defined twice (in
  `scan.py` and `mapdoc.py`) are defined once.
- **Debate.** A seeded generator in the standard library is enough to find
  defects of the kind found here. *Cut:* a property-testing library (a dependency to
  earn only if the simple generator proves too weak); a vendored corpus of
  awkward strings (a dozen hand-picked ones do the job); a Markdown parser
  as a comparison oracle (the scanner differs from a parser by design, so
  most differences would be noise).
- **Kind.** code.

### WO-25 — Protocol coverage *(open, narrowed)*

- **Goal.** Both protocol eras are tested, and a schema change is always a
  deliberate act.
- **Rationale.** R-QUAL-7, R-INV-9. Seen by hand: the server answers the
  per-request protocol without a handshake. No test covers it.
- **Acceptance.** A stdio test for the `2026-07-28` revision; a stored
  snapshot of the sixteen input schemas that a test compares; the behaviour
  on shutdown documented (replies to calls still running when stdin closes
  are not delivered).
- **Debate.** The first draft recommended adding `structuredContent` and an
  `outputSchema` to every tool. On reflection, no:
  - output schemas for sixteen tools would add substantially to
    `tools/list`, against WO-20;
  - a result carried both as text and as structured content is paid for
    twice by any client that passes both to its model;
  - nothing shows that either client needs it.
  Decide after WO-11, on evidence. *Also cut:* a test that the CLI and the
  MCP path return the same data (they call the same method through the same
  wrapper; the test would prove the obvious).
- **Kind.** code.

### WO-26 — Harden and test the publish check *(open, narrowed)*

- **Goal.** The last guard before a public push is tested and covers every
  commit pushed.
- **Rationale.** R-SEC-6, R-INV-15. The hook checks only the tip of each
  ref; the script has no tests.
- **Acceptance.** The hook checks every new commit in the pushed range (it
  already receives the remote SHA); tests in a temporary repository show
  that a planted fake token, a forbidden file name and a private-path
  pattern are each caught and a clean tree passes.
- **Debate.** *Cut:* a second, maintained secret scanner (another tool to
  install and keep in step, for patterns the script already has; reconsider
  if the script ever misses something real); a check for bidirectional
  control characters in source (no incident, no evidence of risk here).
- **Kind.** code.

### WO-27 — A security policy *(waiting: a contact address for reports)*

- **Goal.** Someone who finds a vulnerability knows where to send it, and
  the trust boundary is written down.
- **Rationale.** R-SEC-7.
- **Acceptance.** `SECURITY.md`: how to report; what Grove trusts and does
  not (section 9 of `REQUIREMENTS.md` in a paragraph); what to do if a
  secret was pushed (rotate first); how a dependency pin is changed (by
  review, with an audit of the locked set run outside the product). One
  paragraph in the README on copying `grove.db` safely.
- **Debate.** One short file. *Cut:* a contributing guide (a third copy of
  rules that live in `CLAUDE.md` and section 11); a release checklist (three
  lines, to be written at the first release); a commit-message convention
  (nothing consumes it).
- **Kind.** docs. **Needs the owner:** the address.

## Later

### WO-22 — Explicit requirement ids as a trace *(open, narrowed, moved down)*

- **Goal.** A link stated by people beats a link guessed from words.
- **Acceptance.** A declared sentence that carries an id of a configured
  form records it; a test whose name mentions that id counts as covering
  it; the finding evidence says which rule matched.
- **Debate.** Attractive, and premature. Reading `REQUIREMENTS.md` into the
  declared layer today would turn each table row into one long "sentence"
  and add noise, not signal; and matching ids only helps projects that name
  tests by id, which Grove itself does not. Do it only after WO-10 (so
  noise can be excluded) and WO-23 (so the gain can be measured). *Cut:*
  adding requirement and specification files to the declared layer
  wholesale.
- **Kind.** both.

### WO-28 — Stable finding keys *(open, narrowed)*

- **Goal.** A finding can be referred to tomorrow.
- **Rationale.** R-REC-2. Ids change on every scan.
- **Acceptance.** Each finding has a `key` derived from kind, source path
  and normalised text; `recommend` skips a finding whose key is in the
  `refs` of an open work item (WO-15).
- **Debate.** *Cut:* waivers ("accepted" findings with a reason). A second
  state machine on findings; a work item marked `done` with a note says the
  same thing.
- **Kind.** both.

### WO-29 — Unfinished work in `recommend` *(waiting: A2)*

- **Acceptance (default, non-breaking).** `grove_recommend_next` adds
  `open_work`: counts and the oldest ids of `in_progress` and `review`
  items. A new top tier only if the owner asks for it.
- **Debate.** The brief already tells a returning agent to list its open
  work; this is a convenience, hence later.
- **Kind.** both.

### WO-30 — Archive without deleting *(waiting: A3)*

- **Acceptance.** An `archived` flag on projects, knowledge documents and
  work items, set through optional parameters of existing tools; archived
  rows are left out of lists and search unless asked for; nothing is
  deleted.
- **Debate.** Needed once the shared home collects test projects; not
  before. Deletion stays out: it is the one operation that cannot be undone.
- **Kind.** both.

### WO-34 — Verify macOS and Windows *(open)*

- **Acceptance.** The suite passes on both; differences found are recorded;
  R-QUAL-6 updated.
- **Debate.** Only when someone uses Grove there.
- **Kind.** verification.

### WO-35 — Scanner precision, measured *(open)*

- **Acceptance.** Only after WO-23. Candidates: TypeScript class methods, Go
  `type ( ... )` blocks, `describe` blocks. Each is adopted only with a
  measured gain.
- **Debate.** A syntax-tree dependency stays rejected (D-17) until
  measurement shows the per-line patterns are what limits Grove.
- **Kind.** code.

## Left out

These were written up in the first draft and removed by the filter. They
keep their ids so that references to them resolve and nobody re-proposes
them without new evidence.

### WO-31 — Test results in the tests layer *(left out)*

- **The idea.** Read a JUnit or TAP result file so the tests layer knows
  pass, fail and skip, not only names.
- **Why not.** Results go stale the moment the code changes, so a stored
  "passed" would be a claim Grove cannot stand behind (R-SCOPE-3). It needs
  a parser for a format whose files come from untrusted projects. And the
  agent that wants results can run the tests. The honest limit, "Grove knows
  a test's name, not what it asserts", stays in the README.
- **Would change the answer:** a client that cannot run tests itself.

### WO-32 — Export command *(left out)*

- **The idea.** `grove export DIR` writing notes and work items as files.
- **Why not.** A CLI command with no MCP twin breaks "both surfaces offer
  every operation" (R-IF-10), and a seventeenth tool is not allowed
  (R-INV-9). Every note is already readable in full with `knowledge get
  --full`. The real gap was backup, which is one paragraph of documentation
  (WO-27).
- **Would change the answer:** a need to move a workshop between machines.

### WO-33 — Unicode and case policy *(left out)*

- **The idea.** Normalise keys, names and paths; fold case; count
  identifiers the tokeniser skips.
- **Why not.** Checked against the code: knowledge keys and project names
  are restricted to ASCII by their validation patterns, and the tokeniser
  matches ASCII letters only, so there is nothing to normalise or fold;
  full-text search has its own Unicode tokeniser. What remained was one
  missing sentence in the README's limits ("words in other scripts are not
  compared"), which this change adds.
- **Would change the answer:** a user whose documentation is not in a
  Latin script.
