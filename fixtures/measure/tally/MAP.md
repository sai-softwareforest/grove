# tally map

Labels: documented (the README says it), observed-in-code (read in the
source), untested (no test exercises it).

## Reading lines (documented, observed-in-code)

`ParseLine` splits a line at the brackets and the quotes of the common log
format.

The minute is cut from the timestamp as text; no time zone is applied.

## Counting

`Tally.Add` keys by path, or by minute and path when `-by-minute` is set
(observed-in-code). Grouping by minute is untested.

`Top` sorts by count and then by key (documented, observed-in-code).

## Sampling (observed-in-code, untested)

`sample.go` keeps at most 10 000 response times per key and replaces
earlier ones at random after that.

The random source is seeded from the clock, so two runs over the same log
can print different percentiles.

## Output

- Untested: the JSON output.
- Untested: the line that reports how many lines could not be parsed.
- The text table separates its columns with tabs (observed-in-code).

## Missing

The README says gzip logs are read; `main.go` opens the file as plain text
(documented).
