# tally

tally reads web server access logs and prints how many requests each path
received, with response-time percentiles. It is a single binary with no
configuration file.

## Build

```sh
go build -o tally .
```

Go 1.22 or later.

## Usage

```sh
tally -top 10 access.log
cat access.log | tally -json
```

With no file argument tally reads standard input.

## Behaviour

Lines that are empty or start with `#` are skipped. A line that cannot be
parsed is counted and reported at the end; it never stops the run.
Query strings are removed from the path before counting, so `/search?q=a`
and `/search?q=b` are one path. Paths are compared case-sensitively.
Status codes of 500 and above are counted separately as errors.

Percentiles use the nearest-rank method. The 50th, 90th and 99th
percentile are printed for every path. No percentile is given for a path
with fewer than five requests.

Paths are listed by request count, largest first; ties are broken by
path. `-json` prints one JSON object per path instead of the text table.
`-top N` limits the output to the N busiest paths.

Requests can be grouped per minute with `-by-minute`.

Gzip-compressed logs are read transparently.

## Layout

| File | Purpose |
|---|---|
| `parse.go` | one log line to a request |
| `bucket.go` | counting per path and per minute |
| `percentile.go` | nearest-rank percentiles |
| `render.go` | the text table and the JSON output |

## Limitations

- Only the common log format with a trailing response time is understood.
- A line longer than 64 KB ends the run with an error.
- IPv6 addresses in brackets are not handled.
