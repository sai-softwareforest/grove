# Tiny — architecture map

A small hand-written map used by Grove's tests. It is only ever read.

Evidence labels used below:

- `documented` — stated in the project's own README.
- `observed-in-code` — read directly in the source files.
- `untested` — no test was found for it.

## Purpose

Tiny adds two integers and greets a user by name (`README.md` — `documented`).

## Modules

| Module | Role (`observed-in-code`) |
|---|---|
| `src/tiny/calc.py` | `add(a, b)` returns the sum of two integers |
| `src/tiny/greet.py` | `greet(name)` builds a greeting string |

## Risks

- `greet` has no test file at all: nothing under `tests/` imports it. (`observed-in-code`, `untested`)
- Passing an empty name to `greet` returns "Hello, !" rather than raising. (`untested`)

```
documented: this line sits in a code fence and must be ignored
```
