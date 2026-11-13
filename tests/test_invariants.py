"""Fitness tests for the invariants in REQUIREMENTS.md, section 2.

These fail when a change breaks a decided property of the product, whatever
else it does: no network, no model, no process spawning, fixed layering, a
closed set of error codes, deterministic scans.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, TINY
from sf_grove import errors
from sf_grove.service import Grove

SRC = REPO / "src" / "sf_grove"
MODULES = sorted(path for path in SRC.glob("*.py"))

# Standard-library modules that would break an invariant: network access
# (R-INV-1), starting processes or loading code at run time (R-SEC-1). Other
# standard-library modules are fine and need no entry anywhere.
STDLIB_FORBIDDEN = {
    "socket", "socketserver", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib",
    "xmlrpc", "asyncio", "webbrowser", "subprocess", "multiprocessing", "importlib", "runpy", "code", "ctypes",
    "pickle", "marshal",
}  # fmt: skip
# Every third-party module sf_grove may import, and the one module that may
# import it. Adding a row is a dependency decision for the owner (R-INV-14),
# and the only way a model or network client could arrive (R-INV-2).
THIRD_PARTY_ALLOWED = {"pathspec": {"scan"}, "anyio": {"mcp_server"}, "mcp": {"mcp_server"}, "mcp_types": {"mcp_server"}}

# R-QUAL-3: which sibling modules each module may import. The pure parts know
# nothing of storage; only the two outer layers know the tool table.
LAYERING = {
    "__init__": set(),
    "errors": set(),
    "tokens": set(),
    "claims": set(),
    "scan": {"claims"},
    "mapdoc": {"scan"},
    "gaps": {"claims", "tokens"},
    "db": {"errors"},
    "service": {"", "db", "errors", "gaps", "mapdoc", "scan"},
    "tools": {"errors", "service"},
    "cli": {"", "errors", "service", "tools", "mcp_server"},
    "mcp_server": {"", "db", "tools"},
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_OS = {"system", "popen", "startfile", "fork", "forkpty", "kill"}


def _imports(path: Path) -> tuple[set[str], set[str]]:
    """(top-level external modules, sibling sf_grove modules) imported by a file."""
    external: set[str] = set()
    siblings: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            external.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # from . import x / from .x import y
                if node.module:
                    siblings.add(node.module.split(".")[0])
                else:
                    for alias in node.names:
                        siblings.add(alias.name if (SRC / f"{alias.name}.py").exists() else "")
            elif node.module:
                external.add(node.module.split(".")[0])
    return external, siblings


def test_every_module_is_covered_by_the_layering_table() -> None:
    assert {path.stem for path in MODULES} == set(LAYERING)


@pytest.mark.parametrize("path", MODULES, ids=lambda path: path.stem)
def test_modules_import_only_what_the_invariants_allow(path: Path) -> None:
    external, siblings = _imports(path)
    for name in sorted(external):
        assert name not in STDLIB_FORBIDDEN, f"{path.name} imports {name!r}; see REQUIREMENTS.md R-INV-1, R-SEC-1"
        if name not in sys.stdlib_module_names:
            assert path.stem in THIRD_PARTY_ALLOWED.get(name, set()), (
                f"{path.name} imports third-party {name!r}; see REQUIREMENTS.md R-INV-2, R-INV-14"
            )
    assert siblings <= LAYERING[path.stem], f"{path.name} imports {sorted(siblings - LAYERING[path.stem])}; see R-QUAL-3"


@pytest.mark.parametrize("path", MODULES, ids=lambda path: path.stem)
def test_no_module_evaluates_code_or_starts_a_process(path: Path) -> None:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in FORBIDDEN_CALLS, f"{path.name}:{node.lineno} calls {node.func.id}()"
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
            assert node.attr not in FORBIDDEN_OS and not node.attr.startswith(("exec", "spawn")), (
                f"{path.name}:{node.lineno} uses os.{node.attr}"
            )


def test_error_codes_are_a_closed_set() -> None:
    assert errors.ERROR_CODES == ("not_found", "invalid", "io", "internal")
    # An unknown code never leaves Grove: it is reported as internal.
    assert errors.fail("made_up", "x")["error"]["code"] == "internal"
    assert errors.GroveError("made_up", "x").code == "internal"


def test_ordinary_commands_do_not_load_the_mcp_sdk(tmp_path: Path) -> None:
    code = (
        "import sys\n"
        "from sf_grove.cli import main\n"
        f"assert main(['--home', {str(tmp_path / 'home')!r}, 'status']) == 0\n"
        "loaded = sorted(name for name in sys.modules if name.split('.')[0] in ('mcp', 'mcp_types', 'anyio'))\n"
        "assert not loaded, loaded\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr


def _picture(grove: Grove, name: str) -> dict:
    """Everything a scan produced, without the parts allowed to differ (ids, times)."""

    def all_pages(read) -> list[dict]:
        items: list[dict] = []
        while True:
            page = read(len(items))
            items.extend(page["items"])
            if len(items) >= page["total"]:
                return items

    blueprint = all_pages(lambda offset: grove.blueprint_get(name, limit=200, offset=offset))
    findings = all_pages(lambda offset: grove.gaps(name, limit=200, offset=offset))
    recommendation = grove.recommend_next(name)
    return {
        "items": [{key: value for key, value in item.items() if key != "id"} for item in blueprint],
        "findings": [
            {
                "kind": finding["kind"],
                "summary": finding["summary"],
                "evidence": {key: value for key, value in finding["evidence"].items() if key != "item_ids"},
            }
            for finding in findings
        ],
        "recommendation": (recommendation["action"], recommendation["rationale"], (recommendation["finding"] or {}).get("summary")),
    }


def test_scans_are_deterministic(tmp_path: Path) -> None:
    pictures = []
    for run in range(2):
        with Grove(tmp_path / f"home-{run}") as grove:
            grove.project_create("tiny", str(TINY))
            grove.project_create("grove-src", str(SRC))
            first = grove.scan("tiny")
            grove.scan("grove-src")
            again = grove.scan("tiny")  # a rescan in the same home gives the same result too
            for key in ("items", "findings", "caps", "warnings", "skipped_files", "long_lines", "gap_notes"):
                assert first[key] == again[key], key
            pictures.append({name: _picture(grove, name) for name in ("tiny", "grove-src")})
    assert pictures[0] == pictures[1]
    assert pictures[0]["grove-src"]["items"], "the second project should not be empty"
