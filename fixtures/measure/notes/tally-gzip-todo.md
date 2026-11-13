# Reading gzip logs

The README says gzip-compressed logs are read transparently. They are
not: `main.go` opens the file as plain text and every line fails to parse.

To do: look at the first two bytes (1f 8b) and wrap the reader with
`compress/gzip`. Rotated logs are the usual case, so this matters.
