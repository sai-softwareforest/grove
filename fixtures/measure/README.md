# The measuring corpus

A small labelled corpus for one question: how often is a Grove finding
right, and does a search find the note (`REQUIREMENTS.md` R-QUAL-10, work
order WO-23). `tests/test_measure.py` reads it, computes the numbers and
holds each to a recorded floor. To print today's numbers with every wrong
finding and every missed gap:

```sh
uv run python tests/test_measure.py
```

Nothing here is used by any other test. The projects are only ever read.

## What is here

| Path | What it is |
|---|---|
| `parcel/` | A Python library: shipping prices, tracking codes, address labels |
| `shelf/` | A TypeScript library: an office lending library |
| `tally/` | A Go command: counts and percentiles from access logs |
| `NAME.labels.json` | The true gaps of project NAME, listed by hand, one list per finding kind |
| `notes/` | Sixteen notes, as an agent would leave them in Grove about these projects |
| `queries.json` | Twenty-six queries, each with the notes it should find |

Each project has a README, source, tests that pass in its own language,
and a `MAP.md` with evidence labels. The labels files sit beside the
projects, not inside them, so a scan never walks them.

## How the lists were made

The projects were written first, as small projects are: a README that
describes behaviour, not files; tests named in their own words; one or two
promises the code does not keep; one or two modules nobody documented. The
lists were then written by reading each project, before Grove was run on
it. After the first run every disagreement was read again against the
rules below; no label was changed.

The queries were changed twice after the first run, and both changes are
named here because they moved the numbers. Two were added (`test`,
`price`): until then no query returned more than two notes, so the order
of results was not being measured at all. One was replaced: `reminder
text` was meant to ask for an identifier by its words, but the note holds
both words on their own, so it passed without testing that; `parse line`
asks for `ParseLine` and does test it.

**The corpus is not neutral.** Its author knew the heuristic. It is three
projects and 51 true gaps. Read the numbers as a line that a change must
not fall below, and as a list of concrete misses to look at; do not read
them as the precision to expect on another project.

## What counts as a true gap

- **`declared_untested`.** A statement in the project's documents that
  promises a behaviour, or states a limit as something the code does
  (refuses, cuts off, ends with an error), and that no test runs and
  checks. A sentence with several promises is a gap when one of them has
  no test. Not gaps: installation and usage instructions, what the
  product is, thanks, licences, a table that lists files, and a limit
  that only says a feature is absent ("not supported").
- **`declared_unseen`.** A statement that promises a behaviour for which
  the project holds no code. A promise that is implemented but untested
  is not one; a statement that a feature is absent promises nothing.
- **`actual_undocumented`.** A source file with behaviour of its own (not
  a test, not an empty package file, not a file of re-exports) whose
  purpose no document describes, by its name or by what it does. A file
  whose behaviour the README describes without naming the file is
  documented.
- **`map_untested`.** A statement in the project's map that its author
  marks as having no test: by the label on the statement, on its heading,
  on its table row or on the lead-in above it, or in plain words ("has
  none"). The legend is not a statement. A sentence that uses the word
  for something else ("nothing here is untested") is not a gap.

Every entry has a `why`. The `line` is where the statement starts in the
file; it is for the reader and is checked by a test, but matching does
not use it.

## When a finding counts

A finding counts for a listed gap when both are in the same file and one
text holds the other, compared as lower-case words (punctuation, Markdown
marks and line breaks do not count). So a map block that carries its
labels counts for the statement inside it. A finding about a file
(`actual_undocumented`) counts on the path alone.

- **Precision** of a kind: of the findings of that kind, the share that
  count for a listed gap.
- **Recall** of a kind: of the listed gaps of that kind, the share that
  some finding counts for.

Both are taken over the three projects together. The three kinds a scan
computes are read after the scan and before the map is ingested, because
an ingested map adds declared and actual items of its own and the lists
were made from the projects' own documents. `map_untested` is read after
the ingest.

## Search

The notes are written to an empty data directory, at workspace level,
with the file name as the key and the first line as the title. Each query
is asked once and judged on its first ten results:

- **Recall**: the share of the query's relevant notes that came back,
  averaged over the queries that have a relevant note.
- **Reciprocal rank**: one over the place of the first relevant note, 0
  when none came back, averaged the same way. This is the number that
  moves when the order of results changes.
- **Precision**: of all the notes returned, over every query, the share
  that was relevant.

A note is relevant to a query when a reader who typed the query would
want it; a note that only uses the word in passing is not. One query
should find nothing.

## Changing the corpus

Adding a project, a label or a query changes the numbers, and so the
floors. Do it in a change of its own, never together with a change to a
pattern, to the scoring or to the search: otherwise nobody can tell which
of the two moved a number. Keep it small; public benchmark sets and mined
repositories were left out on purpose (WO-23).
