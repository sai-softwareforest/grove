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

An order is argued a second time when it is built, because the details only
show then. That is recorded under **Debate while building** (WO-08, WO-09,
WO-10, WO-12, WO-14, WO-24).

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
| WO-08 | An automated gate for every change (CI) | must | infrastructure | done |
| WO-09 | Refuse a data directory inside a project root | must | both | done |
| WO-10 | Per-project scan excludes | must | both | done |
| WO-11 | Verify the Grok Bot registration for real | must | verification | open (trial run; three measurements not recorded) |
| WO-12 | A linter and one check script | should | code | done |
| WO-13 | Untrusted text: say so, and narrow map ingest | should | both | done |
| WO-14 | Work-item history | should | both | done |
| WO-15 | References on work items | should | both | open (narrowed) |
| WO-16 | Cheap blueprint navigation | should | both | open (narrowed) |
| WO-17 | Report the symbols cap | should | both | done |
| WO-18 | Validate `kind` | should | both | done (narrowed: the schema `enum` is deferred) |
| WO-19 | Knowledge: other scopes, read from a line | should | both | open (narrowed; other scopes built, `from_line` waits for WO-20) |
| WO-20 | A leaner, more instructive MCP surface | should | both | open (narrowed) |
| WO-21 | CLI ergonomics for agents | should | both | open (CLI side done; MCP author waits on the budget/WO-20) |
| WO-22 | Explicit requirement ids as a trace | later | both | open (narrowed, moved down) |
| WO-23 | Measure the heuristics and the search | should | code | done |
| WO-24 | Randomised tests for the parsers | should | code | done |
| WO-25 | Protocol coverage | should | code | done |
| WO-26 | Harden and test the publish check | should | code | open (narrowed) |
| WO-27 | A security policy | should | docs | done |
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

### WO-08 — An automated gate for every change (CI) *(done)*

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
- **Owner's decision (A8, 2026-11-12).** Yes, in this shape, as a visible
  check only: no branch protection and no required status check until the
  job has been seen to stay green. Relayed by the owner's assistant.
- **Debate while building.** One file, `.github/workflows/ci.yml`, about
  thirty lines.
  - *Kept: the five rules as a text test* (`tests/test_gates.py`, standard
    library, no YAML parser). The debate above cut a workflow linter as a
    required tool; it did not cut knowing when a rule is broken. The next
    order to touch this file (WO-12 adds a lint step) is the moment a secret,
    a floating version or `pull_request_target` could slip in, and prose
    would not stop it (the lesson of WO-07).
  - *Kept: rule 5 as "no expression at all".* The workflow contains no
    `${{ }}`. That is stricter than "no pull-request value in a script" and
    can be checked by one substring test; the job needs none. The event name
    comes from the runner's own `GITHUB_EVENT_NAME`.
  - *Kept: the publish check runs on the pull request's head commit,* not on
    the merge commit that GitHub builds for the run. The merge commit has a
    message GitHub wrote, so checking it would never read the author's own
    message. The checkout therefore fetches two commits and the step checks
    the second parent. The tests do run on the merge result, which is what
    would land.
  - *Kept: `persist-credentials: false` and no dependency cache.* The token
    is not left in the checkout for later steps, and a cache that pull
    requests can write is a known way to poison later runs; the install is a
    few seconds without it.
  - *Kept: a fixed runner image and a fixed uv version* (`ubuntu-24.04`, uv
    0.13.7, the version of the first build). A floating one would let the
    gate change with no commit in this repository.
  - *Cut: a Python set-up action.* uv installs the interpreter named in
    `.python-version`; one action fewer to pin and trust.
  - *Cut: checking every commit of the pull request.* That is the range
    check of WO-26, in the script, where the local hook gets it too.
  - *Cut: a concurrency group, a status badge, a path filter.* None changes
    whether a defect is seen. A path filter would skip the publish check on
    a documents-only change, which is where a pasted secret is most likely.
  - *Cut: branch protection and a required check.* The owner's decision.
  - *Risk taken knowingly:* `test_scan_robustness.py` asserts time bounds
    (1 to 3 seconds for work that takes milliseconds). On a slow shared
    runner one could fail without a defect. They are left as they are: the
    margins are wide, and watching for exactly this is why the check starts
    as visible only. A failure there is to be read, not rerun (R-QUAL-1).
  - *Not checkable in CI:* machine-specific paths. The patterns live in the
    uncommitted `scripts/check-publish.local`, which a clean runner does not
    have. The local hook stays the guard for those.
  - *Found while building, fixed with it:* the publish check let an agent
    session link through, in a file and in a commit message, although
    R-INV-15 names session ids. Ten lines in the script and three tests; see
    WO-26.
- **Kind.** infrastructure. Tests: `tests/test_gates.py`.

### WO-09 — Refuse a data directory inside a project root *(done)*

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
- **Debate while building.** One private method, called from two places;
  no new field, parameter or state.
  - *Kept: the check in `project_create` runs before the database is
    opened.* A refusal that had first created `grove.db` inside the project
    would break the rule it enforces. `scan` has to open the database to
    learn the root; there the file already exists.
  - *Kept: `scan` resolves the stored root again.* A link on the way to the
    root can change after registration; one `realpath` per scan.
  - *Kept: one sentence in the `root_path` parameter description* (43
    bytes of `tools/list`), where a caller chooses the path. *Cut:* a sentence in
    the `grove_scan` and `grove_project_create` descriptions (bytes in every
    session for an error that explains itself when it happens).
  - *Cut: refusing every operation on a project registered this way.* Its
    notes and work items must stay reachable, or the person cannot see what
    they are about to move. Opening such a database still writes to it
    (migrations, work items); stopping that would lock the data in.
  - *Cut: checking every registered root on each call,* so that a home
    inside project A is refused while scanning project B. A query and a
    path walk on every call; each project is checked when it is scanned,
    which is when R-HOME-4 applies to it.
  - *Cut: refusing a project root inside the data directory.* The reverse
    case writes nothing into the project.
  - *Cut: comparing by inode (`samefile`)* to catch differently spelt paths
    on case-insensitive file systems. Those platforms are unverified
    (WO-34); resolving symlinks is the stated rule.
  - *Cut: a `status` warning when the data directory lies inside some
    registered root.* A field on the first call of every session, for a
    state the next scan reports anyway.
- **Kind.** both (a tightening under R-COMPAT-6). Tests:
  `tests/test_scan_safety.py`.

### WO-10 — Per-project scan excludes *(done)*

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
- **Debate while building.** One column, one parameter, one result field.
  - *Kept: patterns are matched against each file's path; excluded
    directories are walked, not pruned.* Pruning is what git does and saves
    the walk, but then the number of files removed is unknown: `fixtures/`
    would report 0 files, exactly like a mistyped pattern. Matching each
    file keeps the count exact for one extra match per file (measured:
    50 000 paths against five patterns in 0.07 s); nothing is read and the
    time cap still holds. *Side effect, accepted and documented:* unlike
    git, a later `!pattern` brings back a file under an excluded directory.
    That is what makes "`docs/` except `docs/blueprint.md`" a two-line
    list (D-33).
  - *Kept: excluded files are outside `files_seen` and the file cap.*
    Otherwise a large vendored tree would still use up the cap that
    excluding it was meant to free. The time cap is checked for each
    excluded file too.
  - *Kept: a size limit as an error* (50 patterns of 200 characters). The
    list is stored and comes back in every scan result and project row, so
    it must be bounded (R-GROK-4); a real list has a handful of entries.
  - *Kept: the list is written in the scan's own transaction, and only
    when given.* A refused or failed scan changes nothing, and the stored
    list is always one that produced a blueprint.
  - *Cut: an `exclude` field on the project row.* Only a scan can set the
    list, so `last_scan.excluded.patterns` already shows it.
  - *Cut: a count per pattern.* With negations, saying which pattern
    removed a file is subtle, and the total already exposes a list that
    removes nothing. It can be added later; a field can never be removed.
  - *Cut: a line in `warnings` when files are excluded.* Warnings become
    the project's `cap_warnings`; an exclusion the caller asked for is not
    a cap. `excluded` reports it.
  - *Cut: a `--no-exclude` flag.* Blank entries are dropped, as blank lines
    in a `.gitignore` are, so `--exclude ''` is the empty list. One flag.
  - *Cut: parameters to add or remove a single pattern.* The result echoes
    the list; a caller edits it and sends it back.
  - *Cut: a test that pins the text of shipped migrations.* It would guard
    R-INV-7 against an edited migration, which the step-by-step test
    cannot see, but it is outside this order. It fits the schema snapshot
    of WO-25.
  - *Cost:* `tools/list` grows from 15 692 to 16 054 bytes (the first draft
    of the wording cost 443; it was shortened to 362). 330 bytes of the
    budget remain until WO-20 recovers about 1.5 KB.
  - *Consequences accepted:* R-INV-3 now names the stored list as an input
    of a scan, beside the tree and the arguments. If two scans of one
    project overlap and one of them sets a new list, each reports in
    `excluded` the list it really used, and the next scan applies the
    stored one. After the upgrade to schema 3 an older Grove refuses the
    data directory (R-INV-7), as with every migration.
  - *Measured on this repository:* 1613 declared items and 254 findings
    without a list; 360 and 31 with `fixtures/` and the three
    non-normative documents excluded.
- **Kind.** both. Tests: `tests/test_scan_exclude.py`, `tests/test_db.py`.

### WO-11 — Verify the Grok Bot registration for real *(open: trial run, three measurements not recorded)*

- **Goal.** The README's Grok Bot instructions are known to work.
- **Rationale.** R-GROK-7. When this order was written Grove had never been
  tried against Grok Bot; that was the largest unverified assumption for one
  of the two clients.
- **Acceptance.** Someone with a Grok Bot account registers Grove with the
  README's shape, lists the sixteen tools, runs `grove_status` and sees
  `home_source: "env"`; the shape, the Grok Bot version and the protocol
  revision it spoke are recorded in the README.
- **Debate.** No code. It comes before several should-orders because their
  value depends on what Grok Bot actually does: whether it shows server
  instructions (WO-20), whether it reads structured results (WO-25),
  whether it reads an `AGENTS.md` (WO-21).
- **Trial of 2026-11-12.** Three Grok Bots (Mila, Momo and Ume) used Grove
  over MCP on the computer that holds the data directory. This is recorded
  from the owner's brief for the change that built WO-14; the session that
  wrote it down did not watch the trial.
  - *Proved:* a Grok Bot can register Grove as a local stdio server, list
    the sixteen tools and run them, end to end. The Grok Bots can also run
    the `grove` command line on that computer, so MCP is not their only
    door.
  - *Learned:* a Grok Bot keeps the tool schemas it read when its connector
    started. After Grove is upgraded, the connector has to be restarted
    before new parameters (such as `note` from WO-14) are offered. The
    README now says so.
  - *Not recorded, so still open:* the Grok Bot version; the protocol
    revision it spoke; whether the registration was the README's shape
    exactly, and whether `grove_status` showed `home_source: "env"`. None
    of these is guessed here.
  - *Not answered:* whether Grok Bot shows server instructions to its model
    (WO-20 still waits on this), reads structured results (WO-25) or reads
    an `AGENTS.md` (WO-21).
- **To close.** At the next Grok Bot session on that computer: note the
  version and the protocol revision from the connector, call `grove_status`
  and note `home_source`, confirm the registration against the README, and
  write the three into the README. It needs no code.
- **Kind.** verification.

## Should

### WO-12 — A linter and one check script *(done)*

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
- **Debate while building.** Three small things: seven lines in
  `pyproject.toml`, `scripts/check` (about sixty lines of bash) and one step
  in the workflow. Measured first: the error-class rules already ran clean
  on the whole tree, so no Python file changed.
  - *The linter is ruff with one setting, `select = ["F"]`.* That is the
    pyflakes set: undefined names, unused names and imports, and mistakes of
    the same class (a redefinition that is never used, an f-string without a
    placeholder). A file that does not parse is reported whatever is
    selected.
  - *"Configured for the existing style" is met by selecting no style rule
    at all:* no line length, no import order, no quoting rule. Nothing about
    the layout of the code is judged, so nothing had to move. A line-length
    setting was weighed and left out: only the formatter and a rule that is
    not selected would read it, and the code is not in the formatter's
    layout at any width (at 140, the longest line today, it would still
    rewrite 14 of 30 files).
  - *Pinned to 0.17.3, not to the newest release.* 0.17.5 was one day old on
    the day of the build. A development tool runs on every author's machine
    and in CI; a release that has been out for two weeks is the cheaper
    risk. The linter is in the `dev` group only and is not a runtime
    dependency (R-INV-14).
  - *A test holds the configuration* (`tests/test_gates.py`): the pin is
    exact and the linter's section is exactly the one setting. A wider rule
    set, an ignore list or a formatter setting then fails the suite and
    sends its author to this debate, instead of arriving in a later edit
    (the lesson of WO-07).
  - *The whole tree is linted, `fixtures/` included* (`ruff check` with no
    path), so a new Python file anywhere is covered without a list to keep.
    **Would change the answer:** a fixture that needs a deliberate mistake;
    it gets an exclude then, with the reason beside it.
  - *The three shell warnings were unused variables.* In
    `scripts/check-publish`, `escaped` was computed and never read; the
    private-path search was and is a fixed-string match (checked by hand
    before and after: the pattern `a.b` does not match `axb`). In the hook,
    the two remote fields of each line are read into `_`. Removing the dead
    line also removed the one info-level remark. shellcheck 0.11.0 is silent
    on the three bash files.
  - *`scripts/check` runs every step even after a failure* and ends with a
    summary: `passed`, `FAILED` or `skipped` per step, exit code 1 if any
    failed. Stopping at the first failure would hide the second one until
    the next run.
  - *The shell linter stays optional, as the acceptance says,* and a skipped
    step is a line in the summary, never silence (the rule for caps, applied
    to a check). It is not a development dependency: a pinned copy would be
    a Python package that wraps a downloaded binary, one more thing to trust
    for three files. *Consequence, accepted:* on a machine without
    shellcheck the bash files are not linted, and the summary says so.
  - *One step was added to the workflow, `uv run ruff check`,* as WO-08
    expected. The linter comes from `uv.lock`: no new action, no expression,
    no floating version, and the five rules still hold.
  - *CI does not call `scripts/check`, and does not run the shell linter.*
    The publish check in CI must read the pull request's head commit, not
    the merge commit (WO-08), and the script reads `HEAD`. The shellcheck on
    the runner is whatever its image carries, so a new image could turn the
    job red with no change in the repository. **Would change the answer:**
    a shell warning that reaches `main` unnoticed.
  - *The pre-push hook is unchanged in what it runs.* A hook that runs the
    suite on every push is the hook people learn to skip.
  - *The script is tested by running it,* in a temporary repository with
    stand-ins for `uv` and `shellcheck` on a search path that holds only
    what the script needs. The suite therefore does not start itself, and
    the skipped case is tested on machines that do have shellcheck. A second
    test fails when a bash file exists that the script does not lint.
  - *Cut again: reformatting, a type-checker gate, a coverage floor, a
    spelling checker.* For coverage, "print it" is left to the command in
    `docs/analysis.md`, section 8: printing it from `scripts/check` would
    add a coverage plugin as a pinned dependency and a slower run, for a
    number nothing acts on.
  - *Cut: running the linter as a test.* `uv run pytest -q` alone would
    then catch a lint mistake, but the script would lint twice and a lint
    finding would be reported as a failing test.
  - *Found on the way:* the workflow's header named a test file that does
    not exist; it now names `tests/test_gates.py`.
- **Kind.** code.

### WO-13 — Untrusted text: say so, and narrow map ingest *(done)*

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
- **Built in two changes.** Acceptance (1), the sentence, then acceptance
  (2), the extension list. Each was argued when it was built.
- **Debate while building: the sentence.** One sentence, 99 bytes, in the
  server instructions; a client receives it once per session. `tools/list` is
  byte for byte what it was (16 366 bytes), so the 18 bytes left in the
  budget are still there.
  - *Built alone: the sentence.* The two parts share a requirement area
    and nothing else. The sentence is words. The extension list changes
    what a command accepts (R-COMPAT-6) and needs its own tests and its
    own line under "Changed"; it is a separate review.
  - *Kept: a test, though no earlier order tested the instructions.*
    R-SEC-4 says MUST, and WO-20 will rewrite the instructions: a sentence
    that nothing tests is the one a rewrite drops. The test looks for the
    rule (the three sources, "data", "never an instruction"), not for the
    exact wording, so WO-20 may reword it. The smoke test also compares
    what a client receives in `initialize` with the text in the module: a
    sentence in a constant that is never sent would prove nothing.
  - *Cut: repeating the rule in a tool description.* The order says once,
    not sixteen times, and no description has room.
  - *Cut: a decision-log row.* Nothing was decided here that the order had
    not decided already.
  - *The cuts stand:* no counting or escaping of invisible characters, no
    trust marker in the text, no trust field, no filtering model.
  - *Not known:* whether a Grok Bot's model is shown the server
    instructions (WO-11). If it is not, the sentence still reaches clients
    that do show them, and the README's note for another project's
    `CLAUDE.md` carries the same rule. Nothing more is built on a guess.
- **Debate while building: the extension list.** One check in
  `service.ingest_map`, so the command line and the MCP tool cannot differ.
  `tools/list` is still 16 366 bytes: no description and no parameter
  changed.
  - *The list is the scanner's `DOC_EXTENSIONS`, not a second tuple.* It
    was already the order's list, to the letter. A test pins it, so
    widening the scanner's list fails a map test and sends its author to
    R-SEC-5.
  - *Case does not count:* `MAP.MD` and `NOTES.TXT` are maps. The scanner
    lower-cases a name before it looks at the extension, and the map tool
    now reads a name the same way.
  - *A dotfile is not "a file without an extension".* Python's split gives
    `.env` and `.netrc` no extension, so the order read to the letter would
    accept the files this narrowing most plausibly keeps out. A name that
    is only a dot and a word is taken as its own extension and refused. A
    refusal can be lifted later as an addition; an acceptance can only be
    withdrawn as one more tightening. **Would change the answer:** a real
    map kept in a dotfile.
  - *The name judged is the resolved one,* the one the knowledge key and
    `source_path` already came from. A link `notes.md` that leads to
    `settings.json` is refused; a link to a map is read whatever the link
    is called.
  - *The name is judged before the file is looked for.* `missing.py` is
    `invalid`, not `not_found`: Grove says nothing about a file it would
    not read. A mistyped extension on a missing file gets the message about
    extensions, which is the more useful of the two.
  - *It is not a guard against secrets, and the documents say so.* `id_rsa`
    has no extension and is still read, and anyone can rename a file. It is
    least privilege for a tool named for maps, as the order put it. *Cut:*
    looking at the content to decide ("looks like Markdown" has no
    definition that a test could hold).
  - *The description still says "markdown" and lists no extension:* there
    are 18 bytes left. The refusal message lists them, so an MCP client
    learns the rule at the first refusal. *Cut:* the list in the command's
    help text (one more copy; the README has it). WO-20 can name it in the
    description if it frees the bytes.
  - *R-COMPAT-6, said plainly.* The rule allows a tightening for input
    "that could never have produced a meaningful result". That is true of
    `settings.json`; it is not quite true of a map saved as `map.adoc` or
    `MAP.md.bak`, which was ingested before and is refused now. The order
    decided this, as WO-09 did for its refusal. The changelog names the
    remedy: rename the file; with the same stem it keeps its key and its
    revisions. Nothing stored is touched.
  - *Cut again: a decision-log row.* The order made the decision; what was
    settled while building is in this list.
  - *The cuts stand:* no counting or escaping of invisible characters, no
    trust marker, no trust field, no filtering model.
- **Kind.** both (the extension list is a tightening under R-COMPAT-6).
  Tests: `tests/test_mcp_stdio.py`, `tests/test_map_ingest.py`,
  `tests/test_cli.py`.

### WO-14 — Work-item history *(done)*

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
- **Debate while building.**
  - *An event only for a status change or a note.* Creating an item writes
    none: the item already carries `created_at` and `author`, and a first
    event would say the same thing twice. Replacing `plan`, `notes` or
    `title` writes none: the order says so, and an event without a note
    cannot say what changed. *Consequence, accepted:* an `author` given on
    an update that only replaces a field is checked and then recorded
    nowhere.
  - *A status set to the value it already has is not a change.* An agent
    that repeats `--status in_progress` each session would otherwise fill
    the history with empty rows.
  - *`old_status` and `new_status` are always both stored*, equal for a
    note. A note then shows which status the item was in when it was
    written, and no reader has to handle a missing value.
  - *A note is at most 1000 characters* (an error above it, section 8 of
    the requirements). `work get` returns twenty of them, and no default
    result may be unbounded (R-GROK-4): the worst case is about 20 KB.
    Longer text belongs in a knowledge document, named in the note.
  - *Only `work get` returns the history.* Not `work list` (up to 200 items
    of 20 events each), and not the results of `work create` and `work
    update`, which an agent receives on every write. The writer of a note
    reads it back with `work get`.
  - *Cut: paging the history.* Two more parameters on `grove_work_get`
    would have to be described, and 18 bytes of the description budget
    remain. `total` says when events are older than the twenty returned;
    they stay stored. **Would change the answer:** an item that really
    passes twenty events, once WO-20 has freed the space.
  - *Cut: triggers that forbid `UPDATE` and `DELETE` on the table.* The
    table is append-only because one `INSERT` is the only statement that
    touches it, as with `knowledge` (D-38).
  - *Cut: back-filling a first event for existing items.* It would invent a
    history that was never recorded.
  - *Cut: the long author description on `grove_work_update`.* The schema
    refers to `grove_work_create` in a few words. The sentence "This only
    updates Grove's local record" was removed from the description; the
    sentence that ends every description already says it.
  - *Measured:* `tools/list` went from 16 054 to 16 366 bytes of 16 384.
    Nothing more can be described until WO-20, which still waits on WO-11.
  - *Unintended consequence, recorded:* `--note` used to be accepted by the
    command line as a shortening of `--notes`, because the parser accepts
    any unambiguous prefix. It was never documented. It now means the new
    flag, so it appends an event and no longer replaces `notes`.
  - *Unintended consequence, recorded:* `notes` and `note` differ by one
    letter. The names are the order's; the description and `--help` say
    which one replaces and which one appends.
  - After the upgrade to schema 4 an older Grove refuses the data directory
    (R-INV-7), as with every migration. A running MCP server must be
    restarted to offer the new parameters (see the trial under WO-11).
- **Kind.** both. Tests: `tests/test_work.py`, `tests/test_db.py`.

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
    author (WO-14, built) is exactly that record.
  - *Cut: typed link objects.* A prefix in the string carries the type
    without a schema to maintain.
  - *Cut: a warning when an item is closed without evidence.* Grove records;
    it does not nag (R-SCOPE-3).
- **Kind.** both. After WO-14, which is built; this order needs its own
  migration.

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

### WO-17 — Report the symbols cap *(done)*

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
- **Debate while building.** One result field, two keys on blueprint items,
  one test file. No tool name, description or parameter is touched;
  `tools/list` is the same 16 366 bytes and the stored input schemas are
  unchanged.
  - *Where the report lives.* `caps.symbols_capped`, beside
    `caps.declared_capped`. The scan summary already travels whole to the
    scan result of both surfaces and to the project (`last_scan`), so
    `service.py`, `cli.py` and `tools.py` did not change; the tests call
    the CLI and the MCP tools and read the field from `scan`, `project get`
    and the blueprint.
  - *A bounded list.* Unlike `declared_capped`, which lists every capped
    document, this list shows the first 50 files with `total` and
    `omitted`, as `skipped_files` does. One repository of generated code
    can hold hundreds of files over the cap, and the summary is returned by
    every `project get`. A file left out of the list still carries its own
    count on its blueprint item.
  - *`found`, `kept`, `dropped`, and the cap once.* Not `total`: the list
    has a `total` of its own, the number of files. The cap is
    `caps.max_symbols_per_file`, once, not a field of every entry (the
    analysis had already removed one number that was reported twice).
  - *The keys on the items.* `symbols` and `tests` keep their meaning, the
    number kept, which is the number of items stored; `gaps.py` reads
    `symbols`. The number found is a second key, `symbols_found` or
    `tests_found`, present only when the cap applied. So the blueprint of a
    project with no such file is the same, byte for byte, as before.
  - *Counting means reading on.* The scanner used to leave the file at the
    cap. To know the true count it reads the rest. Measured on the worst
    file that is read at all (512 KB of one-line definitions, 40 000 of
    them): 4 ms before, 45 ms now. The time cap is still checked on every
    line. When it ends the scan inside such a file, `found` is the number
    counted up to there and the result says `max_seconds` as before; a
    test steps a clock by hand to show it.
  - *What a scan keeps is unchanged.* The old and the new scanner were run
    on four trees (this repository, `src/`, the fixture, and a generated
    tree with six files over the cap in four languages): the items are
    identical apart from the two new keys. One exception, made on purpose:
    the cap was checked once a line, so a line with several JavaScript test
    names could take a file to 502. A report that says "kept 502, cap 500"
    would be a second defect; the cap is now exact.
  - *Rust, reported and not changed.* The Rust extractor has one cap for
    every definition of a file. In a source file the inline tests share the
    500 with the symbols; the entry counts both, and `symbols_found` counts
    the symbols alone, so it can equal `symbols` when only tests were lost.
    In a test file the helpers use up the cap, so fewer than 500 tests may
    be kept: the entry then says, for example, found 300, kept 250. Giving
    tests a cap of their own would change which items a scan keeps; that
    is a decision for its own order, and until then the numbers are true.
  - *Not done: the tool description.* The `grove_scan` description names
    the other reports and not this one. It has 18 bytes left and this order
    was told to leave every description alone. It stays true: it says the
    caps are reported in the result, and the warning line reaches a client
    that reads nothing else. Naming the field belongs to WO-20.
  - *Not done, as the order decided:* counters for clipped titles, clipped
    bodies and dropped short sentences. Also left out: a count of inline
    tests on the module item (it has never had one; the scan entry counts
    them), a sum of everything dropped as a field (the warning says it),
    and a change to `extract_symbols` or `extract_test_names`, which keep
    their arguments and still return at most 500.
  - *A project scanned by an earlier version* has no `symbols_capped` in
    its `last_scan` until it is scanned again.
- **Kind.** both. Tests: `tests/test_symbols_cap.py`.

### WO-18 — Validate `kind` *(done, narrowed: the schema `enum` is deferred)*

- **Goal.** A typo is an error, not an empty answer.
- **Rationale.** R-GAP-5. Tested: a misspelt kind returns `ok` with no items
  and `complete: true`.
- **Acceptance.** `kind` is an enum in the schema and validated in the
  service (`invalid`, listing the kinds); the CLI offers the choices.
- **Debate.** *Cut:* rejecting relative paths over MCP, and a
  `resolved_from` field. Results already echo the absolute path, and the
  rule is written down (R-IF-8); neither change would prevent a mistake the
  echo does not already reveal.
- **Debate while building.** One check in the service, one flag of the CLI,
  one test file. No tool name, description, parameter or schema is touched;
  `tools/list` is the same 16 366 bytes and the stored input schemas are
  unchanged.
  - *Not done: the `enum` in the schema.* Measured: with
    `"enum": [the four kinds]` on `kind`, `tools/list` is 16 455 bytes, 89
    more, against a budget of 16 384 with 18 left (R-GROK-3). This order was
    told to change no description text, so nothing could be shortened to
    pay for it. What a client loses is small: the description already names
    the four kinds, and the service refuses a wrong one with a message that
    lists them. What it would gain is a refusal before the call, from
    clients that check arguments against the schema. The `enum` is one line
    for whichever change next makes room in the tool list (WO-20 removes
    about 1.5 KB); a test already holds a future `enum` to the same four
    kinds.
  - *One check, in the service.* `Grove.gaps` compares `kind` with
    `FINDING_KINDS`, so the CLI and the MCP tool return the same envelope,
    and a test compares the two. The message has the form used for `layer`
    and `status`: `kind must be one of declared_untested, declared_unseen,
    actual_undocumented, map_untested`. It does not repeat what was sent,
    so there is no rule for clipping it. The earlier check "longer than 60
    characters" is gone: it was already `invalid`, and a long wrong kind
    now gets the message that helps.
  - *A blank kind is still no filter.* `kind: ""`, `--kind ""` and a kind
    of spaces returned every finding before and still do; spaces around a
    valid kind are still ignored. R-COMPAT-6 allows a tightening only for
    input that could never have produced a meaningful result, and these
    did. R-GAP-5 now says so.
  - *The CLI offers; it does not check.* `--kind` shows the kinds in the
    usage line and in the help exactly as argparse shows choices, built from
    `FINDING_KINDS`, and passes the value on. *Cut: argparse `choices`,* as
    `--layer` has. It would refuse `--kind ""` and a kind with spaces
    around it, which work today, and it would give the CLI a message of its
    own, worded by argparse, where the MCP tool has another.
  - *Order of the checks.* Project, paging, then kind, as `blueprint_get`
    does with `layer`. A wrong project with a wrong kind is `not_found`.
  - *Not done: the tool description.* It does not say that an unknown kind
    is an error. It has 18 bytes left and was to be left alone. It stays
    true: it names the four kinds, and the error tells the client what to
    send.
  - *Noticed, not changed.* `grove work list --status` and `grove work
    update --status` do not show their five values in the help; the service
    has always refused a wrong one with a message that lists them.
  - *Kept cut, as the order decided:* rejecting relative paths over MCP,
    and a `resolved_from` field.
- **Kind.** both (tightening under R-COMPAT-6). Tests:
  `tests/test_gaps_kind.py`, and one call in each of the two stdio tests of
  `tests/test_mcp_stdio.py`.

### WO-19 — Knowledge: other scopes, read from a line *(open, narrowed: other scopes built, `from_line` waits for WO-20)*

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
- **Built: the result half.** `knowledge get` on both surfaces returns
  `other_scopes` when the key also exists in another scope: one entry
  `{"project": NAME}` per scope, the workspace first as `{"project": null}`,
  then projects by name, at most 20, with `other_scopes_total` as the true
  count. Both are absent when no other scope holds the key. Which document
  comes back is unchanged (R-KNOW-3).
- **Still open: `from_line`.** It is a new input parameter, and a parameter
  must be described (R-IF-10). `tools/list` is at 16 366 of 16 384 bytes,
  so it waits for the description budget that WO-20 frees. This half of
  R-KNOW-8 stays open, and so does the order.
- **Debate while building.** One query and two result fields in
  `service.knowledge_get`. No tool name, description or parameter changed:
  `tools/list` is byte for byte what it was (16 366 bytes), and the input
  schemas are the same.
  - *Built alone: the result field.* A result field needs no description
    to be read; a parameter nobody is told about is not a feature. *Cut:*
    `from_line` on the command line only (the two surfaces would differ,
    R-IF-10).
  - *An entry is `{"project": NAME}`, and `null` is the workspace.* It is
    the word and the value the document's own `project` field uses, and
    what the caller passes back as `project` to read that document.
    *Cut: a plain list of names* (a `null` among strings explains nothing,
    and a list of strings can never gain a field). *Cut: `project_id`* (a
    name is accepted wherever an id is, and names are unique). *Cut:
    `latest_revision` and `title` on each entry* (the second call tells;
    every field is permanent).
  - *Absent, not `[]`, when the key is in one scope only,* as `outline` and
    `more` are absent from a result that was not excerpted. The ordinary
    call carries no extra byte. *Consequence, accepted:* a client cannot
    tell "nowhere else" from "a Grove older than this change".
  - *A cap, so two fields where the order named one.* There is one entry
    per project that holds the key, and nothing bounds the number of
    projects. `map` is the likely case: `ingest-map` takes the key from
    the file name, so every project that ingested a `MAP.md` holds it. No
    default result may be unbounded (R-GROK-4) and no cap may be silent,
    so 20 are named and `other_scopes_total` counts them all, the way
    `outline` and `outline_total` do in the same result. Worst case about
    2.5 KB; usually one line. **Would change the answer:** a reviewer who
    prefers one uncapped field. The `invalid` message of R-KNOW-3 already
    names every project without a cap; it was not touched here.
  - *The workspace first, then by name.* Without `project` the workspace
    document is the one that wins, so for a caller who named a project it
    is the scope most likely to be the surprise. The order is fixed, so
    the same call gives the same list.
  - *Scopes beyond the twentieth are counted, not listed, by any
    operation.* The field exists to prevent a surprise, not to enumerate.
    A caller who wants one project's document names the project and gets
    it, or `not_found`. *Cut: paging the list* (two parameters).
  - *A scope counts once, whatever its revisions, and with or without
    `revision` in the call.* The returned document's scope is never
    listed.
  - *Errors say what they said.* `not_found` for a named project that
    lacks the key does not say where the key does exist. The order is
    about the document that was returned, and a message is not a result
    field. **Would change the answer:** an agent seen to give up there.
  - *Measured: the query is written as the index is.* A join from
    `knowledge` to `projects` scans the table, bodies included: 60 ms on
    50 000 documents of 3000 characters. Selecting the distinct
    `COALESCE(project_id, 0)` for the key first reads only the existing
    index: 2 ms, the cost of the lookup R-KNOW-3 already makes. No new
    index, so no migration.
  - *The description does not name the field.* There are 18 bytes left and
    this change may not spend them. Nothing the description says became
    false, and the field names itself in the result. WO-20 can add the
    words. `cli.py` did not change either: the command prints what the
    service returns, and a test reads it from the command line.
  - *Tests sit in `tests/test_knowledge.py`,* calling the tool in process
    as the excerpt and listing tests do. *Cut: a stdio test.* The smoke
    test already shows that a result reaches a client as the service
    built it; more protocol coverage is WO-25.
  - *Not written: a decision-log row.* The cap and the shape are decisions,
    and they are recorded here and in R-KNOW-8. Other orders are being
    built at the same time and would take the same next number; the
    reviewer may ask for a row at merge.
  - *The order's cuts stand:* no `section` by title, no `offset` with
    `max_chars`, no `include_workspace` on search.
- **Kind.** both. Tests: `tests/test_knowledge.py`.

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
    model, moving the sentence there would lose it. The trial of
    2026-11-12 did not answer this, so the order still waits.
- **Kind.** both.

### WO-21 — CLI ergonomics for agents *(open: CLI side done; MCP author waits on the budget, WO-20)*

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
- **Debate while building.**
  - *Built: the command line. Waiting: `author` on `grove_ingest_map`.* The
    tool list has 18 bytes left of its budget (R-GROK-3) and the barest
    form of the parameter, `"author": {"type": "string"}`, costs 30; written
    as on `grove_work_update` it costs 109. Nothing fits until WO-20 frees
    space, so the tool, its schema, its description and its result are
    untouched: `tools/list` is byte for byte what it was (16 366 bytes).
    Over MCP an `author` argument to `grove_ingest_map` is still refused as
    unknown, and an ingested map carries `GROVE_AUTHOR` from the
    registration's `env`, or no author.
  - *R-IF-10 is not met for this one parameter*, and its status says so.
    `Grove.ingest_map` takes `author` as an optional third argument with
    today's behaviour as the default; the tool's handler still passes two.
    **Closes the order:** the schema property, a `call_tool` test, the
    Authors paragraph of the README, and the status of R-GROK-1 and
    R-IF-10.
  - *The result of `ingest-map` is unchanged.* It has no `author` field; a
    new result field would show on both surfaces. The author is read back
    with `knowledge get`.
  - *A terminal on standard input is refused with `invalid`*, at once and
    before anything is read. Waiting for typed text is a prompt (R-IF-9),
    and to an agent whose shell has a terminal it is a hang with no output.
    *Consequence, accepted:* a person cannot type a note and end it with
    Ctrl-D; `cat | grove knowledge write ... --file -` still does that.
  - *Reading stops one byte past the 2 MB cap.* A pipe has no size to check
    first, and an endless one would otherwise fill memory. The body is then
    refused by the check every body passes, with the same message; nothing
    is cut short and stored. A named file is still read whole before that
    check, as before.
  - *The text is stored as it arrives*, like a file's: the newline a
    here-document ends with is kept, and bytes that are not UTF-8 are
    replaced. Nothing read (an empty pipe, `/dev/null`, a closed standard
    input) gets the existing answer, "body must not be empty".
  - *Unintended consequence, recorded:* `--file -` used to name a file
    called `-` in the working directory, and read it if it existed. That
    file is now `--file ./-`.
  - *Cut: `-` as the PATH of `ingest-map`.* A map's key and title come from
    its file name; a pipe has none, so it would need a `--key` too. A map
    is a file someone wrote; nothing is saved by not naming it.
  - *Cut: reading standard input when `--file` is left out.* A forgotten
    flag stays a usage error and never becomes a wait.
  - *On `PATH`: a link to `.venv/bin/grove`, not a second install.* The
    link is one command, uses the environment `uv sync` built from
    `uv.lock`, and follows `git pull && uv sync` with no further step. `uv
    tool install --editable` was tried and works, and the README says so in
    one sentence, with its cost: a second environment that does not read
    `uv.lock`. *Cut:* an install script or a `grove` command that writes
    the link (Grove would write outside its data directory, for two shell
    lines). A test makes the link in a temporary directory and runs `grove`
    by name from another one; it is skipped, visibly, where the command is
    not installed next to the interpreter.
  - *`CLAUDE.md` is not changed.* Its example still writes a note with
    `--file note.md`, which stays correct. Whether the brief should show
    `--file -` instead is left to the owner.
  - *No decision row yet.* What is settled here is recorded above; the row
    belongs with the change that closes the order.
  - Tests: 300 pass (293 before).
- **Kind.** both. Tests: `tests/test_cli.py`, `tests/test_knowledge.py`.

### WO-23 — Measure the heuristics and the search *(done)*

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
- **Debate while building.** One corpus (`fixtures/measure/`), one test
  file (`tests/test_measure.py`), no change under `src/`. Where the numbers
  show a weakness it is listed below as a candidate and nothing was changed.
  - *The numbers, measured on 2026-11-13.* Three projects (Python,
    TypeScript, Go), 51 true gaps listed by hand, taken together:

    | Kind | True gaps | Findings | Right | Precision | Recall |
    |---|---|---|---|---|---|
    | `declared_untested` | 24 | 21 | 7 | 0.33 | 7 of 24 = 0.29 |
    | `declared_unseen` | 6 | 22 | 2 | 0.09 | 2 of 6 = 0.33 |
    | `actual_undocumented` | 4 | 6 | 3 | 0.50 | 3 of 4 = 0.75 |
    | `map_untested` | 17 | 14 | 13 | 0.93 | 13 of 17 = 0.76 |

    Search, 16 notes and 26 queries, judged on the first ten results:
    recall 0.72, reciprocal rank 0.72, precision 0.74 (23 of the 31 notes
    returned were relevant). Of the 25 queries with a relevant note, 18
    found all of theirs and 7 found none. Whenever a relevant note came
    back, one was in first place. The one query that should find nothing
    found nothing.
  - *Read them as a line to hold, not as what to expect elsewhere.* The
    corpus is small and its author knew the heuristic. By project the
    spread is wide: in the project whose tests share few words with its
    README, all 5 untested statements are found (5 of 12 findings right);
    in the other two, 2 of 19 are found. `fixtures/measure/README.md`
    says how the lists were made and names the three changes made to the
    queries after the first run.
  - *What a true gap is had to be written down first.* The rules are in
    the corpus README. Two of them decide numbers: a limit that only says
    a feature is absent ("not supported") is not a gap, because no test
    could ever close it; and a module is documented when a document
    describes what it does, whether or not it names the file. A reader
    who disagrees with a rule can change the list and see what moves.
  - *Four kinds, not three.* "Per finding kind" includes `map_untested`,
    so each project has a map. The three kinds a scan computes are read
    before the map is ingested: a map adds items of its own to the
    comparison, and the lists were made from the projects' documents.
  - *The floors are the measured values cut to two decimals,* over the
    three projects together. At this size one finding more or less moves
    every number by more than 0.01, so each floor catches a single
    change. Per project there is no floor: one project has a single true
    gap of a kind.
  - *One test more than the order names: a floor may not go stale.* When
    a number rises, its floor stays behind, and a later fall back to the
    old value would pass. The test fails until the floor is raised, so an
    improvement shows in review as a changed number. It is one function
    and can be deleted if that is too strict.
  - *The measure is tested too.* A matching rule that counted every
    finding as right would report 1.00 for ever; one test feeds the
    scoring a wrong file, changed words and an unrelated sentence. The
    failure message of a floor lists the wrong findings and the missed
    gaps, and `uv run python tests/test_measure.py` prints them all.
  - *The fixture projects are real small programs.* Their own tests pass:
    the Python and Go ones were run with pytest and `go test`, the
    TypeScript ones through a stand-in for the test runner, which is not
    installed here. Grove's suite does not run them.
  - *Cut while building:* graded relevance and a rank-weighted score
    (with at most five notes returned there is nothing to grade); a
    stored copy of every finding (the failure message serves); measuring
    again after the map is ingested; measuring the `recommend` order.
  - Tests: 389 pass (381 before).
- **Candidates the numbers point to.** None is built or decided; each
  needs its own order and would be judged by this measure (WO-35).
  1. *One shared word silences a finding, and ordinary words do it.* In
     the TypeScript project 8 of 9 untested statements are silent because
     they share a word such as "book", "loan", "check", "never" or "back"
     with some test name: "Writes are atomic: the file is replaced, never edited in
     place" is silenced by the "never" of an unrelated test. The same
     rule hides 4 of the 6 promises that have no code (one word such as
     "label" or "catalogue" is also a symbol). Candidates: ask for more
     than one shared word, or a share of the statement's words; give less
     weight to a word most test names hold; add function words to the
     stop words.
  2. *A behaviour described in other words than the code's names reads
     as unseen.* 20 of 22 `declared_unseen` findings are wrong: 10 are
     behaviours that exist, 10 are sentences that promise nothing. The
     kind is already never recommended (D-09). Candidate: say in the
     description how weak it is, or rank it last in `gaps`.
  3. *Sentences that promise nothing are compared.* 11 of the 14 wrong
     `declared_untested` findings: thanks and history, which fall to
     `behaviour` by default; a limit that only says a feature is absent,
     which no test can silence; a row of a table that lists files; and
     "has no other dependency" or "with no configuration file", where
     "no" plus a noun counts as a promise before the setup signals are
     looked at. The other 3 have a test whose name uses other words.
  4. *A sentence that starts with a flag is glued to the one before.*
     After "path." the splitter wants a capital, a digit or a quote;
     `` `-json` `` has lost its backticks by then. Two untested statements
     were joined to a tested one and silenced with it.
  5. *A URL path makes a sentence `setup`.* "`/search?q=a`" is taken for
     a file path, so the sentence is never compared. It cost nothing
     here; the statement has a test.
  6. *`actual_undocumented` wants the file's name in the documents.* All
     3 wrong findings are in the project whose README describes
     behaviour without naming files, as with `calc.py` in `fixtures/tiny`;
     the one miss is `members.ts`, because the documents say "member" of
     a person.
  7. *Map: a heading called "Labels" is taken for the legend.* The
     Python project has address labels; everything under that heading
     is dropped. Also seen: a claim written "Untested: ..." is skipped
     (2 of the 4 misses; known, `BUILD_NOTES.md`); "nothing in
     `src/isbn.ts` is untested" becomes a finding; "has none" without
     the label is not read, which is by design.
  8. *Search: every word must be in the note.* 6 of the 7 queries that
     miss return nothing at all. Each is a question or a phrase with a
     word the note lacks: "how to name a test" fails on "to", "send mail
     to the customer" on "mail" where the note says "email". Candidates: leave
     function words out of the query; when all words find nothing, fall
     back to any word, ranked, and say so in the result.
  9. *Search: the words of a camel-case identifier do not find it.*
     "parse line" misses the note that names `ParseLine` and returns
     another. The whole identifier, an identifier with an underscore, a
     term with a hyphen and a number, a prefix and a plural for a
     singular all work.
- **Kind.** code (tests and fixtures only). Tests: `tests/test_measure.py`.

### WO-24 — Randomised tests for the parsers *(done)*

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
- **Debate while building.** One test file, three defects fixed, four
  patterns that had two or three copies now have one.
  - *The first version of the test passed on the defective code.* Random
    lines and documents alone, with the fixed seed, held no long paragraph
    of "[". A randomised test that would not have found the defect it is
    written against is decoration. Now every piece of the alphabet also
    gets one paragraph of 20 000 characters made of nothing else. With
    that, the test fails on the code before this order (the map reader:
    0.81 seconds against a bound of 0.45) and passes after it.
  - *Defect 1, found by the generator: a paragraph in a map.* A paragraph
    is joined before it is cleaned and has no length cap. The link, image
    and tag patterns read from every opener to the end of the text:
    40 000 characters of "[" in short lines took 9 seconds (18 under a
    labelled heading), a map may be 2 MB, and map ingest has no time cap.
    The patterns now stop at the next opener of their own kind and take
    linear time; 2 MB of the slowest input found takes about 2.5 seconds.
  - *Defect 2, found by a sweep run while building: the heading pattern.*
    Every line start with every piece of the alphabet at the line cap
    (7140 lines) showed that one line "# ####...x" of 5000 characters cost
    0.17 seconds in a document and 0.43 in a map: the pattern removed the
    closing "#"s by trying again after every character. The closing run is
    now removed in code (`scan.atx_heading`).
  - *Defect 3, found by defining the pattern once.* The knowledge outline
    in `service.py` had a third copy of the heading pattern, and a
    knowledge document has no line cap: one line of 40 000 characters took
    11 seconds on `knowledge get`. The outline now uses the one definition.
  - *Also made linear: the file-name pattern in `claims.py`* (22
    milliseconds for one hyphenated word of 5000 characters). It was the
    slowest path left and set the slope of the time bound. It names the
    same file as before.
  - *What "the same meaning" was checked against.* The old and the new
    patterns were run side by side on 400 000 generated lines: headings
    and file names never differed; inline cleaning differed on 90 lines,
    each with a doubled or unclosed opener. On 552 000 lines of real
    documentation and source on the build machine, 270 lines differed:
    a "<" that is not a tag (a generic type such as `Array<String>`, a
    comparison such as "<1.5.0" before a later tag) and link targets with
    parentheses, which are now read to their real end. Fixed cases hold the well-formed forms
    (`test_scan_robustness.py`).
  - *Defined once.* The fence, the heading, the list marker, the table
    separator and the thematic break are written in `scan.py`; `mapdoc.py`
    and the outline import them. A map still keeps a task box in an item's
    text and a document drops it: the two share the list marker, not the
    box. Making them agree would change what a map seeds; not this order.
    A test fails when any pattern is written in two modules
    (`test_invariants.py`). *One exception, named in the test:* the
    one-atom word pattern in `claims.py` and `mapdoc.py`; sharing it needs
    `mapdoc` to import `claims`, and the layering is a decision (R-QUAL-3).
  - *The time bound is absolute: 0.25 seconds plus 10 microseconds a
    character,* for the faster of two runs. The slowest input found costs
    1.5 microseconds a character, and no case of the fixed seed uses more
    than a tenth of its bound; forty other seeds found nothing. The bound
    sees a quadratic path as strong as defect 1 from 10 000 characters on.
    It does not see a mild one (the paragraph defect of WO-06 would need
    more than a megabyte) nor one line that is slow only below the cap;
    fixed cases hold those. *Weighed and left out:* comparing two sizes of
    one shape (the ratio is noise when both runs take a millisecond).
  - *Cases run smallest first,* so a path that grows too fast fails at the
    first size that shows it. On the old code the test failed in seven
    seconds instead of hanging.
  - *Cut: the sweep in the suite.* Thirty-six megabytes of input on every run
    for what three fixed cases now hold. **Would change the answer:** a
    new line pattern; run the sweep by hand then (the recipe in
    `docs/blueprint.md` says what to look for).
  - *Cut: a switch for the seed, a stored digest of the cases, a
    subprocess with a timeout per case.* To explore, change `SEED`. A
    digest would fail on every edit of the alphabet. The suite has no
    other timeout.
  - *Cut again: a property-testing library, a vendored corpus, a parser
    as oracle.* Fourteen awkward strings are in the alphabet (byte order
    mark, NUL, other line ends, a lone surrogate, the letters that match
    ASCII when a pattern ignores case).
  - *One existing test relied on the slowness* (a file of worst-case lines
    to outlast the time cap). No file is that slow now, so the test steps
    a clock by hand; it no longer depends on the machine.
  - *The README lists the constructs* under "Which Markdown is read", and
    names CommonMark and GitHub Flavored Markdown. Each line of the list
    has a sample in `test_extractors.py`, so the list cannot drift.
  - *The cost:* the suite runs 11 seconds instead of 6. The random test is
    4.4 of them: 343 documents, 3.1 MB, fifteen extractors, twice each.
  - *Seen on the way, not changed.* (1) A sentence stores its heading and
    its class reason whole: a 34 KB document under one 5000-character
    heading produced 9.9 MB of `extra`. Not a time defect; clipping it
    changes stored data and wants its own order. (2) The JavaScript
    test-name pattern is still quadratic below the line cap (6
    milliseconds a line at worst); the cap bounds it. (3) Map ingest still
    has no time cap; a cap would be a new result field.
- **Kind.** code.

### WO-25 — Protocol coverage *(done)*

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
- **Debate while building.** Two tests for the second era, one stored file
  with two tests, and the documents. No line of `src/` changed: the SDK
  already serves both eras, and what was missing was proof and a written
  account. No tool name, description, parameter or result field is
  touched; `tools/list` is the same 16 366 bytes.
  - *The hand trial had left out half of the envelope.* The note in
    `docs/analysis.md` names one key,
    `io.modelcontextprotocol/protocolVersion`. With that key alone every
    request is refused as invalid: `io.modelcontextprotocol/clientCapabilities`
    is required too (an empty object will do). The README and that note
    now name both.
  - *What the era test asserts.* No `initialize`; then `server/discover`
    (the version, the tools capability, the instructions, the server's
    name), `tools/list`, calls that succeed, a project created and
    scanned, two calls that fail, exit code 0 and a clean stdout. The tool
    list is compared in both eras with the tool table and with the stored
    schemas, so "the same sixteen tools in both eras" is a test and the
    stored file is tied to the bytes a client receives, not only to a
    Python object.
  - *One connection, one era.* A second test, not asked for in so many
    words: the first request decides the era, and a request of the other
    era gets a JSON-RPC error and leaves the connection usable. A client
    author needs exactly this sentence, the README now makes it, and a
    claim in the README wants a test. The error codes are the SDK's; if a
    later SDK changes them, the test fails and the README is read again.
  - *The stored schemas.* `tests/snapshots/tool_input_schemas.json`, one
    object from tool name to input schema, in table order, 9.7 KB. The
    test reports which tools differ, then a changed order of keys (the
    bytes a client receives change, though the meaning does not), then a
    changed layout. A second test feeds the comparison ten changed copies
    and asserts each is reported: a snapshot test that cannot fail is
    decoration.
  - *Updating is a command, not a switch.* `uv run python
    tests/test_tool_schemas.py --write`. *Left out:* an environment
    variable that makes the test rewrite the file (left set in a shell or
    in CI, the test would pass for ever), and a test that writes at all.
  - *Left out of the stored file: the tool descriptions.* The order says
    input schemas. Parameter descriptions are inside the schemas and are
    covered. The sixteen tool descriptions change with every wording fix;
    storing them would turn "update the snapshot" into a reflex, which is
    the opposite of a deliberate act. They keep their own guards (the size
    budget, the documents contract).
  - *Shutdown, measured before it was written down.* 150 runs in both eras
    (`BUILD_NOTES.md`). The order's sentence is true and incomplete: the
    reply is lost, no error is sent in its place, the exit code is 0, and
    a call that has started still finishes, so every project of every run
    was stored whether or not its reply arrived. The last part matters
    most to a client: after a lost reply, read before repeating a write.
    The README says so.
  - *Why shutdown has no test.* Which replies are lost is a race, and a
    test that fails now and then is a defect (R-QUAL-1). A call that is
    certain to be running would settle it; the one candidate found, a
    named pipe given as a map file, is refused before it is opened, and a
    hook in the product only to make a call hang is not worth having. The
    certain half is tested: five requests sent back to back are all
    answered while stdin stays open, in any order, matched by id.
  - *Not changed: delivering the lost replies.* It would mean keeping the
    SDK's loop alive after the end of input, in code Grove does not own,
    for clients that close early. No client is known to. Its own order,
    if one is ever shown to.
  - *The cuts stay cut, and are now visible.* Both stdio tests assert that
    no tool carries an `outputSchema` and no result a `structuredContent`
    (D-29). Offering them later means changing those lines on purpose.
  - *Seen on the way, not changed.* In the per-request era the SDK adds
    `resultType`, `ttlMs`, `cacheScope` and the server's name to every
    result. The whole `tools/list` line is 15 912 bytes on the wire there,
    inside the budget of R-GROK-3 (which measures the tool array with
    Python's default separators: 16 366).
  - *The cost:* three more server processes in the suite, 14 seconds
    instead of 13.
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
- **Done early, with WO-08.** The script refuses an agent session id in the
  tracked files and in the revision's commit message, with tests in
  `tests/test_gates.py` (clean commit passes; a link in a file and a link in
  a message are each refused). It was pulled forward because R-INV-15
  promised it, nothing enforced it, a session link had already reached a
  pull-request description once, and agent tools add such a line to commit
  messages by default. The tests asked for above belong in the same file.
  *Weighed and left out:* a hard-coded list of machine paths (naming a
  private path in a public script publishes it; that is what the local file
  is for), and reading pull-request descriptions (the script has no network
  and must not get one).
- **Debate.** *Cut:* a second, maintained secret scanner (another tool to
  install and keep in step, for patterns the script already has; reconsider
  if the script ever misses something real); a check for bidirectional
  control characters in source (no incident, no evidence of risk here).
- **Kind.** code.

### WO-27 — A security policy *(done)*

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
- **Debate while building.** One file of four parts, one paragraph in the
  README, one test. The owner gave the address (2026-11-13); it is the only
  one published, and the test fails if a second one appears in the file.
  - *No promise the project cannot keep.* The policy says in so many words
    that no response time and no bounty are promised. *Cut:* a table of
    supported versions (there is one version), a disclosure timetable, a
    key for encrypted mail (none exists).
  - *The trust paragraph names what is not finished* (R-SEC-4, R-SEC-5;
    WO-13); a policy that listed only what holds would mislead. It leaves
    how far each has come to the status column, so that WO-13 need not
    edit this file. One fact was added that section 9 does not state,
    after reading `db.py`: `grove.db` is not encrypted and gets the
    permissions of any new file.
  - *A pushed secret: rotate, tell, remove, close the hole.* Removal is an
    ordinary commit; rewriting history takes nothing back and is left to
    the owner. The hook's known gap (tip commit only, WO-26) is named.
  - *The audit is two commands in the policy, not a script and not a CI
    step.* It needs the network; `scripts/check` and the tests do not. Its
    tool is run with `uvx` and is no dependency. Run by hand on the locked
    set (38 packages, 2026-11-13): no known vulnerability. *Weighed and
    left out:* `uv audit` (marked experimental by `uv`; its lookup service
    could not be reached from the machine this was built on, so it was not
    shown to work); a scheduled audit in CI (a second workflow that fails
    when a report is published, not when the code changes; the policy says
    that none is scheduled). **Would change the answer:** a pin that stays
    vulnerable because nobody ran it.
  - *Copying `grove.db`: one way, tried.* With a connection open, a copy of
    `grove.db` alone lacked the last write and gave no error; after a
    killed process the log file stayed, and one `grove status` folded it
    in. Hence the check in the paragraph: copy when no `grove.db-wal` is
    beside the file. *Cut:* SQLite's own backup command as a second way
    (the brief tells agents to leave `grove.db` alone, and the tool was not
    there to try it); a backup command in Grove (WO-32).
  - *The test checks facts, not prose:* one address, the four headings,
    every pin in `pyproject.toml` exact and named. `SECURITY.md` joins the
    documents whose requirement and work-order ids must resolve.
  - *Cut, as the order decided:* a contributing guide, a release checklist,
    a commit-message convention. No code, tool description, parameter or
    result field changed.
- **Kind.** docs (+ `tests/test_docs_contract.py`).

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
