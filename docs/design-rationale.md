# Why Grove is built this way, and how well it fits a factory of Grok Bot and Claude

Written by Claude on 2026-11-13, at the owner's request, from inside a Claude
Code cloud session that was working on this repository at the time. It is an
argument, not a specification. What Grove must do is in `REQUIREMENTS.md`;
how the code is arranged is in `docs/blueprint.md`; what is planned is in
`docs/work-orders.md`. This document explains the reasoning behind those
three, says where the reasoning holds and where it does not, and lists the
problems found while using Grove for real work.

It is written so that someone who does not write software can follow it. The
names in `code type` (files, requirement ids such as R-INV-1, work orders
such as WO-14) are there so that an engineer or an agent can find the exact
place a statement refers to. They can be skipped on a first reading.

Every factual statement here was either read in the code or produced by
running Grove in that session, always against a temporary data directory.
Where something could not be checked, the text says so.

**Revised once, later on 2026-11-13,** in the change that built WO-14,
after Ume (the team's systems architect) had reviewed this document and the
owner had approved three follow-ups: issue 1(a) is done, issue 2 is
rewritten from a real Grok Bot trial, and issue 4 is built. Each revised
place is marked *Update*. The original findings are left standing next to
the updates, because the reasoning still explains why the work was done.

## 1. The answer in one page

Grove is a notebook and a map for coding agents, kept on one computer. It
does three plain things: it reads a codebase and writes down what the
documents promise, what the code contains and what the tests are named; it
keeps notes that are never overwritten; and it keeps a list of jobs with a
status. It contains no artificial intelligence of its own, it never changes
the code it reads, and it never contacts the internet.

Those refusals are the design. In a software factory where two different AI
agents (Mila, a Grok Bot, and Claude) work on the same software and a person
approves anything that matters, the shared tool in the middle should be the
one part that cannot act, cannot spend, cannot leak and cannot be argued
with. Grove is built to be that part, and on that central point the design
is right.

Is it *optimal* for that factory? No, and it would be dishonest to say so.
It is a good fit with four named limits:

1. **Its memory stops at the edge of one computer.** A Claude cloud session
   runs on a fresh machine that is thrown away afterwards. It sees an empty
   Grove, and anything it writes into Grove is lost. This session was such a
   session (section 5, issue 1).
2. **The Grok Bot side had never been tried when this was written.**
   *Update:* it has now been tried once, and it worked; what was measured
   and what was not is under issue 2.
3. **The job list was too thin to show who did what.** A second note erased
   the first, and nothing recorded who changed a status (issue 4). For a
   factory with two agents, that is the part that most needs to be solid.
   *Update:* a history now records both (WO-14).
4. **The "gap findings" are hints of unknown accuracy.** On Grove's own
   repository, none of the six "untested promise" findings pointed at a real
   gap (section 4.3).

None of the four is a reason to change the foundations. The first two are
about reach and proof; the last two are unfinished work that is already
specified. Section 7 lists eleven issues with a suggested fix for each;
one was fixed alongside this document, and three more (1a, 2 and 4) were
acted on in the revision.

## 2. What Grove is for, and what it refuses to be

Imagine a workshop shared by two craftsmen who never meet. Each arrives,
works for a few hours and leaves, and remembers nothing of the last visit.
What they need on the wall is a plan of the building, a notebook nobody can
tear pages out of, and a job board. That is Grove's whole purpose
(`REQUIREMENTS.md`, R-SCOPE-1): a scan, knowledge, work items, and one
suggestion for what to look at next.

An AI agent really is like that craftsman. Each session starts with no
memory of earlier sessions. Whatever must survive from one session to the
next, or pass from one agent to another, has to be written down somewhere
outside the agent. Grove is that somewhere.

Just as important is what Grove refuses to be. Each refusal is a rule with a
test behind it, not a matter of taste.

- **It does not write code.** It never edits, generates or runs anything in
  the project it looks at (R-SCOPE-2, R-INV-4). A test hashes every file of
  a scanned project before and after and fails if one byte changed
  (`tests/test_scan_safety.py`).
- **It stays on one machine.** It opens no network connection of any kind
  (R-INV-1). A test reads Grove's own source and fails if any file imports a
  networking module (`tests/test_invariants.py`).
- **It has no model inside.** No language model and no "embeddings"
  (R-INV-2). Everything is pattern matching, word comparison and a small
  database. The same input always gives the same output (R-INV-3).
- **It does not touch GitHub.** It cannot open a pull request, comment or
  merge (R-INV-5). A link stored on a job is kept as text and never opened.
- **It does not judge.** Every finding is labelled `heuristic`, a hint
  (R-SCOPE-3). When an agent says a job is `done`, Grove writes that down;
  it does not check it.

## 3. Why those refusals suit a factory of two agents and one person

The factory in question has three kinds of participant. Mila, a Grok Bot,
and Claude both read and change the software. Sai, the owner, approves
merges, anything that costs money, and anything that carries liability. The
design question is what the tool they share should be allowed to do. Grove's
answer is "as little as possible", and here is why each restriction helps.

**No model inside means the referee belongs to neither side.** Mila runs on
one company's model and Claude on another's. If the shared tool also
contained a model, its opinions would come from one vendor, would change
whenever that vendor changed the model, and would be one more thing that can
be confidently wrong. A tool made of fixed rules gives both agents the same
answer, gives the same answer next month, and can be checked by a person
reading one short file (`src/sf_grove/gaps.py`). The intelligence is in
the agents; the shared ground under them should not move. There is a second,
practical benefit: a tool with no model costs nothing to run and cannot
generate a bill.

**Local only means nothing leaves, so there is nothing to answer for.** The
source code, the notes and the job list stay in one file on one disk
(`grove.db`). There is no server to secure, no account, no data-processing
question, no subscription. For the person who carries the liability, the
shared tool adds none.

**No GitHub access means there is exactly one road to the main branch.** The
agents propose changes as pull requests; the person merges. If Grove could
open or merge pull requests it would be a second road, and the approval step
would no longer be the only gate. Because Grove cannot act on GitHub at all,
no instruction hidden in a scanned file and no mistake by an agent can make
*Grove* publish or merge anything. This is also why Grove can safely return
text written by strangers (a README it scanned, a note from the other
agent): it has no dangerous action for that text to trigger. The risk moves
to the agent reading the text, which is why the brief tells agents to treat
such text as information and never as instructions (`CLAUDE.md`, and
the server instructions since WO-13: R-SEC-4).

**It records and does not judge, so approval stays with the person.** A tool
that declared work "verified" would invite everyone to trust the tool. Grove
only says "Claude reported this as ready for review". The actual review and
the actual approval happen on GitHub, by someone other than the author
(`REQUIREMENTS.md`, section 11.1, item 11).

**Nothing is overwritten or deleted, so one agent cannot erase the other's
record.** Writing a note under an existing name adds a new revision; the old
one stays (R-INV-12). There is no delete operation at all (R-SCOPE-4). In a
shared notebook used by two agents that make mistakes, that is the safe
default.

**The same input gives the same output, so disagreements can be settled.**
If Mila and Claude both scan the same code they get the same findings in the
same order. A person can rerun the command and see what they saw.

## 4. The parts, one at a time

For each part: why it exists, how it behaves, and whether it was awkward in
practice.

### 4.1 The data directory

Everything Grove knows lives in one database file inside one folder, chosen
in a fixed order: a `--home` option on the command, else the `GROVE_HOME`
setting, else `~/.grove` in the user's home folder (R-HOME-1,
`src/sf_grove/db.py`). The rule for a factory is "one folder per machine,
shared by every agent" (R-HOME-3), because the notebook is only shared if
both agents open the same one.

This is simple and it is the right default: no server, safe for several
programs at once (R-HOME-8), trivially backed up by copying a folder. Its
classic failure is two agents quietly using two different folders, each
seeing an empty workshop. The repository already defends against that: the
`status` command says which folder is in use and how it was chosen, and
warns when it is empty (R-HOME-2). Grove also refuses to keep its folder
inside a project it scans, so that "never writes inside the project" stays
true even when someone configures it badly (R-HOME-4, built as WO-09).

Two awkward points. First, an agent's commands do not share settings from
one command to the next, so the folder must be named on every call or set
where the agent is started; the brief says so (R-HOME-6). Second, and far
more important: the rule says "per machine", and a cloud session is a
different machine. That is issue 1.

A small thing seen while testing: even `grove status`, which is labelled as
read-only, creates the folder and an empty database if they do not exist. A
mistyped folder name therefore creates a new empty workshop without
complaint. The warning in `status` is what catches this; see issue 9.

### 4.2 Sixteen tools and a command line that are the same thing

Agents reach Grove in two ways. MCP (the Model Context Protocol) is a
standard way for an AI assistant to be handed a list of tools it may call;
Grove offers sixteen. The command line is the same sixteen operations typed
as commands (`grove scan NAME`, `grove work list NAME`, and so on). Grok Bot
can use only the first way; Claude Code can use either.

The important design choice is that there is one implementation and two thin
doors onto it. `src/sf_grove/service.py` holds the sixteen operations;
`src/sf_grove/tools.py` is one table that names and describes them; the MCP
server and the command line both read that table (decision D-05). So the two
agents cannot be given different behaviour by accident, and a test fails if
the documents, the table and the commands disagree
(`tests/test_docs_contract.py`).

Three further choices matter for agents in particular:

- **One shape for every answer.** Every result is either "ok, and here is
  the data" or "not ok, with one of four error codes and a sentence saying
  what to do" (R-INV-10, R-IF-4). An agent never has to guess whether
  something worked.
- **The sixteen names are frozen** (R-INV-9). An agent's habits and saved
  instructions keep working across versions. The price is that every new
  ability has to be squeezed into an existing tool as an optional setting,
  which sometimes produces odd shapes: listing all notes is done by calling
  the *search* tool with no search words (WO-04), and the list of paths to
  ignore is set through the *scan* tool (WO-10). Both are documented and
  both are a fair price for stability.
- **Nothing is cut short silently** (R-INV-11). An agent has a limited
  amount of text it can hold in mind at once. Grove pages long lists,
  summarises scans and shortens long notes, and every time it does so the
  answer says so and says how to get the rest.

In practice, from Claude's side, the command line was easy: the answers are
uniform, errors explain themselves, and `--text` gives a readable form for a
person. Two things got in the way. Writing a note requires a file on disk
rather than accepting the text directly (R-CC-4; since built in WO-21:
`knowledge write --file -` reads standard input). And the
tool descriptions, which are all a Grok Bot reads over MCP, already occupied
16 054 of a 16 384-byte budget (R-GROK-3). That left 330 bytes, which
matters for the order of future work (issue 8). *Update:* WO-14 used 312 of
them; 18 remain.

Whether the MCP door works with Grok Bot at all was unproven when this was
written. *Update:* it works (issue 2).

### 4.3 The three-layer scan and its findings

The scan reads a project and files what it finds under three headings
(R-SCAN-3):

- **declared**: what the documents say. Headings and sentences from the
  README and the files under `docs/`.
- **actual**: what the code contains. One entry per source file, plus the
  names of the functions and classes in it.
- **tests**: what the tests are called.

The idea behind the three layers is the oldest question in software quality:
does the product do what its documents say, and is there a test that proves
it? Where the layers do not line up, Grove records a *finding*, for example
"the README promises this and no test mentions it".

How it decides is deliberately crude. A sentence and a test "match" if they
share one meaningful word (R-GAP-3, `src/sf_grove/tokens.py`). There is no
understanding involved. This was chosen because it is fast (the scan of this
repository took 0.04 seconds), needs no extra software, and can be explained
in one sentence. A real code parser was considered and postponed until
someone has measured whether it would help (decision D-17).

The honest result of using it on this repository, with fixtures and
background documents excluded as `docs/blueprint.md` section 6 recommends:
373 declared items, 156 code items, 161 test items, six "promised but
untested" findings and 23 "promised but not seen in code" findings. Reading
the six:

- Four are sentences such as "It does not talk to GitHub or to any other
  network service" and "v0 calls no model". Each of these **is** tested,
  thoroughly, in `tests/test_invariants.py`. The test names simply share no
  word with the sentences.
- One is a fragment of a list, not a promise.
- One is a statement of a limit ("The scanner is not a parser") that no test
  could prove.

So on its own repository the finding list pointed at zero real gaps out of
six. Most of the 23 "not seen in code" findings are the same kind of thing:
true statements about what Grove does *not* do, which naturally have no
function named after them. That is not a scandal: the README says plainly
that findings are "a reason to go and read, not a result", and on the small
example project the tool ships with, the one finding is exactly right. But
it does mean the scan's value today is the **map** (where things are, what
is named what, which documents make promises), not the **verdicts**.
Nobody has yet measured how often a finding is right (R-QUAL-10, open as
WO-23), and until that exists no one can say whether a change to the rules
makes them better or worse. *Update:* it is measured (WO-23, 2026-11-13),
on three small projects kept in the repository. About one in three
"untested" findings there is a true gap, and about one in eleven "unseen"
ones; the numbers are in `docs/work-orders.md`.

There is one irony worth knowing. The file that consists of nothing but
promises, `REQUIREMENTS.md`, is not read by the scan at all, because its
name is not on the list of document names (`docs/blueprint.md`, section 6;
WO-22). Grove's own traceability is instead kept by hand: each requirement
names the test file that guards it, and a test checks that those files
exist. That hand-kept chain is more reliable than word overlap, and it is
what actually guided the work in this session.

### 4.4 The single recommendation

`grove recommend` returns one suggested next step, chosen by a fixed order
(R-REC-1): first a gap that a person has marked in a map, then promised
behaviour with no test, then the oldest job that is ready to start, and so
on. It exists so that an agent arriving at an unfamiliar codebase has
somewhere to begin.

For that purpose it is fine. As the factory's "what next" it has a flaw that
follows directly from the previous section: heuristic findings rank above
planned jobs, and a finding cannot be marked as dealt with. On this
repository the answer is always the sentence about GitHub quoted above. A
job created for the project and left `ready` was never suggested, and will
not be for as long as that sentence stays in the README. This is issue 3.

### 4.5 Knowledge

Notes are stored under a short name (a "key"), either for one project or for
the whole workshop. Writing to an existing name adds a revision; nothing is
replaced (R-INV-12). Notes are searchable by their words (R-KNOW-5), can be
listed without searching (R-KNOW-6), and long ones come back as an excerpt
with a table of contents unless the whole text is asked for (R-KNOW-4).

This is the part of Grove that most directly answers "agents forget
everything between sessions", and it is well made: forty simultaneous writes
of one note produce revisions 1 to 40 with none lost
(`tests/test_db.py`). Search matches words, not meaning, which is the
consequence of having no model inside; in exchange it is predictable and
free.

Its weakness is not in how it is built but in where it lives: in the one
folder on the one machine (issue 1).

### 4.6 Work items

A work item is a job: a title, an optional plan, notes, a status (`ready`,
`in_progress`, `review`, `done` or `blocked`) and the name of whoever
created it. Any status may follow any other (R-WORK-3); Grove records what
it is told.

This is the thinnest part, and `docs/analysis.md` section 3.5 already says
so. Checked again in this session: one agent wrote a progress note on a job,
a second agent wrote another, and the first note was gone. Nothing records
who changed a status or when. The name on a job is whatever the caller
typed; it identifies nobody. The repair was specified and had not been
built: an append-only history of every change, with author and time (WO-14),
and the ability to attach references such as a requirement id or a
pull-request link (WO-15).

*Update:* the history is built. An update that changes the status, or that
carries a `note`, adds one line to the job's history with the time, the
author and the status before and after; nothing removes a line. Two agents
can now log progress on one job without erasing each other, as long as they
use `note` and not `notes`, which is still replaced whole. The name on a
line is still whatever the caller typed. References (WO-15) are not built.

What should **not** be read into this section is a wish for Grove to enforce
a workflow. "Any status may follow any other" is correct for a tool that
does not judge. The gap is the missing record, not missing rules.

## 5. What using it from a Claude cloud session was actually like

The task in this session was to add continuous integration (WO-08) and to
write this document. What helped, in order of how much:

1. **The documents in the repository.** `REQUIREMENTS.md` gave every rule an
   id and said whether a test guards it. WO-08 in `docs/work-orders.md` gave
   five acceptance criteria and a record of what had already been considered
   and rejected, which meant the job could be done without asking a single
   question and without re-proposing something already turned down.
2. **The tests that guard the rules.** `tests/test_docs_contract.py` and
   `tests/test_invariants.py` meant that a change which broke a promise
   would fail at once instead of relying on the author to remember it.
3. **The publish check and its hook** (`scripts/check-publish`), with one
   hole, which is issue 5.
4. **Grove itself, as a map.** Scanning the repository and reading the
   findings produced the evidence in section 4.3.

What did not help, and could not: Grove's memory. The session ran on a new
machine. `grove status` reported no projects and suggested that this was
"probably the wrong directory", which in a cloud session is misleading
advice, because there is no right directory to find. The "returning
session" steps in `CLAUDE.md` (list unfinished jobs, search the notes) had
nothing to return to. Anything written into Grove here would have vanished
when the session ended. Everything that crossed between the earlier sessions
and this one crossed as files in git or as the written brief.

*Update:* the brief and the README now say this in advance (issue 1a), so
the next cloud session does not have to find it out.

That is the most important practical finding of this document, so it is
worth stating without softening: **today the factory's shared memory between
Mila and a cloud Claude is the git repository, not Grove.** Grove's notebook
and job board work for agents that sit on the same computer.

## 6. Is the design optimal for a factory of Grok Bot and Claude?

The foundations are right, and it would be a mistake to move them: a shared
tool with no model, no network and no power to act is what a two-vendor
factory with a human approver should want in the middle. The construction is
careful in the ways that matter for agents: one implementation behind two
doors, one answer shape, frozen names, nothing cut short silently, nothing
overwritten.

It is not optimal, for the four reasons given at the start. Put as plainly
as possible:

- It is a good fit for **two agents on one computer with a person approving
  on GitHub**.
- It was **unproven** for Grok Bot until someone connected one (WO-11).
  *Update:* three Grok Bots have now used it on the computer that holds the
  data, and it worked; that is the first bullet observed, not predicted.
- It is a **poor fit, as it stands, for agents on different computers**,
  which includes every Claude cloud session. For those, the repository's
  documents do the job that Grove's notebook was meant to do.
- Its **tracking of who did what was not strong enough** to be the
  factory's record. *Update:* WO-14 exists. For agents on one computer the
  job history is now a usable record of who reported what and when. It is
  still a record of statements (issue 6), and it still does not reach a
  cloud session, so the pull requests remain the record that everyone can
  see.

## 7. Issues found, with a suggested fix for each

Each entry says what is wrong, how it was established, what to do, and
whether it was done here. "Can wait" always comes with the reason.

**1. Grove's memory does not reach a cloud session.**
Established by this session (section 5). The rule "one data directory per
machine" (R-HOME-3, assumption A4) quietly assumes all agents are on one
machine.
*Suggested, cheapest first.* (a) Say it in the brief and the README: in a
session on a temporary machine, Grove is a local map only; anything that
must last goes into the repository's documents and the pull request; an
empty `status` is expected there. A few sentences, no code. (b) Decide
whether a workshop should be movable between machines. An export command was
considered and left out (WO-32), with the note that "a need to move a
workshop between machines" would change the answer. That need now exists. It
would have to be plain text files written and read deterministically, and
they could not be committed to this public repository (R-INV-15 forbids
publishing data directories), so the owner would have to choose where they
live.
*Not suggested:* synchronising over a network. That breaks R-INV-1 and gives
the shared tool exactly the reach the design denies it.
*Not done here.* The brief (`CLAUDE.md`) is the instruction every agent
obeys, so changing it is the owner's call; (b) is a design decision. It can
wait because the repository documents already carry the load, as this
session showed.
*Update: (a) is done,* on the owner's approval of 2026-11-12. `CLAUDE.md`
and the README now say that on a temporary machine Grove is a local map
only, that an empty `status` is expected there, that anything lasting goes
into the repository's documents and the pull request, and that the shared
memory between a cloud session and agents on another machine is the git
repository. No code changed; the `hint` in `status` is as it was.
*(b) stays unbuilt,* and WO-32 stays left out. The reason given above still
holds, and Ume's review reached the same conclusion: git already carries the
load. A need to move a workshop that git cannot meet would reopen it.

**2. Grok Bot had never been connected.** *Now tried; partly measured.*
As first written: stated in the README and as R-GROK-7; nothing in that
session could change it. One further question sat underneath: Grove can
only be used by a program that can start another program on the same
computer. If Mila ran as a hosted service rather than on the machine that
holds the code, she could not use Grove at all, whatever the registration
looked like.
*Suggested then:* do WO-11 before any further feature work for the MCP
side, and as part of it write down where Mila actually runs.
*Update.* That statement is out of date. On 2026-11-12 three Grok Bots
(Mila, Momo and Ume) used Grove over MCP, end to end, on the computer that
holds the data directory. The sixteen tools were listed and ran. This
answers the question underneath: they run where the data is. It also
corrects an assumption made throughout this document, that a Grok Bot can
reach Grove only through MCP: the command line is available to them too.
This is recorded from the owner's brief; it was not watched from the
session that wrote this update.
*One lesson from the trial:* a Grok Bot keeps the tool schemas it read when
its connector started, so after Grove is upgraded the connector must be
restarted or the Grok Bot goes on using the old ones. The README now says
so. It matters at once, because WO-14 adds two parameters.
*Not recorded, and not guessed:* the Grok Bot version, the protocol
revision it spoke, and whether the registration was exactly the README's
shape. WO-11 asks for these in the README, so the order stays open for that
part only. Also unanswered: whether a Grok Bot's model is shown the server
instructions, which WO-20 depends on; WO-20 therefore still waits.

**3. The recommendation puts guesses ahead of planned work and cannot be
told a guess is settled.**
Established by running it (section 4.4). The order is fixed in R-REC-1 and
tested.
*Suggested:* until it changes, treat `recommend` as a way into an unfamiliar
codebase and treat `grove work list` as the queue; one sentence in the tool
description would say so. The real repair is already specified: WO-28 lets
`recommend` skip a finding that an open job refers to, and needs WO-15
first. Whether ready jobs should simply rank above heuristic findings is a
question for the owner, in the same family as A2.
*Not done here:* it changes a tested, documented order. It can wait because
the brief already tells a returning agent to list its jobs first.

**4. A second note on a job erases the first, and status changes leave no
trace.**
Established by running it (section 4.6); first reported in
`docs/analysis.md` 3.5.
*Suggested:* build WO-14 next after WO-11. Of everything open, this is what
a two-agent factory needs most.
*Not done here:* it is a work order of its own, with a database change.
*Update: built* (WO-14, R-WORK-5). Progress logged with `note` is appended
and cannot be erased; every status change is recorded with author and time;
`work get` shows the newest twenty events and the total. `notes` is still
replaced whole, by decision: one way to append is enough.

**5. The publish check let a session link through.** *Fixed here.*
R-INV-15 says no agent session ids are published. The script looked for
passwords and keys but not for session ids, and it read files but never the
commit message. Tried in a scratch repository: a file containing a session
link, committed with a message containing another, passed as "clean". This
matters in practice: a session link had already reached a pull-request
description once, and the tool Claude runs in adds such a link to every
commit message unless told not to.
*Done:* `scripts/check-publish` now refuses the pattern in files and in the
commit message, with three tests (`tests/test_gates.py`).
*Still open:* a pull-request description is typed into GitHub and no local
script can see it, so that remains the author's responsibility. Private
folder names are checked only on a machine that has the uncommitted pattern
file, never in CI. Only the newest commit of a push is checked (WO-26).

**6. "Review" and "done" in Grove are statements, not proof.**
By design (R-SCOPE-3), and correct. It is listed because it is easy to
forget: a job marked `done` by an agent has not thereby been approved by
anyone, and the `author` on it is a typed label.
*Suggested:* nothing in the code. In the factory's own rules, the approval
that counts is the merge on GitHub.

**7. The requirements file is invisible to the scan.**
See section 4.3. Known as WO-22 and rightly postponed until the findings
can be measured (WO-23).
*Suggested:* leave the order as it is.

**8. There is almost no room left for new tool descriptions.**
Measured: 16 054 of 16 384 bytes. WO-14, WO-15, WO-16 and WO-19 each add
settings that must be described.
*Suggested:* do WO-20 (which removes about 1.5 KB of repetition) before any
of them, and WO-11 before WO-20, since WO-20 moves text to a place that Grok
Bot may or may not show to its model. The work-order list implies this
order but does not state it as a dependency.
*Not done here:* it is sequencing advice, not a change.
*Update:* the owner chose to build WO-14 first and to keep WO-20 waiting
until it is known whether server instructions reach a Grok Bot's model.
WO-14 was therefore kept to 312 bytes of description, and one redundant
sentence was removed to make it fit. 16 366 of 16 384 bytes are now used.
The advice has become a hard limit: no further parameter can be described
anywhere until WO-20 is done.

**9. A read-only command creates an empty workshop.**
Seen in section 4.1. Considered and left alone: making `status` refuse to
create anything would need a second way of opening the database, and the
existing warning already tells the agent what happened.

**10. The new CI job could fail without a real defect.**
Some tests in `tests/test_scan_robustness.py` assert that work finishes
within one to three seconds. The margins are wide, but a busy shared machine
is not the author's laptop. This is the reason the check starts as visible
and not required. If one of these tests ever fails in CI, the failure should
be read and the margin reconsidered, not rerun until green (R-QUAL-1).

**11. This document adds to the noise in Grove's scan of itself.**
Every file under `docs/` is read as "what the product declares". The exclude
list recommended in `docs/blueprint.md` section 6 already covers it; nothing
to do.

## 8. What is strong, what is unfinished, and what would be a mistake to "improve"

**Already strong.** The tested invariants (no network, no model, no process
spawning, read-only scans). One implementation behind both doors, with
documents that fail the build when they drift from the code. Honest
reporting of every limit and truncation. Notes that cannot be overwritten.
The discipline, recorded in `docs/work-orders.md`, of arguing each change
down to its smallest form and writing down what was rejected. And from
today, a check on every pull request that runs on a clean machine.

**Unfinished, in the order suggested here.** Proving Grok Bot (WO-11;
*update:* proved in use, with the version and protocol revision still to be
written down). Deciding how cloud sessions take part (issue 1; *update:*
said plainly in the brief, export left unbuilt). The history of work items
(WO-14; *update:* built) and references on them (WO-15). Reclaiming
description space (WO-20) before adding settings; *update:* this now blocks
every new setting. Measuring the findings (WO-23) before
touching the scanner. Hardening the publish check over every commit of a
push (WO-26). A security contact (WO-27), which waits on the owner
(*update:* given; `SECURITY.md` is written).

**Mistakes that would look like improvements.**

- *Putting a model inside Grove* to make the findings or the recommendation
  smarter. The agents are the models. A model in the shared tool would make
  it vendor-specific, costly, changeable and unable to be checked by hand,
  which removes the reasons it is trustworthy.
- *Letting Grove talk to GitHub*, to synchronise jobs with issues or to
  check that a pull request was merged. It would create a second road to the
  main branch and give hidden text in a scanned file something to exploit.
- *A hosted or synchronised Grove.* It would solve issue 1 by giving up the
  property that nothing leaves the machine. If workshops must travel, files
  the owner controls are the way.
- *Enforcing a workflow or locking jobs.* An agent session that dies would
  leave locks behind, and a tool that polices invites agents to work around
  it. Record everything; enforce nothing.
- *Letting Grove certify that work is done.* Approval belongs to the person
  and happens on GitHub.
- *Adding a seventeenth tool, or renaming one.* Stability of the sixteen
  names is worth more than tidiness.
- *A heavier scanner before anyone has measured the current one.* Without
  WO-23, any change to the patterns is an opinion.
- *Deleting things.* It is the one operation that cannot be undone; hiding
  (WO-30) is enough.
- *Growing the CI job* with a matrix of systems, coverage targets or bots
  that merge on their own. The job exists so that a clean machine has run
  the tests before a person decides; anything that decides *for* the person
  defeats the purpose.

## 9. What was considered for this document and left out

- *Placing it in the pull-request description only.* A description is not
  versioned with the code and is not found by the next agent that opens the
  repository.
- *Folding it into `docs/analysis.md`.* That file is a dated study of one
  commit with its own method. This is a different kind of text for a
  different reader.
- *Repeating the requirements.* Rules are cited by id and not restated, so
  there is one place to change them.
- *Changing `CLAUDE.md` for issue 1.* Suggested above; left to the owner.
  (*Update:* the owner approved it; see issue 1.)
- *In the revision: rewriting the original findings as if they had never
  been true.* A reader who compares this document with the work orders
  should be able to see what was found, and then what was done about it.
- *A score or a rating for the design.* A number would hide the four limits
  that matter.

The statements about the present state of the work (what is open, what the
byte count is, what the scan found) are true of the repository on the date
at the top; those marked *Update* are true of the revision. `docs/work-orders.md` is where the current state is kept.
