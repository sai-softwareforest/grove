# Grove — notes for Claude Code

Grove is a workshop, not an autonomous coder. It maps a codebase, records a
three-layer blueprint (declared / actual / tests), stores searchable knowledge
and tracks local work items. You do the work; Grove is where you look things
up and keep track.

## How to use it

- Set the data directory first: `export GROVE_HOME=/workspace/grove-data`
  (or pass `--home DIR`). Never point it inside a project you scan.
- Prefer the `grove` CLI (`/workspace/grove/.venv/bin/grove`, or `uv run grove`
  from this directory) or the `grove_*` MCP tools. Do not read or edit
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
- Scans are read-only. Grove never writes inside a scanned project.
- Findings are heuristics (token overlap). Read the code before acting on one.
- Knowledge is append-only by revision: writing an existing key adds a
  revision, it never overwrites.

## Working on Grove itself

- `uv sync && uv run pytest -q` must stay green.
- Tests always use an isolated temporary `GROVE_HOME`.
- Recommended data directory on this computer: `GROVE_HOME=/workspace/grove-data`.
- v0 scope is fixed: sixteen MCP tools, no network, no model calls.
- Everyday return path (new session; picks up this file and the tree):
  `cd /workspace/grove && claude`
- How to resume the original Fable v0 build session is recorded in
  `BUILD_NOTES.md`. Do not move or purge Claude project data.
