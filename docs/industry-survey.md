# Industry survey for Grove

Surveyed on 2026-11-12 and 2026-11-13. Source: the curated list
[sindresorhus/awesome](https://github.com/sindresorhus/awesome) at commit
`bc98e51` (dated 2026-09-02), and the lists it points to.

The question asked of every entry: *could this change Grove's requirements,
design or engineering practice?* Grove is a local, deterministic Python CLI
and MCP stdio server; it contains no model and makes no network call
(`REQUIREMENTS.md`, section 2). Those invariants are the filter.

## 1. How the list was walked

1. **The root list, completely.** All 671 linked lists in the root
   `readme.md` were read by name and description and put in one of two
   groups. Section 5 names every one of them, so nothing is silently skipped.
2. **48 lists read in full.** Each was cloned (shallow, on the
   survey dates) and every line read. Every heading in every one of these
   lists got a verdict: 1430 sections in total. Section 6 gives the
   commit and date of each copy.
3. **803 entries judged one by one** as *adopt*, *consider* or
   *tempting but wrong*. For 793 of them a script confirmed that the
   URL stands on the cited line of the cited list; the other 10
   are passages of a list's own text and carry no URL. The reading was done
   by five parallel reader agents under one written brief; their output was
   then checked mechanically and selected by hand.
4. **125 resources shortlisted** (section 3) and **52 rejected by
   name** (section 4).

**What this is not.** It is not a claim that every linked page was read.
This session could reach GitHub and package registries but no other
website, so linked pages were not opened. A statement about what a resource contains therefore comes from
the list's own one-line description, or from one of the two sources read
directly (section 2). Where a row relies on general background knowledge,
it says so. No star counts or popularity figures are quoted anywhere.

**What the root list does not have.** There is no list for the Model Context
Protocol, none for SQLite, and none for requirements engineering. The
relevant material was found inside other lists (coding-agent lists, the
general database lists, architecture and documentation lists). Things looked
for and not found in any list read: Keep a Changelog, RFC 2119 as an entry of
its own, the XDG directory specification, EARS requirement syntax, fitness
functions, OpenSSF Scorecard, SLSA, mutation testing for Python, and any
guide to SQLite WAL, backup or FTS5. Where this survey uses one of those, it
is general practice, not a finding of the survey.

## 2. Two sources read directly

Both are GitHub repositories, cloned on 2026-11-12.

| Source | Commit | What was read | What it changes |
|---|---|---|---|
| [modelcontextprotocol/modelcontextprotocol](https://github.com/modelcontextprotocol/modelcontextprotocol) | `06e9234` (2026-11-12) | `docs/specification/2025-11-25/server/tools.mdx`, `docs/specification/2026-07-28/changelog.mdx`, `.../basic/transports/stdio.mdx`, the `ToolAnnotations` schema | (a) Tool results may carry `structuredContent` and tools an `outputSchema`; a server that returns structured content should also return the JSON as text, which is what Grove returns today → WO-25. (b) The `2026-07-28` revision removes the `initialize` handshake, requires `server/discover`, and says servers should list tools in a deterministic order; Grove's server answered all three in a hand-run probe, with no test yet → R-QUAL-7, WO-25. (c) The same revision deprecates the protocol's logging feature in favour of stderr for stdio servers, which is what Grove does → R-INV-8. (d) The security section says servers must validate inputs and sanitise outputs; Grove validates inputs and passes stored text through verbatim → R-SEC-4, WO-13. (e) Annotations are hints; Grove sets `readOnlyHint`, `destructiveHint=false` and `openWorldHint=false` and does not set `idempotentHint` → WO-20. |
| [cli-guidelines/cli-guidelines](https://github.com/cli-guidelines/cli-guidelines) | `697d6a2` (2026-05-15) | `content/_index.md` (the text published as the Command Line Interface Guidelines) | Confirms: zero exit code on success and non-zero on failure; primary and machine-readable output on stdout; messages on stderr. Asks for: `-` to read from stdin where a file is expected (Grove's `knowledge write --file -` fails today → WO-21); additive changes only (→ R-COMPAT-2); configuration precedence of flags over environment (Grove: `--home` over `$GROVE_HOME` → R-HOME-1). Not adopted: the XDG directory layout, because `~/.grove` is already the documented default. |

## 3. The shortlist

Each row gives the resource, where in the lists it was found, and the
practice or requirement it suggests. `R-…` ids refer to `REQUIREMENTS.md`,
`WO-…` ids to `docs/work-orders.md`.

**A row is not a recommendation.** Being on this list means a resource was
worth weighing, no more. Each suggestion was then argued on three questions:
is it the simplest thing that serves Grove, what does it cost on every
call, and what could it break or make permanent. Where that argument went
against a suggestion, the row says **Declined**, **Deferred** or **Left
out** and why; the fuller debate is with the work order it names. A
resource existing is not a reason to change Grove.

### A. The agent-facing interface: MCP, tool descriptions, instruction files

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [Model Context Protocol](https://modelcontextprotocol.io/) | awesome-generative-ai:243 | The protocol Grove serves. Suggests: name the specification revisions Grove is verified against and re-check on every SDK bump. Read directly (see section 2): the `2026-07-28` revision removes the handshake, adds `server/discover`, and asks for a deterministic tool order. → R-QUAL-7, WO-25. |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | awesome-python:156 | Grove's one protocol dependency. Suggests keeping to the official SDK, pinned exactly, stdio only. → R-INV-14. |
| [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | awesome-claude-code:121 | The list describes it as guidance on just-in-time retrieval and note-taking. That is Grove's job description. Suggests: every result is bounded by default, with a visible way to get more. → R-GROK-4. |
| [context-tax](https://github.com/gethrbr/context-tax) | awesome-claude-code:787 | Suggests measuring what the sixteen descriptions cost on every turn and setting a budget. Measured here: 15.1 KB for `tools/list`. → R-GROK-3 (now a test), WO-20. |
| [MCP Probe Kit](https://github.com/mybolide/mcp-probe-kit) | awesome-gemini-cli:425 | Suggests a test that lists the tools over real stdio and compares names and schemas with a stored snapshot. Grove has the names test; a schema snapshot is missing. → R-INV-9, WO-25. |
| [Writing a Good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md) | awesome-claude-code:102 | Suggests auditing each line of `CLAUDE.md` (would the agent err without it?) and keeping detail in linked documents. Applied in this change: `CLAUDE.md` points to `REQUIREMENTS.md` instead of repeating it. → R-CC-1. |
| [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices) | awesome-claude-code:111 | The official source for instruction-file practice; cite it as the basis for `CLAUDE.md` conventions. → R-CC-1. |
| [Ctxlint](https://github.com/ctxlint/Ctxlint) | awesome-claude-code:852 | Suggests testing that every command quoted in an instruction file still exists. Applied here without the tool: a test parses every `grove ...` line of `CLAUDE.md` with the real argument parser. → `test_docs_contract.py`. |
| [LintLang](https://lintlang.ai/) | static-analysis:2320 | A linter for natural-language agent instructions and tool descriptions, per the list. Suggests treating tool descriptions as tested artefacts. **Declined:** one focused test covers sixteen descriptions (WO-03). |
| [agnix](https://github.com/agent-sh/agnix) | awesome-claude-code:846 | Same idea for `CLAUDE.md`, `AGENTS.md` and MCP configuration. A candidate dev-only check. **Declined:** a dependency for what one test already checks (WO-03). |
| [agents-md-cookbook](https://github.com/Taiizor/agents-md-cookbook) | awesome-claude-code:843 | Grove has two agent clients and only a `CLAUDE.md`. Suggests an `AGENTS.md` generated from, or pointing to, the same source. Whether Grok Bot reads one is unverified. **Deferred:** only if Grok Bot is shown to read one (WO-11, WO-21). |
| [Pluribus](https://github.com/caioribeiroclw-pixel/pluribus) | awesome-gemini-cli:236 | Same convention from the other agent's ecosystem: one canonical source, many instruction files. **Deferred** with the row above (WO-21). |

### B. CLI design and the JSON contract

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [Command Line Interface Guidelines](https://clig.dev/#guidelines) | guides:228 | The CLI design guide. Read directly from its GitHub source (section 2). It supports what Grove does (machine-readable output on stdout, messages on stderr, zero/non-zero exit) and asks for two things Grove lacks: `-` for stdin where a file is expected, and additive-only change. → R-IF-1, R-COMPAT-2, WO-21. Its advice to follow the XDG directory layout is **not** adopted: `~/.grove` is part of the compatibility surface (R-HOME-1). |
| [JSON Schema](https://json-schema.org/specification) | awesome-standards:51 | Suggests publishing schemas for the envelope and each tool's `data`, and validating results against them in tests. MCP has `outputSchema` for this. **Declined for now:** output schemas would enlarge the tool list and structured results double the payload, with no shown need (WO-25, D-29). |
| [JSON-RPC](https://www.jsonrpc.org/specification) | awesome-standards:44 | MCP rides on JSON-RPC. Suggests keeping Grove's own `error.code` vocabulary clearly apart from protocol errors. → R-IF-3, R-IF-4. |
| [JSEND](https://github.com/omniti-labs/jsend) | awesome-standards:64 | Prior art for a success/fail/error envelope. Compared, not adopted: Grove's envelope is frozen (R-INV-10). |
| [SemVer Spec](https://semver.org/) | awesome-standards:130 | Suggests writing down what the public interface is, so that a version number means something. → section 3 of `REQUIREMENTS.md`. |
| [jq](https://github.com/stedolan/jq) | awesome-cli-apps:594 | Suggests documenting `jq` recipes for the envelope and testing that stdout is exactly one JSON document on success and on error. The second half is tested today. → R-IF-1. |
| [RFC-3339 vs ISO-8601](https://ijmacd.github.io/rfc3339-iso8601/) | awesome-falsehood:110 | Suggests naming one timestamp format. → R-IF-7. |
| [tldr](https://tldr.sh/) | awesome-naming:119 | Example-first help. Suggests one worked example per operation in `--help` and in each tool description. **Declined:** sixteen examples cost more context than they save (WO-20). |

### C. Requirements, architecture documents, decisions, traceability

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [Architectural Decision Records](https://adr.github.io/) | awesome-software-architecture:67 | Suggests recording each decision with its context and consequences. Applied here as a numbered decision log in `docs/blueprint.md`, which also absorbs the "decisions the spec left open" from `BUILD_NOTES.md`. |
| [ARCHITECTURE.md](https://matklad.github.io/2021/02/06/ARCHITECTURE.md.html) | awesome-readme:140 | The list's section says source-code maps, invariants and design decisions are what an architecture file needs. Applied here: `docs/blueprint.md` has exactly those parts. |
| [The C4 Model](https://c4model.com/) | awesome-software-architecture:82 | A levelled vocabulary (context, containers, components, code). Used as the outline of the blueprint, not as a tool. |
| [arc42](https://arc42.org/) | awesome-software-architecture:66 | A fixed section template for architecture documents. Considered; the blueprint keeps a smaller outline. |
| [What nobody tells you about documentation](https://www.divio.com/blog/documentation/) | awesome-engineering-team-management:829 | Four kinds of documentation: tutorials, how-to guides, explanation, reference. Suggests giving each Grove document one role, and, for the scanner, that only reference-type text should become *declared* claims. → WO-10, WO-22. |
| [poliastro](https://docs.poliastro.space/) | awesome-read-the-docs:84 | Carries the Diátaxis link for the same four-part model; a second source for the row above. |
| [sphinx-needs](https://sphinx-needs.readthedocs.io/) | awesome-read-the-docs:57 | The list shows it only as a documentation example. From general knowledge (not verified here) it models requirements as typed items with ids and links to tests. Suggests the data model for work-item links, not the dependency. **Taken in the smallest form:** free-form references on work items (WO-15). |
| [Living Documentation by Design, with Domain-Driven Design](https://leanpub.com/livingdocumentation) | awesome-ddd:94 | Documentation that is checked against the code, not trusted. This is Grove's core idea; a source for wording about doc drift. |
| [Specification by Example](https://www.manning.com/books/specification-by-example) | awesome-ddd:77 | Requirement → example → test. Suggests that an explicit link (a requirement id in a test name) should beat token overlap. **Deferred** until excludes and measurement exist (WO-22). |
| [Mycelium](https://github.com/haabe/mycelium) | awesome-claude-code:615 | The list describes a requirement record built from a few fixed questions plus a decision log. Suggests fixed fields for work orders; `docs/work-orders.md` uses goal, rationale, acceptance. |
| [CommonMark](https://commonmark.org/) | awesome-markdown:217 | Grove reads Markdown with hand-written patterns. Suggests naming the specification and listing which constructs are read and which are not. → WO-24. |
| [GitHub Flavored Markdown Specifications](https://github.github.com/gfm/) | awesome-markdown:218 | Tables and task lists come from this dialect; maps and READMEs use them. Same requirement as above. → WO-24. |
| [markdown-it-py](https://github.com/executablebooks/markdown-it-py) | awesome-markdown:110 | A CommonMark parser in Python. Suggested use: a development-only oracle for differential tests of the scanner. As a runtime dependency it is rejected (R-INV-14). **Declined:** the scanner differs from a parser by design, so most differences would be noise (WO-24). |
| [BlockWatch](https://github.com/mennanov/blockwatch) | static-analysis:1917 | Keeps code and documentation in sync by linting. Applied here in a smaller form: tests that tie the README, the blueprint and the tool descriptions to the code (`test_docs_contract.py`). |
| [Conventional Commits](https://www.conventionalcommits.org/) | awesome-standards:124 | Machine-readable commit types. Considered for the changelog; not required yet. **Declined:** nothing consumes it (WO-27). |

### D. Work items, review, definition of done

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [There Are No Bugs, Just TODOs](https://almad.blog/essays/no-bugs-just-todos/) | awesome-engineering-team-management:743 | The list's summary: a tracker must show ownership, queue position, state, breakdown and closing; priority and severity fields add little. A checklist for Grove's work-item model, which has state and author but no order, breakdown or history. **Taken in part:** history and references (WO-14, WO-15); no priority or severity fields. |
| [How to do a code review](https://google.github.io/eng-practices/review/reviewer/) | awesome-code-review:51 | The best single source in the lists for what a reviewer checks. Suggests a short, fixed review checklist recorded on a work item before it leaves `review`. **Not built into Grove:** a review is recorded as a history note with its author (WO-14); a checklist can live as a knowledge document. |
| [Feedback Ladders: How We Encode Code Reviews at Netlify](https://www.netlify.com/blog/2020/03/05/feedback-ladders-how-we-encode-code-reviews-at-netlify/) | awesome-code-review:48 | A small closed vocabulary for how binding a review comment is. Fits a field on a review note. **Declined** as a field; it is a convention for the text of a note (WO-15). |
| [Ship Small Diffs](https://blog.skyliner.io/ship-small-diffs-741308bec0d1) | awesome-code-review:56 | Small changes review better. Suggests one work item per reviewable change. → `docs/work-orders.md` sizing. |
| [An experiment to assess the cost-benefits of code inspections in large scale software development (Porter, Siy, Toman & Votta, 1997)](http://laser.cs.umass.edu/courses/cs521-621.Fall10/documents/PorterSiyetal.pdf) | awesome-code-review:23 | Per the list: most of the benefit of inspection comes from one asynchronous pass. Supports a single `review` state with a recorded reviewer who is not the author. → R-WORK-2, section 11. |
| [presence](https://github.com/sara-star-quant/presence) | awesome-claude-code:694 | Suggests that `done` needs recorded test evidence. Grove records; it does not run tests. **Declined as a field:** evidence goes into a history note (WO-14, WO-15); Grove records and does not block. |
| [isitdone](https://github.com/raimondasl/isitdone-gemini) | awesome-gemini-cli:178 | Same rule from the other ecosystem: done means the project's real checks passed on the exact tree. **Kept as a convention** in section 11.2 of the requirements, not as a feature. |
| [Concord MCP](https://github.com/Get-Concord-AI/concord-mcp) | awesome-gemini-cli:129 | A local work-state server for several agents. Raises the question Grove has not answered: who owns an `in_progress` item. **Answered without locks:** the history shows who touched an item last (WO-14). |
| [Cookie licking](https://devblogs.microsoft.com/oldnewthing/20091201-00/?p=15843) | awesome-naming:145 | Names a failure mode of shared work lists: claimed, then abandoned. Suggests showing the age of `in_progress` items (never changing them automatically). → WO-29. |
| [Blameless PostMortems and a Just Culture](https://codeascraft.com/2012/05/22/blameless-postmortems/) | awesome-sre:366 | Suggests a short blameless note when a gate fails late or a finding proves wrong, stored as a knowledge document. No code needed. |
| [A collection of postmortem templates](https://github.com/dastergon/postmortem-templates) | awesome-sre:375 | A source for one minimal template for such notes. |
| [The Checklist Manifesto: How to Get Things Right](http://atulgawande.com/book/the-checklist-manifesto/) | awesome-sre:172 | Design rules for short checklists. Basis for the short definition of done in `REQUIREMENTS.md` section 11. |

### E. Testing practice

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [hypothesis](https://github.com/HypothesisWorks/hypothesis) | awesome-python:690 | Property-based testing. Suggested targets: the tokeniser, the Markdown and map readers, FTS query quoting, "a cap is always reported". Development-only. **Deferred:** a seeded generator from the standard library comes first (WO-24). |
| [coverage](https://github.com/coveragepy/coveragepy) | awesome-python:715 | Measured here: 90 % at the reviewed commit, 92 % with this change. **A floor was declined:** a number gate invites tests written for the number (WO-12). |
| [Bats](https://github.com/bats-core/bats-core) | awesome-testing:244 | `scripts/check-publish` guards every push and has no tests. Suggests testing it (a planted fake secret fails; a clean tree passes), with this tool or from pytest. → WO-26. |
| [Naughty Strings](https://github.com/minimaxir/big-list-of-naughty-strings) | awesome-testing:310 | A corpus of awkward strings. Suggests pushing each through keys, titles, bodies, queries and scanned files. **Declined:** a dozen hand-picked strings do the job without a vendored corpus (WO-24). |
| [test-inventory](https://github.com/Huldoser/test-inventory) | awesome-testing:270 | A static inventory of tests with their state (skipped, expected-fail) and reasons. Grove's tests layer has names only. **Left out:** stored test states go stale at the next edit (WO-31). |
| [VeriSpec](https://github.com/godikemahesh/verispec) | awesome-testing:253 | The only entry in the testing list about spec-to-test traceability. A comparison point for WO-22. |
| [behave](https://github.com/emirmrkaljevic/behave) | awesome-testing:252 | Golden tests of a CLI. Suggests replaying the same cases against the CLI and the MCP server and comparing envelopes. **Declined:** the CLI and the MCP path share one wrapper, so the comparison would prove the obvious (WO-25). |
| [The Fuzzing Book](https://www.fuzzingbook.org/) | awesome-fuzzing:21 | The reference for fuzzing parsers that take untrusted input. → WO-24. |
| [SlowFuzz: Automated Domain-Independent Detection of Algorithmic Complexity Vulnerabilities, 2017](https://arxiv.org/pdf/1708.08437.pdf) | awesome-fuzzing:568 | Fuzzing for algorithmic slowness, not crashes. Exactly the class of defect found in Grove's patterns during this survey (see `docs/analysis.md`). → R-SCAN-7, WO-24. |
| [RegreSQL](https://github.com/dimitri/regresql) | awesome-db-tools:297 | Regression tests for query results. Suggests golden results for knowledge search so that ranking changes show up in review. → WO-23. |
| [bats](https://github.com/sstephenson/bats) | awesome-tap:76 | A second pointer to shell-script testing, and, with the rest of this list, a candidate result format if the tests layer ever reads results. **Taken:** tests for the publish script (WO-26). **Left out:** reading result files (WO-31). |

### F. Parsing robustness: regular expressions, Unicode, paths, hidden text

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [Runaway Regular Expressions: Catastrophic Backtracking](https://www.regular-expressions.info/catastrophic.html) | awesome-regex:264 | The checklist for superlinear backtracking. Applied in this change: several of Grove's Markdown patterns were quadratic on long lines; one is rewritten and a line-length cap now bounds the rest. → R-SCAN-7. |
| [Python: re](https://docs.python.org/library/re.html) | awesome-regex:215 | The reference for the engine Grove uses. From general knowledge (not verified here), possessive quantifiers and atomic groups are available in current Python and remove some backtracking without a dependency. → WO-24. |
| [recheck](https://github.com/makenowjust-labs/recheck) | awesome-regex:292 | A checker for this defect class, for JavaScript-flavoured patterns per the list. Advisory only for Python patterns. |
| [RE2](https://github.com/google/re2) | awesome-regex:246 | A non-backtracking engine. As a runtime dependency it would be a compiled package; rejected for v0 (R-INV-14). The line cap gives the bound instead. |
| [Composing & Decomposing: decompositions / normalization forms](http://unicode.org/versions/Unicode8.0.0/ch03.pdf#page=44) | awesome-unicode:174 | Normalisation. Suggests choosing one normal form at every place where equality matters (keys, names, stored paths). Grove does none today. **Left out:** keys and names are ASCII by validation, so there is nothing to normalise (WO-33). |
| [Unicode Myths (Mark Davis slides)](http://macchiato.com/slides/UnicodeMyths.pdf) | awesome-unicode:178 | Caseless comparison needs case folding, not lower-casing. Grove lower-cases. **Left out:** tokens are ASCII by pattern, where lower-casing and folding agree (WO-33). |
| [ID_START / ID_CONTINUE](https://codepoints.net/search?IDS=1) | awesome-unicode:557 | Identifier characters beyond ASCII. Grove's tokeniser is ASCII-only; suggests declaring that and counting what it skipped. **Taken as one sentence** in the README's limits; counting skipped identifiers was declined (WO-33). |
| [Myths about File Paths](https://yakking.branchable.com/posts/falsehoods-programmers-believe-about-file-paths/) | awesome-falsehood:239 | Suggests writing down the path rules: how equality is decided, what happens with non-UTF-8 names, and containment of the data directory. **Taken in part:** containment of the data directory (WO-09). The rest was left out (WO-33). |
| [Falsehoods about text](https://wiesmann.codiferes.net/wordpress/archives/30296) | awesome-falsehood:163 | A checklist for excerpting and key handling. **Left out** (WO-33). |
| [Truths programmers should know about case](https://www.b-list.org/weblog/2018/nov/26/case/) | awesome-falsehood:263 | A second source for "fold, do not lower". **Left out:** see the rows above (WO-33). |
| [Falsehoods about Time](http://infiniteundo.com/post/25326999628/falsehoods-programmers-believe-about-time) | awesome-falsehood:97 | Suggests that revision order must not depend on the clock. Grove orders by revision number and row id. → R-IF-7, R-KNOW-2. |
| [Don't you (forget NLP): Prompt injection with control characters in ChatGPT](https://dropbox.tech/machine-learning/prompt-injection-with-control-characters-openai-chatgpt-llm) | awesome-prompt-injection:43 | Control characters as an injection carrier. Suggests a stated, reported policy for control characters in text Grove returns. **Declined:** a new field on six tools for a risk the client is better placed to handle (WO-13). |
| [Trojan Source](https://trojansource.codes/) | awesome-cicd-attacks:90 | Bidirectional and format characters hide meaning from reviewers. Suggests rejecting them in Grove's own source and surfacing them in scanned text. **Declined:** no incident and no evidence of risk here (WO-13, WO-26). |
| [CVE-2024-26150 Security Notice](https://backstage.io/blog/2024/02/28/security-notice/) | awesome-backstage:120 | A path-traversal fix in a tool that takes paths from templates. A reminder for `--root`, `--file` and `path` arguments that arrive from agents. **Taken in part:** the data-directory guard (WO-09) and the file-type limit on map ingest (WO-13). |

### G. Search and the evaluation of heuristics

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [Introduction to Information Retrieval](http://www-nlp.stanford.edu/IR-book/) | awesome-information-retrieval:22 | The textbook for tokenising, stemming, ranking and, above all, evaluation. → WO-23. |
| [Cranfield Collections](http://ir.dcs.gla.ac.uk/resources/test_collections/cran/) | awesome-information-retrieval:54 | The method, not the data: documents, queries, relevance judgments. Suggests a small checked-in collection for knowledge search and a labelled fixture set for each finding kind. `BUILD_NOTES.md` says precision and recall were never measured. → R-QUAL-10, WO-23. |
| [Falsehoods about Search](https://opensourceconnections.com/blog/2019/05/29/falsehoods-programmers-believe-about-search/) | awesome-falsehood:235 | A review checklist for `grove search`: stemming surprises on identifiers, what an empty result means. → WO-23. |

### H. Storage: SQLite, migrations, backup

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [sqlite3](https://docs.python.org/3/library/sqlite3.html) | awesome-python:461 | The standard-library driver Grove uses. Keep. Suggests saying clearly when the linked SQLite lacks FTS5 (today the first open fails with a generic `io` error). |
| [Sqitch](https://github.com/sqitchers/sqitch) | awesome-db-tools:174 | Pairs every change with a verify step. Suggests a test per migration that upgrades from the previous version; Grove has one for migration 2. → R-INV-7, section 11. |
| [Atlas](https://github.com/ariga/atlas) | awesome-db-tools:161 | Schema inspection and diff. Suggests a test that a database migrated step by step equals one created fresh. **Taken:** as a test alongside the next migration (WO-10). |
| [tbls](https://github.com/k1LoW/tbls) | awesome-db-tools:197 | A data dictionary with a drift check. Applied here in small: `docs/blueprint.md` lists every table and a test compares that list with the real schema. |
| [sqlite-utils](https://github.com/simonw/sqlite-utils) | awesome-db-tools:144 | A maintainer's tool for inspecting a *temporary* home. Never part of the product, and never pointed at the real `grove.db` (the `CLAUDE.md` rule). |
| [Litestream](https://github.com/benbjohnson/litestream) | awesome-db-tools:479 | Rejected as a feature (replication to remote storage breaks R-INV-1). It exposes a real gap: there is no stated backup procedure for a WAL-mode file. **Taken as documentation only:** a paragraph on copying the file safely (WO-27). |

### I. Security: untrusted text, secrets, supply chain, CI hardening

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [OWASP GenAI LLM Top 10 (2026)](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) | awesome-prompt-injection:31 | The taxonomy to name in a threat model. Grove contains no model, but it feeds text to models. → R-SEC-4, WO-13. |
| [Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection](https://arxiv.org/abs/2302.12173) | awesome-prompt-injection:68 | The primary citation for indirect prompt injection: instructions planted in content that an assistant later retrieves. Grove retrieves README sentences, map text and other agents' notes. → WO-13. |
| [Indirect Prompt Injection Through MCP Tools: A Defense Guide](https://www.stackone.com/blog/indirect-prompt-injection-mcp-tools-defense) | awesome-prompt-injection:51 | The closest match in all the lists: text returned by MCP tools that was written outside the trust boundary. Suggests classifying the sixteen tools by whether their result can carry such text. → WO-13. |
| [Why content-based prompt-injection detection has a structural blind spot](https://dev.to/churik5/i-tried-to-break-my-own-mcp-prompt-injection-detector-one-class-of-attack-walks-straight-through--4534) | awesome-prompt-injection:53 | A warning for the design: an in-band "this is data" marker can be forged by the stored text. Suggests marking provenance in a separate field that Grove sets. → WO-13. |
| [Agents Rule of Two: A Practical Approach to AI Agent Security](https://ai.meta.com/blog/practical-ai-agent-security/) | awesome-prompt-injection:32 | Restates Grove's invariants as a security property: Grove supplies untrusted input to an agent, so Grove itself must never add outbound actions. Supports R-INV-1 and R-INV-5. |
| [Design Patterns for Securing LLM Agents against Prompt Injections](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/) | awesome-prompt-injection:37 | Design patterns for isolating untrusted content on the client side. Suggests keeping Grove's result shape friendly to them. → WO-13. |
| [Anyone can Access Deleted and Private Repository Data on GitHub](https://trufflesecurity.com/blog/anyone-can-access-deleted-and-private-repo-data-github) | awesome-cicd-attacks:21 | Anything pushed to a public repository must be treated as exposed for good. The pre-push hook checks only the tip commit of each ref. → WO-26. |
| [Hidden GitHub Commits and How to Reveal Them](https://neodyme.io/en/blog/github_secrets/) | awesome-cicd-attacks:27 | A second source for the same conclusion; belongs in an "if a secret was pushed" procedure. → WO-27. |
| [Git hooks documentation at git-scm.com](https://git-scm.com/docs/githooks) | awesome-git-hooks:119 | The reference for the hook's contract. Grove's hook already reads the remote SHA and ignores it; using it would allow checking the whole pushed range. → WO-26. |
| [Gitleaks](https://github.com/zricethezav/gitleaks) | awesome-devsecops:238 | A maintained secret scanner as a second line behind the hand-written patterns. Development or CI only. **Declined for now:** another tool to keep in step for patterns the script already has (WO-26). |
| [Proactive Controls](https://owasp.org/www-project-proactive-controls/) | awesome-devsecops:81 | Ten controls; the right size to walk once and record which apply. **A one-off reading**, not a work order. |
| [Python chapter of Fedora Defensive Coding Guide](https://docs.fedoraproject.org/en-US/defensive-coding/programming-languages/Python/) | awesome-appsec:700 | A short Python-specific list of things to avoid. Suggests one recorded review of `sf_grove` against it. **A one-off reading**, not a work order. |
| [Bandit](https://github.com/PyCQA/bandit) | awesome-devsecops:308 | The Python security linter. Run here for observation: it reports the f-string SQL in `service.py`; each case was read and is built from fixed fragments with bound values. → R-SEC-2, WO-12. |
| [pip-audit](https://github.com/pypa/pip-audit) | awesome-python:1197 | Audits pinned dependencies against known vulnerabilities. With exact pins nothing updates by itself, so a scheduled audit is how a bad pin gets noticed. Needs the network, so it is never part of the product or the test suite. → WO-27. |
| [Statement on event-stream compromise" (under @dominictarr, scuttlebot and others)](https://gist.github.com/dominictarr/9fd9c1024c94592bc7268d36b8d83b3a) | awesome-maintainers:43 | A maintainer's account of a dependency compromise. Supports the two-dependency policy and suggests writing down how updates are reviewed. → R-INV-14, WO-27. |
| [Keeping your GitHub Actions and workflows secure Part 1: Preventing pwn requests](https://securitylab.github.com/research/github-actions-preventing-pwn-requests/) | awesome-cicd-attacks:50 | CI rule for a public repository: test pull requests with the `pull_request` event only. → WO-08. |
| [Keeping your GitHub Actions and workflows secure Part 2: Untrusted input](https://securitylab.github.com/research/github-actions-untrusted-input/) | awesome-cicd-attacks:51 | CI rule: never interpolate pull-request titles or branch names into scripts. → WO-08. |
| [PPE — Poisoned Pipeline Execution](https://medium.com/cider-sec/ppe-poisoned-pipeline-execution-34f4e8d0d4e9) | awesome-cicd-attacks:53 | Names the attack: the test job runs code from the pull request, so it must hold no secrets and a read-only token. → WO-08. |
| [The GitHub Actions Worm: Compromising GitHub Repositories Through the Actions Dependency Tree](https://www.paloaltonetworks.com/blog/prisma-cloud/github-actions-worm-dependencies/) | awesome-cicd-attacks:74 | Pin every action to a full commit SHA. → WO-08. |
| [zizmor](https://github.com/zizmorcore/zizmor) | awesome-cicd-attacks:111 | A linter for workflow files, to run from the first workflow commit. **Declined as a requirement:** for a workflow of twenty lines, reading it against the rules above is enough (WO-08). |
| [actionlint](https://rhysd.github.io/actionlint) | static-analysis:2634 | A second workflow linter. **Declined** with the row above (WO-08). |

### J. Quality gates for the repository itself

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [ruff](https://github.com/astral-sh/ruff) | awesome-python:666 | One tool for lint and format, development-only. Run here for observation: 22 lint findings (mostly import order), and 22 of 24 files would be reformatted. **Taken for error-class rules only; reformatting declined:** churn in nearly every file for no change in behaviour (WO-12). |
| [mypy](https://github.com/python/mypy) | awesome-python:677 | A type checker. Run here for observation: 4 reports, all optional-string narrowing in `service.py`; each was read and none is a defect. **Declined as a gate** (WO-12). |
| [PEP-586](https://www.python.org/dev/peps/pep-0586/) | awesome-python-typing:164 | Suggests typing the closed sets (status, layer, kind, error code) as literals. **Declined:** see the row above (WO-12). |
| [PEP-589](https://www.python.org/dev/peps/pep-0589/) | awesome-python-typing:165 | Suggests typing the envelope and row shapes, with no runtime cost. **Declined:** boilerplate over code whose shapes the tests already pin (WO-12). |
| [import-linter](https://github.com/seddonym/import-linter) | awesome-python:659 | Enforces import rules between modules. Applied here without the dependency: a standard-library test checks Grove's layering and forbids network and process modules (`test_invariants.py`). → R-QUAL-3, R-INV-1. |
| [shellcheck](https://www.shellcheck.net) | static-analysis:1739 | Run here for observation on the two bash files: three warnings (one unused variable in `scripts/check-publish`, two unused loop variables in the hook). **Taken** (WO-12, WO-26). |
| [shfmt](https://github.com/mvdan/sh) | awesome-shell:434 | A formatter for the two bash files. **Declined:** two short files do not need a formatter. |
| [Use the Unofficial Bash Strict Mode (Unless You Looove Debugging)](http://redsymbol.net/articles/unofficial-bash-strict-mode/) | awesome-shell:454 | A secret check must fail closed. Both scripts already use `set -euo pipefail`. |
| [Greg Wooledge's (aka "greycat") wiki](https://mywiki.wooledge.org) | awesome-shell:449 | The review checklist for scripts that iterate over file names and commit ranges. A reading for whoever changes the hook (WO-26). |
| [codespell](https://github.com/codespell-project/codespell) | static-analysis:3400 | Spelling matters more for Grove than for most projects: a misspelt word in a doc or an identifier silently lowers token overlap. **Declined:** low yield for a new dependency (WO-12). |
| [continuousIntegration](http://martinfowler.com/articles/continuousIntegration.html) | awesome-ciandcd:44 | The definition of the practice: one automated, self-testing build per change, kept fast. Grove has none. → R-QUAL-9, WO-08. |
| [actions/checkout](https://github.com/actions/checkout) | awesome-actions:65 | First-party checkout action; pin by SHA. → WO-08. |
| [pre-commit](https://github.com/pre-commit/pre-commit) | awesome-python:664 | A hook framework. Considered and not adopted: `core.hooksPath` with one bash script needs no extra dependency. |
| [uv](https://github.com/astral-sh/uv) | awesome-python:1119 | Already in use. Suggests that gates run against the frozen lock, so a gate never resolves new versions. → WO-08. |

### K. Close prior art: local memory and work tools for agents

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [LWC](https://github.com/JanYork/llm-wiki-cli) | awesome-gemini-cli:367 | The nearest design twin by the list's description: bounded recall, citations, atomic writes, a read-only stdio server. A checklist to hold Grove against. |
| [LLMSlim](https://github.com/Thanatos9404/llmslim) | awesome-gemini-cli:415 | Local SQLite, stdio, no model. Suggests a caller-supplied size budget on get and search, reported back, as an alternative to fixed caps. **Declined:** a second size limit for clients to reason about; one start line is enough (WO-19). |
| [Selvedge](https://github.com/masondelan/selvedge) | awesome-claude-code:700 | Stdio MCP plus local SQLite that records *why* a change was made. Suggests linking a note to a work item or commit. **Taken in the smallest form:** a reference on a work item (WO-15). |
| [fable](https://github.com/grooverLab/fable) | awesome-claude-code:676 | Suggests "recall is byte-identical" as a tested property of knowledge revisions. Grove's `--full` read is tested for equality with what was written. |
| [PLUR](https://github.com/plur-ai/plur) | awesome-claude-code:691 | Plain-text, human-correctable memory. Suggests a readable export of every note; its delete operation is the tension with R-INV-12. **Left out:** a CLI-only export breaks "both surfaces" (WO-32); deletion stays out (A3). |
| [Librarian](https://github.com/ngmeyer/librarian-mcp) | awesome-claude-code:200 | A local MCP server over a folder of Markdown files. Suggests partial-identifier matching in search. A candidate to measure, not to build (WO-23). |
| [IssueDB](https://issue-queue.readthedocs.io/en/latest/llm_agents.html?utm_source=awesome-gemini-cli&utm_medium=referral) | awesome-gemini-cli:233 | A command-line issue tracker built for agents. Direct prior art for `grove work`; compare its command surface. Compared; nothing taken beyond the history (WO-14). |
| [gemini-beads](https://github.com/thoreinstein/gemini-beads) | awesome-gemini-cli:151 | Task memory stored in git. An alternative storage choice, noted in the decision log. |
| [Repowise](https://www.repowise.dev) | static-analysis:2082 | The list describes it as deterministic, model-free code-health scoring with a CLI and MCP surface. Shows there is room for per-file scores; Grove stays with three flat layers. |

## 4. Tempting, and rejected

Each of these looks like a natural next step for a tool like Grove. Each is
rejected by name, grouped by the invariant it would break. Rejecting a tool
does not always mean rejecting its idea; where an idea is worth keeping, the
row says which.

### A model inside the product (breaks R-INV-2 and R-INV-3)

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [mem0](https://github.com/mem0ai/mem0) | awesome-python:168 | A memory layer for agents built on models. Grove's knowledge stays revisioned text with FTS5. |
| [sentence-transformers](https://github.com/huggingface/sentence-transformers) | awesome-python:173 | Semantic search needs embeddings and ends determinism. |
| [chromadb](https://github.com/chroma-core/chroma) | awesome-python:485 | A vector store; also breaks "one SQLite file". |
| [faiss-cpu](https://github.com/facebookresearch/faiss) | awesome-python:514 | Dense-vector search; needs embeddings. |
| [LlamaIndex](https://www.llamaindex.ai/) | awesome-generative-ai:216 | A retrieval-augmentation framework. Retrieval stays FTS5; the model is the client, not the server. |
| [privateGPT](https://github.com/zylon-ai/private-gpt) | awesome-generative-ai:91 | Local, so it passes the network rule, but it is still a model inside the product. |
| [autodoc](https://github.com/context-labs/autodoc) | awesome-chatgpt:210 | Model-written summaries of a codebase. The declared layer must come from documents people wrote. |
| [MAMA](https://github.com/jungjaehoon-lifegamez/MAMA) | awesome-claude-code:688 | The same storage as Grove plus embeddings. |
| [InjecGuard](https://github.com/safolab-wisc/injecguard) | awesome-prompt-injection:87 | A guard model that filters text before returning it. Tempting for WO-13; it breaks determinism, and silent filtering would break R-INV-11. |
| [crilio](https://github.com/mukundzha/crilio) | awesome-testing:70 | A model as judge of findings. Grove labels findings heuristic and lets the agent judge. |
| [ai-natural-language-tests](https://github.com/aiqualitylab/ai-natural-language-tests) | awesome-testing:248 | Requirement text to tests through a model and a vector database: the shortcut for declared-to-tests linking that Grove must not take. |
| [RAG AI Plugin](https://www.opslevel.com/resources/top-10-backstage-plugins-for-2025) | awesome-backstage:49 | The portal version of the same feature. |

### A network service, a hosted dashboard, or sync (breaks R-INV-1)

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [meilisearch](https://github.com/meilisearch/meilisearch-python) | awesome-python:511 | A search server reached over the network. |
| [Apache Lucene](http://lucene.apache.org/core/) | awesome-information-retrieval:46 | The usual "real search engine" upgrade; a second index and runtime next to one SQLite file. |
| [Codecov](https://about.codecov.io/) | static-analysis:2638 | A hosted coverage dashboard. A local coverage floor gives the same guarantee. |
| [SonarCloud](https://sonarcloud.io) | awesome-code-review:94 | Hosted automated review as a gate. Gates must be computed locally. |
| [Gerrit](https://www.gerritcodereview.com/) | awesome-code-review:83 | A review server. Grove's review is a local record. |
| [Kinto](https://github.com/Kinto/kinto) | awesome-json:110 | A storage service for sync between machines. Sharing, if ever needed, is an explicit export (WO-32). |
| [remoteStorage](https://remotestorage.io/) | offline-first:897 | Cross-device sync: the first feature users will ask for, and the one that ends local-only. |
| [soul](https://github.com/thevahidal/soul) | awesome-db-tools:230 | An HTTP API over the SQLite file; bypasses the CLI and MCP contract. |
| [OpenAPI Spec](https://spec.openapis.org/) | awesome-standards:48 | Describing the operations this way presumes an HTTP surface. JSON Schema covers the need. |
| [HTTP API Design Guide](https://github.com/interagent/http-api-design#readme) | guides:214 | "Make it a service" is the obvious next step and the wrong one. |
| [Context7](https://github.com/upstash/context7) | awesome-copilot-agents:228 | Fetching external documentation into the knowledge store. |
| [Catalog](https://github.com/backstage/backstage/tree/master/plugins/catalog) | awesome-backstage:31 | A central catalogue service. The idea worth keeping is a small descriptor per project; Grove's project row is that. |
| [Tech Insights Scorecards](https://roadie.io/backstage/plugins/tech-insights/) | awesome-backstage:54 | A hosted scorecard. The idea worth keeping is the strongest in that list: a named set of deterministic checks per project. Grove's findings are such checks; a later work order could group them. |
| [An introduction to monitoring and alerting with timeseries at scale, with Prometheus](https://www.youtube.com/watch?v=gNmWzkGViAY) | awesome-sre:284 | Stands for telemetry in general. Exporting metrics needs a listener or outbound calls. Local logs on stderr are enough. |

### GitHub mutation, or doing the agent's work (breaks R-INV-5 and R-SCOPE-2)

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [GitHub](https://github.com/github/github-mcp-server) | awesome-copilot-agents:222 | Pairing work items with pull requests belongs to the agent, as a separate server. |
| [hub](https://github.com/github/hub) | awesome-git-addons:592 | "Work item to pull request in one command". |
| [Github-Auto-Issue-Creator](https://github.com/Ricky54326/Github-Auto-Issue-Creator) | awesome-github:82 | Turning code comments into GitHub issues. |
| [Automatically approve and merge Dependabot updates](https://github.com/ridedott/dependabot-auto-merge-action) | awesome-actions:316 | Hands-free dependency merges bypass the review gate Grove is meant to exemplify. |
| [Auto-Approve PRs](https://github.com/hmarr/auto-approve-action) | awesome-actions:354 | Same reason. |
| [AgentSys](https://github.com/avifenesh/agentsys) | awesome-claude-code:534 | Automates pull requests and shipping. The useful lesson is its split: deterministic detection first, the model second. |
| [gstack](https://github.com/garrytan/gstack) | awesome-claude-code:561 | Shares the "software factory" label but is the workers, not the workshop. |
| [The Ralph Playbook](https://github.com/ClaytonFarr/ralph-playbook) | awesome-claude-code:602 | An autonomous loop until the spec is met. Grove must not drive an agent. |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | awesome-generative-ai:278 | An autonomous coder. Its artefact chain (requirements → design → tasks) is the chain Grove records and must not generate. |
| [Scaffolder](https://github.com/backstage/backstage/tree/master/plugins/scaffolder) | awesome-backstage:33 | Generating code or repositories. |

### A heavy parser stack or a new runtime dependency (breaks R-INV-14 and the small-scanner design)

| Resource | Found in (list:line) | Why it matters for Grove, what it suggests, and what became of it |
|---|---|---|
| [ast-grep-cli](https://github.com/ast-grep/ast-grep) | awesome-python:675 | Structural search would give exact symbols instead of per-line guesses, at the price of a syntax-tree stack for four languages. Rejected for v0; revisit only after WO-23 can measure what precision it would buy. |
| [Code-Graph-RAG](https://code-graph-rag.com) | static-analysis:1933 | The clearest example: parser stack, graph database, natural-language queries and code editing in one. |
| [cxpak](https://github.com/Barnett-Studios/cxpak) | awesome-claude-code:163 | A typed dependency graph over many languages. |
| [astminer](https://github.com/JetBrains-Research/astminer) | awesome-msr:68 | Syntax-tree mining with its own toolchain. |
| [Pandoc](https://pandoc.org/) | awesome-markdown:132 | Shelling out to a converter for a document tree; also breaks R-SCOPE-2 (no subprocess). |
| [sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) | awesome-python:438 | An ORM over one SQLite file with FTS5 and `user_version` migrations. |
| [fastmcp](https://github.com/PrefectHQ/fastmcp) | awesome-python:157 | A second framework on top of the SDK already in use. |
| [typer](https://github.com/fastapi/typer) | awesome-python:860 | Nicer declarations; a runtime dependency and changed help and exit behaviour that agents rely on. |
| [rich](https://github.com/Textualize/rich) | awesome-python:863 | Colour and tables for readers who are agents; risks non-JSON bytes on stdout. |
| [structlog](https://github.com/hynek/structlog) | awesome-python:839 | The envelope is already the structured output. |
| [rapidfuzz](https://github.com/rapidfuzz/RapidFuzz) | awesome-python:929 | Fuzzy matching would make findings harder to explain. |
| [watchfiles](https://github.com/samuelcolvin/watchfiles) | awesome-python:993 | Automatic rescans need a background process; scans are explicit and on demand. |
| [Eventsoucing in Python](https://github.com/johnbywater/eventsourcing) | awesome-ddd:370 | A ready-made engine for append-only data; Grove's revision model is a few SQL statements. |
| [flywaydb](http://flywaydb.org) | awesome-ciandcd:279 | A migration framework for server databases; forward-only `user_version` migrations are enough. |
| [JSON5](https://json5.org/) | awesome-json:149 | Relaxed JSON input weakens a strict contract and needs a non-standard parser. |
| [python-ftfy](https://github.com/LuminosoInsight/python-ftfy) | awesome-unicode:493 | Repairing scanned text changes what was read; evidence must be verbatim. |

Two further rejections come from the sources read directly, not from a
list: an HTTP transport for the MCP server (the specification offers one;
Grove is stdio only, R-INV-8), and moving the default data directory to the
XDG layout (section 2).

## 5. Coverage of the root list

Every list linked from the root `readme.md`, by section. "Read in full" means
cloned and read line by line; "set aside" means judged from its name and
description in the root list.

### Platforms (55 lists: 1 read, 54 set aside)

Operating systems, mobile, cloud and device platforms. Grove targets none of them. Backstage (a hosted developer portal) was read for the ideas a local workshop could borrow.

- **Read in full:** Backstage (`shano/awesome-backstage`).
- **Set aside:** Node.js, Cross-Platform, Frontend Development, iOS, Android, IoT & Hybrid Apps, Electron, Cordova, React Native, Containers, eBPF, Arch-based Projects, AppImage, Omarchy, Screensavers, Apps, Open Source Apps, watchOS, JVM, Salesforce, Amazon Web Services, Windows, PowerToys Run Plugins, IPFS, Fuse, Heroku, Raspberry Pi, WebExtensions, Smart TV, GNOME, KDE, .NET, Core, Roslyn, DigitalOcean, Flutter, Home Assistant, IBM Cloud, Firebase, Adafruit IO, Cloudflare, Actions on Google, ESP, Deno, DOS, Nix, Integration, Node-RED, Low Code, Capacitor, ArcGIS Developer, Bluetooth Low Energy, Uno Platform, Firebase Genkit.

### Programming Languages (77 lists: 2 read, 75 set aside)

Library catalogues for other ecosystems. Rust, Go and JavaScript are languages Grove *scans*, but their lists catalogue libraries, not practices for a scanner.

- **Read in full:** Python (`vinta/awesome-python`); Typing (`typeddjango/awesome-python-typing`).
- **Set aside:** JavaScript, Promises, Standard Style, Must Watch Talks, Tips, Network Layer, Micro npm Packages, Mad Science npm Packages, Maintenance Modules, npm, AVA, ESLint, Functional Programming, Observables, npm scripts, 30 Seconds of Code, Ponyfills, Swift, Education, Playgrounds, Asyncio, Scientific Audio, CircuitPython, Data Science, MicroPython, Rust, Pest, Haskell, PureScript, Go, Scala, Scala Native, Ruby, Clojure, ClojureScript, Elixir, Elm, Erlang, Julia, Lua, C/C++, R, Learning, D, Common Lisp, Learning, Perl, Groovy, Dart, Java, RxJava, J2ME, Kotlin, OCaml, ColdFusion, Fortran, PHP, Composer, Pascal, AutoHotkey, AutoIt, Crystal, CMake, ActionScript 3, Idris, Ada/SPARK, Q#, Imba, Vala, Coq, V, Move, Esolangs, VBA, F#.

### Front-End Development (85 lists: 1 read, 84 set aside)

Browser technology. Offline-First was read for principle-level support of local-only software.

- **Read in full:** Offline-First (`pazguille/offline-first`).
- **Set aside:** ES6 Tools, Web Performance Optimization, Web Tools, CSS, Critical-Path Tools, Scalability, Must-Watch Talks, Protips, Frameworks, React, Relay, React Hooks, Web Components, Polymer, Angular, Backbone, HTML5, SVG, Canvas, KnockoutJS, Dojo Toolkit, Inspiration, Ember, Android UI, iOS UI, Meteor, BEM, Flexbox, Web Typography, Web Accessibility, Material Design, D3, Emails, jQuery, Tips, Web Audio, Static Website Services, Cycle.js, Text Editing, Motion UI Design, Vue.js, Marionette.js, Aurelia, Charting, Ionic Framework, Chrome DevTools, PostCSS, Draft.js, Service Workers, Progressive Web Apps, choo, Redux, Browserify, Sass, Ant Design, Less, WebGL, Preact, Progressive Enhancement, Next.js, lit, JAMstack, WordPress-Gatsby, Mobile Web Development, Storybook, Blazor, PageSpeed Metrics, Tailwind CSS, Seed, Web Performance Budget, Web Animation, Yew, Material-UI, Building Blocks for Web Apps, Svelte, Design systems, Inertia.js, MDBootstrap, Master CSS, Hydrogen, Tiny JS, Frontend GIS, WebGPU, WebAssembly.

### Back-End Development (32 lists: 0 read, 32 set aside)

Web frameworks and cloud infrastructure; Grove has no server.

- **Set aside:** Flask, Docker, Vagrant, Pyramid, Play1 Framework, CakePHP, Symfony, Education, Laravel, Education, Rails, Gems, Phalcon, Useful `.htaccess` Snippets, nginx, Dropwizard, Kubernetes, Lumen, Serverless Framework, Apache Wicket, Vert.x, Terraform, Vapor, Dash, FastAPI, CDK, IAM, Slim, Fiber, Kustomize, OpenTofu, Reflex.

### Computer Science (38 lists: 4 read, 34 set aside)

Machine learning, vision, speech and theory lists concern models, which Grove must not contain.

- **Read in full:** Empirical Software Engineering (`dspinellis/awesome-msr`); Static Analysis & Code Quality (`analysis-tools-dev/static-analysis`); Information Retrieval (`harpribot/awesome-information-retrieval`); Generative AI (`steven2358/awesome-generative-ai`).
- **Set aside:** University Courses, Data Science, Tutorials, Machine Learning, Tutorials, ML with Ruby, Core ML Models, H2O, Software Engineering for Machine Learning, AI in Finance, JAX, XAI, Speech and Natural Language Processing, Spanish, NLP with Ruby, Question Answering, Natural Language Generation, Linguistics, Cryptography, Papers, Computer Vision, Deep Learning, TensorFlow, TensorFlow.js, TensorFlow Lite, Papers, Education, Deep Vision, Open Source Society University, Functional Programming, Quantum Computing, Theoretical Computer Science, Conversational AI, Position-Based Quantum Cryptography.

### Big Data (9 lists: 0 read, 9 set aside)

Distributed data processing; Grove is one SQLite file.

- **Set aside:** Big Data, Public Datasets, Hadoop, Data Engineering, Streaming, Apache Spark, Qlik, Splunk, Network Analysis.

### Theory (14 lists: 0 read, 14 set aside)

Algorithms, mathematics and paper collections; nothing specific to a workshop tool.

- **Set aside:** Papers We Love, Talks, Algorithms, Education, Algorithm Visualizations, Artificial Intelligence, Search Engine Optimization, Competitive Programming, Math, Recursion Schemes, Audit Algorithms, AGI & CoCoSci, Complex Systems, VLM Architectures.

### Books (6 lists: 0 read, 6 set aside)

Book catalogues; relevant titles surfaced through the topical lists instead.

- **Set aside:** Free Programming Books, Go Books, R Books, Mind Expanding Books, Book Authoring, Elixir Books.

### Editors (5 lists: 0 read, 5 set aside)

Editor plugins; Grove's users are agents.

- **Set aside:** Sublime Text, Vim, Neovim, Emacs, Visual Studio Code.

### Gaming (28 lists: 0 read, 28 set aside)

Game development.

- **Set aside:** Game Development, Game Talks, Godot, Open Source Games, Chess, LÖVE, PICO-8, Game Boy Development, Construct 2, Gideros, Minecraft, ComputerCraft, Game Datasets, Haxe Game Development, libGDX, PlayCanvas, Game Remakes, Flame, Discord Communities, CHIP-8, Games of Coding, Esports, Learn Gamedev, Game Engine Development, GameMaker, Game Production, Babylon.js, Roblox.

### Development Environment (21 lists: 6 read, 15 set aside)

Terminal and dotfile customisation was set aside; shell, command-line, git and GitHub lists were read.

- **Read in full:** Shell (`alebcay/awesome-shell`); Command-Line Apps (`agarrharr/awesome-cli-apps`); GitHub (`phillipadsmith/awesome-github`); Git Add-ons (`stevemao/awesome-git-addons`); Git Hooks (`compscilauren/awesome-git-hooks`); GitHub Actions (`sdras/awesome-actions`).
- **Set aside:** Quick Look Plugins, Dev Env, Dotfiles, Fish, ZSH Plugins, Browser Extensions, Cheat Sheet, Pinned Gists, Git Cheat Sheet & Git Flow, Git Tips, SSH, FOSS for Developers, Hyper, Terminals Are Sexy, WezTerm.

### Entertainment (5 lists: 0 read, 5 set aside)

Not software practice.

- **Set aside:** Science Fiction, Fantasy, Podcasts, Email Newsletters, IT Quotes.

### Databases (17 lists: 2 read, 15 set aside)

Server databases. SQLite has no list of its own in the root list; the two general database lists were read for what applies to a single local file.

- **Read in full:** Database (`numetriclabz/awesome-db`); Database Tools (`mgramin/awesome-db-tools`).
- **Set aside:** MySQL, SQLAlchemy, InfluxDB, Neo4j, MongoDB, RethinkDB, TinkerPop, PostgreSQL, CouchDB, HBase, NoSQL Guides, TypeDB, Supabase, PocketBase, Neon.

### Media (14 lists: 0 read, 14 set aside)

Fonts, images, audio and video.

- **Set aside:** Fonts, Codeface, Stock Resources, GIF, Music, Open Source Documents, Audio Visualization, Broadcasting, Pixel Art, FFmpeg, Icons, Audiovisual, VLC, Audio Over IP.

### Learn (15 lists: 0 read, 15 set aside)

Learning paths and career material.

- **Set aside:** CLI Workshoppers, Learn to Program, Speaking, Tech Videos, Computer History, Programming for Kids, STEAM, Educational Games, JavaScript Learning, CSS Learning, Product Management, Roadmaps, YouTubers, Hackathon, Certificates.

### Security (29 lists: 6 read, 23 set aside)

Offensive security, malware, network and hardware security were set aside; the lists about building software safely were read.

- **Read in full:** Application Security (`paragonie/awesome-appsec`); Security (`sbilly/awesome-security`); Fuzzing (`cpuu/awesome-fuzzing`); DevSecOps (`TaptuIT/awesome-devsecops`); Prompt Injection (`FonduAI/awesome-prompt-injection`); CI/CD Attacks (`TupleType/awesome-cicd-attacks`).
- **Set aside:** CTF, Cyber Security University, Malware Analysis, Android Security, Hacking, Hacking Spots, Honeypots, Incident Response, Vehicle Security and Car Hacking, Web Security, Lockpicking, Cybersecurity Blue Team, Embedded and IoT Security, GDPR, Executable Packing, Malware Persistence, EVM Security, Password Cracking, Security Card Games, Suricata, Detection Engineering, Annual Security Reports, OpenID Connect.

### Content Management Systems (11 lists: 0 read, 11 set aside)

CMS products.

- **Set aside:** Umbraco, Refinery CMS, Wagtail, Textpattern, Drupal, Craft CMS, Sitecore, Silverstripe CMS, Directus, Plone, Payload.

### Hardware (11 lists: 0 read, 11 set aside)

Hardware.

- **Set aside:** Robotics, Internet of Things, Electronics, Bluetooth Beacons, Electric Guitar Specifications, Plotters, Robotic Tooling, LIDAR, Open Hardware, ADS-B, Flying FPV.

### Business (12 lists: 1 read, 11 set aside)

Company and product strategy. Engineering Team Management was read for its engineering-practice sections.

- **Read in full:** Engineering Team Management (`kdeldycke/awesome-engineering-team-management`).
- **Set aside:** Open Companies, Places to Post Your Startup, OKR Methodology, Indie, Tools of the Trade, Clean Tech, Wardley Maps, Social Enterprise, Developer-First Products, Billing, Engineering Strategy.

### Work (7 lists: 1 read, 6 set aside)

Jobs and collaboration products. Code Review was read.

- **Read in full:** Code Review (`joho/awesome-code-review`).
- **Set aside:** Slack, Communities, Remote Jobs, Productivity, Niche Job Boards, Creative Technology.

### Networking (5 lists: 0 read, 5 set aside)

Network protocols and capture tools; Grove has no network.

- **Set aside:** PCAPTools, Real-Time Communications, SNMP, Scapy, Cilium.

### Decentralized Systems (17 lists: 0 read, 17 set aside)

Blockchains and peer-to-peer networks.

- **Set aside:** Bitcoin, Ripple, Non-Financial Blockchain, Mastodon, Ethereum, Blockchain AI, EOSIO, Corda, Waves, Substrate, Golem, Stacks, Algorand, ZeroNet, Cosmos SDK, Tor, ATProto.

### Health and Social Science (12 lists: 0 read, 12 set aside)

Not software practice.

- **Set aside:** Biomedical Information Extraction, Computational Neuroscience, Diversity, Digital History, Empathy in Engineering, Healthcare, Mental Health, Neuroscience, Digital Humanities, Lucid Dreams, Neuroimaging, Transgender.

### Events (3 lists: 0 read, 3 set aside)

Event calendars.

- **Set aside:** Creative Tech Events, Events in Italy, Events in the Netherlands.

### Testing (11 lists: 2 read, 9 set aside)

Browser, mobile and load testing target products Grove is not. CodeRabbit is a hosted, model-based review service (rejected: R-INV-1, R-INV-2).

- **Read in full:** Testing (`TheJambo/awesome-testing`); TAP (`sindresorhus/awesome-tap`).
- **Set aside:** Visual Regression Testing, Selenium, Appium, JMeter, k6, Playwright, Quality Assurance Roadmap, Gatling, CodeRabbit.

### Miscellaneous (132 lists: 22 read, 110 set aside)

A mixed section. The lists about formats, documentation, architecture, operations practice and coding agents were read; the rest are domains unrelated to a local workshop.

- **Read in full:** Scientific Writing (`writing-resources/awesome-scientific-writing`); JSON (`burningtree/awesome-json`); Continuous Integration and Continuous Delivery (`cicdops/awesome-ciandcd`); Readme (`matiassingers/awesome-readme`); Design and Development Guides (`NARKOZ/guides`); Unicode (`jagracey/Awesome-Unicode`); Site Reliability Engineering (`dastergon/awesome-sre`); Falsehood (`kdeldycke/awesome-falsehood`); Domain-Driven Design (`heynickc/awesome-ddd`); Markdown (`BubuAnabelas/awesome-markdown`); Open Source Maintainers (`nayafia/awesome-maintainers`); Software Architecture (`simskij/awesome-software-architecture`); Naming (`gruhn/awesome-naming`); Read the Docs (`readthedocs-examples/awesome-read-the-docs`); ChatGPT (`sindresorhus/awesome-chatgpt`); Regex (`slevithan/awesome-regex`); Event-Driven Architecture (`lutzh/awesome-event-driven-architecture`); Permacomputing (`idematos/awesome-permacomputing`); Standards (`donBarbos/awesome-standards`); Claude Code (`hesreallyhim/awesome-claude-code`); Gemini CLI (`Piebald-AI/awesome-gemini-cli`); Copilot Agents (`Code-and-Sorts/awesome-copilot-agents`).
- **Set aside:** GeoJSON, CSV, Discounts for Student Developers, Radio, Awesome, Analytics, REST, Services Engineering, Free for Developers, Boilerplate Projects, GitHub Wiki, Software Engineering Blogs, Self Hosted, FOSS Production Apps, Gulp, AMA, Answers, Open Source Photography, OpenGL, GraphQL, Urban & Regional Planning, Transit, Research Tools, Data Visualization, Microservices, Code Points, Beginner-Friendly Projects, Katas, Tools for Activism, Citizen Science, MQTT, For Girls, Vorpal, Vulkan, LaTeX, Economics, Funny Markov Chains, Bioinformatics, Cheminformatics, Colorful, Steam, Bots, DTrace, Userscripts, Pokémon, ChatOps, Quantified Self, Web Design, Creative Coding, No-Login Web Apps, Free Software, Framer, Dev Fun, Magento 2, TikZ, Ad-Free, Prometheus, Homematic, Ledger, Web Monetization, Uncopyright, Crypto Currency Tools & Algorithms, Open Source Supporters, Design Principles, Theravada, inspectIT, Calculators, Captcha, Jupyter, FIRST Robotics Competition, Speakers, Board Games, Software Patreons, Parasite, Food, Bitcoin Payment Processors, Scientific Computing, Amazon Sellers, Agriculture, Product Design, Prisma, Connectivity Data and Reports, Stacks, Cytodata, IRC, Advertising, Earth, Web Archiving, WP-CLI, Credit Modeling, Ansible, Biological Visualizations, QR Code, Veganism, Translations, Scriptable, WebXR, Computational Geometry, OpenStreetMap, Computational Biology, Quarto, Biological Image Analysis, Whisper, Stock Trading, Steam Deck, Astrophotography, HPC, Geocaching, SAP Commerce, Tech Ethics.

The root list's last section, "Related", links tools for browsing awesome
lists; it has no content of its own.

## 6. The lists read in full

Sections classified and entries judged, per list. "Reject" means tempting but
wrong for Grove.

| List (owner/repo) | Commit | Commit date | Sections classified | Entries judged adopt / consider / reject |
|---|---|---|---|---|
| [agarrharr/awesome-cli-apps](https://github.com/agarrharr/awesome-cli-apps) | `1f85964` | 2026-10-12 | 80 | 2 / 18 / 2 |
| [alebcay/awesome-shell](https://github.com/alebcay/awesome-shell) | `cb355ae` | 2024-02-20 | 16 | 4 / 9 / 0 |
| [analysis-tools-dev/static-analysis](https://github.com/analysis-tools-dev/static-analysis) | `cb17a89` | 2026-11-12 | 103 | 8 / 34 / 6 |
| [BubuAnabelas/awesome-markdown](https://github.com/BubuAnabelas/awesome-markdown) | `360c7d1` | 2023-05-18 | 22 | 2 / 11 / 2 |
| [burningtree/awesome-json](https://github.com/burningtree/awesome-json) | `e8efe3c` | 2026-06-19 | 33 | 2 / 14 / 4 |
| [cicdops/awesome-ciandcd](https://github.com/cicdops/awesome-ciandcd) | `c5e6fca` | 2026-04-14 | 29 | 1 / 2 / 1 |
| [Code-and-Sorts/awesome-copilot-agents](https://github.com/Code-and-Sorts/awesome-copilot-agents) | `a26d912` | 2026-04-28 | 53 | 0 / 7 / 2 |
| [compscilauren/awesome-git-hooks](https://github.com/compscilauren/awesome-git-hooks) | `417f786` | 2026-02-14 | 17 | 1 / 6 / 0 |
| [cpuu/awesome-fuzzing](https://github.com/cpuu/awesome-fuzzing) | `83fddf9` | 2026-09-14 | 26 | 1 / 11 / 3 |
| [dastergon/awesome-sre](https://github.com/dastergon/awesome-sre) | `e91ef69` | 2022-10-08 | 24 | 2 / 14 / 2 |
| [donBarbos/awesome-standards](https://github.com/donBarbos/awesome-standards) | `67f5107` | 2026-07-18 | 15 | 3 / 17 / 2 |
| [dspinellis/awesome-msr](https://github.com/dspinellis/awesome-msr) | `ac89aca` | 2026-06-01 | 7 | 0 / 8 / 2 |
| [FonduAI/awesome-prompt-injection](https://github.com/FonduAI/awesome-prompt-injection) | `8a4448c` | 2026-09-11 | 11 | 9 / 23 / 2 |
| [gruhn/awesome-naming](https://github.com/gruhn/awesome-naming) | `4fd4338` | 2026-09-17 | 13 | 0 / 6 / 0 |
| [harpribot/awesome-information-retrieval](https://github.com/harpribot/awesome-information-retrieval) | `a60c61a` | 2023-04-20 | 17 | 2 / 7 / 2 |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | `4d95c7a` | 2026-11-12 | 36 | 7 / 31 / 10 |
| [heynickc/awesome-ddd](https://github.com/heynickc/awesome-ddd) | `9dca80e` | 2026-08-26 | 31 | 0 / 10 / 2 |
| [idematos/awesome-permacomputing](https://github.com/idematos/awesome-permacomputing) | `36d6d8d` | 2026-10-17 | 33 | 2 / 7 / 2 |
| [jagracey/Awesome-Unicode](https://github.com/jagracey/Awesome-Unicode) | `e219c3f` | 2019-12-02 | 38 | 6 / 13 / 1 |
| [joho/awesome-code-review](https://github.com/joho/awesome-code-review) | `1887c2a` | 2024-09-09 | 9 | 3 / 15 / 3 |
| [kdeldycke/awesome-engineering-team-management](https://github.com/kdeldycke/awesome-engineering-team-management) | `8ce20c2` | 2026-10-08 | 81 | 3 / 21 / 0 |
| [kdeldycke/awesome-falsehood](https://github.com/kdeldycke/awesome-falsehood) | `0b1aaba` | 2026-10-08 | 26 | 10 / 18 / 0 |
| [lutzh/awesome-event-driven-architecture](https://github.com/lutzh/awesome-event-driven-architecture) | `6dfa43e` | 2026-10-11 | 11 | 0 / 2 / 1 |
| [matiassingers/awesome-readme](https://github.com/matiassingers/awesome-readme) | `f0742eb` | 2026-11-10 | 10 | 1 / 15 / 1 |
| [mgramin/awesome-db-tools](https://github.com/mgramin/awesome-db-tools) | `46bd349` | 2026-10-04 | 51 | 0 / 15 / 2 |
| [NARKOZ/guides](https://github.com/NARKOZ/guides) | `3c512a4` | 2025-07-02 | 50 | 3 / 11 / 1 |
| [nayafia/awesome-maintainers](https://github.com/nayafia/awesome-maintainers) | `bb996d6` | 2021-08-16 | 3 | 0 / 9 / 0 |
| [numetriclabz/awesome-db](https://github.com/numetriclabz/awesome-db) | `ca38653` | 2016-01-08 | 10 | 0 / 1 / 0 |
| [paragonie/awesome-appsec](https://github.com/paragonie/awesome-appsec) | `df38442` | 2025-02-22 | 24 | 1 / 5 / 0 |
| [pazguille/offline-first](https://github.com/pazguille/offline-first) | `d778c27` | 2022-09-20 | 15 | 0 / 6 / 2 |
| [phillipadsmith/awesome-github](https://github.com/phillipadsmith/awesome-github) | `5c1e451` | 2021-04-26 | 5 | 0 / 2 / 1 |
| [Piebald-AI/awesome-gemini-cli](https://github.com/Piebald-AI/awesome-gemini-cli) | `3634489` | 2026-11-12 | 21 | 2 / 21 / 3 |
| [readthedocs-examples/awesome-read-the-docs](https://github.com/readthedocs-examples/awesome-read-the-docs) | `7f77aef` | 2024-06-19 | 10 | 0 / 4 / 1 |
| [sbilly/awesome-security](https://github.com/sbilly/awesome-security) | `51b613c` | 2026-01-11 | 47 | 0 / 11 / 0 |
| [sdras/awesome-actions](https://github.com/sdras/awesome-actions) | `0edccf3` | 2024-09-01 | 43 | 5 / 12 / 3 |
| [shano/awesome-backstage](https://github.com/shano/awesome-backstage) | `0980f5e` | 2026-10-27 | 14 | 0 / 9 / 10 |
| [simskij/awesome-software-architecture](https://github.com/simskij/awesome-software-architecture) | `12a81ac` | 2026-04-19 | 18 | 1 / 10 / 2 |
| [sindresorhus/awesome-chatgpt](https://github.com/sindresorhus/awesome-chatgpt) | `fdf528f` | 2026-02-16 | 23 | 0 / 0 / 5 |
| [sindresorhus/awesome-tap](https://github.com/sindresorhus/awesome-tap) | `d48d876` | 2025-11-11 | 19 | 1 / 5 / 0 |
| [slevithan/awesome-regex](https://github.com/slevithan/awesome-regex) | `77599a1` | 2026-09-02 | 37 | 2 / 14 / 1 |
| [stevemao/awesome-git-addons](https://github.com/stevemao/awesome-git-addons) | `a054ac3` | 2024-10-15 | 55 | 0 / 11 / 1 |
| [steven2358/awesome-generative-ai](https://github.com/steven2358/awesome-generative-ai) | `89e4a9c` | 2026-10-30 | 43 | 1 / 2 / 7 |
| [TaptuIT/awesome-devsecops](https://github.com/TaptuIT/awesome-devsecops) | `a271dcf` | 2024-05-27 | 43 | 3 / 23 / 0 |
| [TheJambo/awesome-testing](https://github.com/TheJambo/awesome-testing) | `7ff1600` | 2026-11-11 | 34 | 4 / 22 / 4 |
| [TupleType/awesome-cicd-attacks](https://github.com/TupleType/awesome-cicd-attacks) | `d6fd99e` | 2026-06-02 | 10 | 10 / 17 / 0 |
| [typeddjango/awesome-python-typing](https://github.com/typeddjango/awesome-python-typing) | `77a60ec` | 2026-11-08 | 18 | 4 / 12 / 2 |
| [vinta/awesome-python](https://github.com/vinta/awesome-python) | `bcd8459` | 2026-11-08 | 83 | 13 / 23 / 16 |
| [writing-resources/awesome-scientific-writing](https://github.com/writing-resources/awesome-scientific-writing) | `f4a041f` | 2026-09-15 | 13 | 0 / 7 / 2 |

## 7. Limits of this survey

- Linked websites were not opened (network policy of the session). Only the
  two GitHub-hosted sources in section 2 were read beyond the lists.
- The lists are other people's selections. An absent topic (section 1) means
  the lists do not cover it, not that the practice does not exist.
- The verdicts are judgements made against Grove's invariants on the survey
  dates. They are inputs to `docs/analysis.md` and `docs/work-orders.md`,
  not decisions; the decisions are in `REQUIREMENTS.md`.
- The reader agents were briefed to surface candidates generously. The
  filtering came afterwards and is recorded in section 3 and in
  `docs/work-orders.md`. The counts of "adopt" in section 6 are the readers'
  first verdicts, not what Grove will do.
- Two lists yielded almost nothing for Grove despite a full read
  (`sbilly/awesome-security`, `phillipadsmith/awesome-github`), and several
  were read mainly to confirm they could be set aside (domain-driven design,
  event-driven architecture, naming, maintainers).
