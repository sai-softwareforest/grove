# Grove — notes for Claude Code

Grove is a workshop, not an autonomous coder. It maps a codebase, records a
three-layer blueprint (declared / actual / tests), stores searchable knowledge
and tracks local work items. You do the work; Grove is where you look things
up and keep track.

## How to use it

- Set the data directory first: `export GROVE_HOME=~/.grove` (or pass
  `--home DIR`). Never point it inside a project you scan. Machine-specific
  paths, if any, belong in `LOCAL.md`, which is not committed.
- Prefer the `grove` CLI (`uv run grove` from this directory, or
  `.venv/bin/grove`) or the `grove_*` MCP tools. Do not read or edit
  `grove.db` directly.
- Output is a JSON envelope: `{"ok": true, "data": ...}` or
  `{"ok": false, "error": {"code", "message"}}`. Exit code 0 or 1.

A typical session:

```sh
grove project create NAME --root PATH   # once per codebase
grove scan NAME                         # after code or docs change
grove gaps NAME                         # what looks unproven
grove recommend NAME                    # one suggested next step
grove search "words"                    # what is already known
grove work create NAME --title "..."    # then: work update ID --status in_progress|review|done
grove knowledge write NAME --key slug --title "..." --file note.md
```

## Rules

- Do not ask Grove to implement or ship anything. It does not write code, and
  it does not open pull requests or contact GitHub.
- When working on this repository, do not `git push`, force-push, add or
  change a remote, or open issues or pull requests unless the user explicitly
  asks for that exact action.
- Before every push, run `scripts/check-publish` and do not push if it fails.
  Do not use `--no-verify` to skip the hook. The check looks for secrets,
  credentials, and private or machine-specific material.
- Never commit secrets, credentials, data directories, or machine-specific
  paths. `LOCAL.md` and `scripts/check-publish.local` stay uncommitted.
- Scans are read-only. Grove never writes inside a scanned project.
- Findings are heuristics (token overlap). Read the code before acting on one.
- Knowledge is append-only by revision: writing an existing key adds a
  revision, it never overwrites.

## Working on Grove itself

- `uv sync && uv run pytest -q` must stay green.
- Tests always use an isolated temporary `GROVE_HOME`.
- The default data directory is `~/.grove`. Keep it outside any scanned project.
- v0 scope is fixed: sixteen MCP tools, no network, no model calls.
- Everyday return path (new session; picks up this file and the tree):
  run `claude` from the repository root.
- After cloning, run `git config core.hooksPath .githooks` so the pre-push
  publish check is installed.
