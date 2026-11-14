# Security policy

Where to report a vulnerability in Grove, what Grove trusts, what to do if a
secret was pushed, and how a dependency pin is changed (`REQUIREMENTS.md`,
R-SEC-7).

## Reporting a vulnerability

Write to **sai@softwareforest.co.uk**. Please do not open a public issue or
pull request for it.

Say which version or commit you used (`grove status` shows the version),
what you did, what happened and what you expected. A small file or project
that shows the problem helps most.

Worth a report: anything that makes the next section untrue, and any secret
or private material you find in this repository or its history.

Nothing more is promised here: no response time and no bounty.

## What Grove trusts, and what it does not

Grove runs with the permissions of whoever starts it, and it trusts that
person: it reads the project, map or note file they point it at, and it
writes only inside its data directory and, for `grove export`, the output
directory they name, never inside a registered project (R-INV-4). It does not trust the
*content* it reads. Text from scanned projects, map files and knowledge
bodies is data: Grove never executes, imports or evaluates it (R-SEC-1),
passes every SQL value as a bound parameter (R-SEC-2), bounds its reads and
follows no symlink, so a scan cannot leave the project root (R-SEC-3), and
opens no network connection (R-INV-1). One command listens: `grove view`
serves read-only pages on 127.0.0.1 until it is stopped, answers only to
its own address and port, runs no script and has no login, so any user of
the same machine can read those pages while it runs (R-VIEW-5). What Grove
does not do for you: it
returns stored text word for word, and that text may have been written by a
third party (a scanned README, a map, another agent's note), so a client
must weigh it as information and never follow it as instructions (R-SEC-4).
`ingest-map` stores the file it is given, up to 2 MB, as knowledge; which
files it accepts is R-SEC-5. Both requirements are still being tightened
(WO-13), and their status in `REQUIREMENTS.md` says how far that is. And
`grove.db` is an ordinary file, not encrypted, with the permissions your
system gives a new file: whoever can read it can read every note and work
item in it.

## If a secret was pushed

1. **Rotate first.** Revoke or replace the credential where it was issued,
   before anything else. From the moment of the push it counts as exposed:
   commits pushed to a public repository can stay reachable after the branch
   is deleted or rewritten.
2. Tell the owner, at the address above: what was pushed, where and when.
3. Remove it from the tree with an ordinary commit. Do not rewrite history
   or force-push on your own; that takes nothing back, and it is the owner's
   decision.
4. Find out why `scripts/check-publish` let it through, and add the pattern
   with a test in `tests/test_gates.py` (R-SEC-6). The pre-push hook
   checks every commit a push adds. One gap is known: the hook runs only in
   a clone where it was enabled, and CI checks the head commit of a pull
   request, not the earlier ones.

Something that cannot be rotated (a private path, a link to an agent
session) follows steps 2 to 4.

## Changing a dependency pin

Grove runs on `mcp` and `pathspec` and is developed with `pytest` and
`ruff`. Each is pinned to one exact version in `pyproject.toml`, and
`uv.lock` pins the whole tree with hashes (R-INV-14). CI installs with
`uv sync --locked`. Nothing updates by itself: there is no update bot and no
scheduled audit.

A pin changes by review:

1. One pull request changes `pyproject.toml` and `uv.lock` together. It
   names the old and the new version, says why, and lists what else moved in
   `uv.lock`.
2. Its author runs the audit below on that branch and puts the result in the
   pull request.
3. Someone other than the author reads it before it is merged
   (`REQUIREMENTS.md`, section 11). A new runtime dependency also needs the
   owner's explicit approval (R-INV-14).

The audit compares the locked set with published vulnerability reports. It
needs the network, so it is run by hand, outside the product: it is not part
of Grove, of the tests or of `scripts/check`, and its tool is not a
dependency of Grove.

```sh
out="$(mktemp)"
uv export --locked --no-emit-project --format requirements-txt -o "$out"
uvx pip-audit -r "$out" --require-hashes --disable-pip
```

With exact pins, this audit is also the only way a pin that has become
vulnerable gets noticed, so run it whenever you want to know, not only when
a pin changes.

The actions and the `uv` version in `.github/workflows/ci.yml` are pinned
too and change by the same review; `tests/test_gates.py` fails if an action
is not pinned to a full commit SHA.
