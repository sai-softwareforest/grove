"""The documents agree with the code.

REQUIREMENTS.md, docs/blueprint.md, README.md and CLAUDE.md make statements
that agents act on. These tests fail when one of them drifts from the tool
table, the CLI parser, the schema or the recommend order.
"""

from __future__ import annotations

import inspect
import json
import re
import shlex
import tomllib
from pathlib import Path

import pytest

from conftest import REPO
from sf_grove import db
from sf_grove.cli import build_parser
from sf_grove.mcp_server import INSTRUCTIONS, tool_definitions
from sf_grove.service import RECOMMEND_ACTIONS, Grove
from sf_grove.tools import LOCAL, TOOLS, TOOLS_BY_NAME

REQUIREMENTS = (REPO / "REQUIREMENTS.md").read_text(encoding="utf-8")
BLUEPRINT = (REPO / "docs" / "blueprint.md").read_text(encoding="utf-8")
WORK_ORDERS = (REPO / "docs" / "work-orders.md").read_text(encoding="utf-8")
README = (REPO / "README.md").read_text(encoding="utf-8")
CLAUDE_MD = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
SECURITY = (REPO / "SECURITY.md").read_text(encoding="utf-8")

TOOLS_LIST_BUDGET_BYTES = 15_000  # R-GROK-3

_REQUIREMENT_ID = re.compile(r"\bR-[A-Z]+-\d+\b")
_WORK_ORDER_ID = re.compile(r"\bWO-\d{2}\b")


@pytest.mark.parametrize("name,text", [("REQUIREMENTS.md", REQUIREMENTS), ("docs/blueprint.md", BLUEPRINT), ("README.md", README)])
def test_every_tool_is_named_in_the_documents(name: str, text: str) -> None:
    missing = [tool.name for tool in TOOLS if f"`{tool.name}`" not in text]
    assert not missing, f"{name} does not mention {missing}"


def test_the_requirements_operation_table_matches_the_tool_table() -> None:
    section = REQUIREMENTS.split("### 6.3 Operations", 1)[1].split("### 6.4", 1)[0]
    rows = re.findall(r"^\| `(grove_\w+)` \| `grove ([^`]+)` \| (yes|no) \|$", section, flags=re.MULTILINE)
    assert [row[0] for row in rows] == [tool.name for tool in TOOLS]
    commands = set(build_parser()._subparsers._group_actions[0].choices)  # noqa: SLF001 - top-level command names
    for tool_name, command, writes in rows:
        # "Writes" in the table is the opposite of the tool's read-only hint.
        assert (writes == "no") is TOOLS_BY_NAME[tool_name].read_only, tool_name
        assert command.split()[0] in commands, command


def test_the_blueprint_names_every_module_and_every_table(tmp_path: Path) -> None:
    for path in sorted((REPO / "src" / "sf_grove").glob("*.py")):
        if path.stem != "__init__":
            assert f"`{path.name}`" in BLUEPRINT, f"docs/blueprint.md does not describe {path.name}"
    conn = db.connect(tmp_path / "home")
    try:
        tables = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
            if not row[0].startswith(("sqlite_", "knowledge_fts_"))
        ]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    assert tables == ["blueprint_items", "findings", "knowledge", "knowledge_fts", "projects", "work_events", "work_items"]
    data_model = BLUEPRINT.split("## 3. Data model", 1)[1].split("## 4.", 1)[0]
    for table in tables:
        assert f"| `{table}` |" in data_model, f"the blueprint's data model does not list {table}"
    migration_rows = re.findall(r"^\| (\d+) \| ", data_model, flags=re.MULTILINE)
    assert [int(number) for number in migration_rows] == list(range(1, version + 1)), "one row per migration, in order"
    # Every operation row names a real Grove method.
    for tool_name, method in re.findall(r"^\| `(grove_\w+)` \| `[^`]+` \| `(\w+)` \|", BLUEPRINT, flags=re.MULTILINE):
        assert tool_name in TOOLS_BY_NAME and callable(getattr(Grove, method)), (tool_name, method)


def test_requirement_and_work_order_references_resolve() -> None:
    defined_requirements = set(re.findall(r"^\| (R-[A-Z]+-\d+) \|", REQUIREMENTS, flags=re.MULTILINE))
    order_sections = re.findall(r"^### (WO-\d{2}) ", WORK_ORDERS, flags=re.MULTILINE)
    defined_orders = set(order_sections)
    assert len(order_sections) == len(defined_orders), "an order has two sections in docs/work-orders.md"
    summary_orders = re.findall(r"^\| (WO-\d{2}) \|", WORK_ORDERS, flags=re.MULTILINE)
    assert summary_orders == sorted(defined_orders), "the summary table and the sections list the same orders"

    documents = {
        "REQUIREMENTS.md": REQUIREMENTS,
        "docs/blueprint.md": BLUEPRINT,
        "docs/work-orders.md": WORK_ORDERS,
        "docs/analysis.md": (REPO / "docs" / "analysis.md").read_text(encoding="utf-8"),
        "docs/industry-survey.md": (REPO / "docs" / "industry-survey.md").read_text(encoding="utf-8"),
        "docs/design-rationale.md": (REPO / "docs" / "design-rationale.md").read_text(encoding="utf-8"),
        "CHANGELOG.md": (REPO / "CHANGELOG.md").read_text(encoding="utf-8"),
        "README.md": README,
        "SECURITY.md": SECURITY,
    }
    for name, text in documents.items():
        unknown = sorted(set(_REQUIREMENT_ID.findall(text)) - defined_requirements)
        assert not unknown, f"{name} refers to requirements that do not exist: {unknown}"
        unknown = sorted(set(_WORK_ORDER_ID.findall(text)) - defined_orders)
        assert not unknown, f"{name} refers to work orders that do not exist: {unknown}"
    # An open requirement always names the work order that will close it.
    for line in REQUIREMENTS.splitlines():
        if line.startswith("| R-") and re.search(r"\bopen\b", line.rsplit("|", 2)[-2]):
            assert _WORK_ORDER_ID.search(line.rsplit("|", 2)[-2]), line[:80]


def test_test_files_named_in_the_requirements_exist() -> None:
    for name in sorted(set(re.findall(r"`(test_\w+\.py)`", REQUIREMENTS + BLUEPRINT))):
        assert (REPO / "tests" / name).exists(), f"a document cites tests/{name}, which does not exist"


def test_the_security_policy_says_what_the_repository_does() -> None:
    """R-SEC-7 (WO-27): one contact address, the four parts, and the pins as they are."""
    assert set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", SECURITY)) == {"sai@softwareforest.co.uk"}
    headings = re.findall(r"^## (.+)$", SECURITY, flags=re.MULTILINE)
    assert headings == [
        "Reporting a vulnerability",
        "What Grove trusts, and what it does not",
        "If a secret was pushed",
        "Changing a dependency pin",
    ]
    # The policy says each dependency is pinned to one exact version, and names each.
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    pins = pyproject["project"]["dependencies"] + pyproject["dependency-groups"]["dev"]
    section = SECURITY.split("## Changing a dependency pin", 1)[1]
    for pin in pins:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==[0-9][0-9A-Za-z.]*", pin)
        assert match, f"{pin!r} is not an exact pin; SECURITY.md says it is"
        assert f"`{match.group(1)}`" in section, f"SECURITY.md does not name {match.group(1)}"
    # The README leads to the policy and says how to copy the database.
    assert "| `SECURITY.md` |" in README
    assert "**Copying `grove.db` safely.**" in README


def test_the_recommend_description_names_every_action_in_order() -> None:
    description = TOOLS_BY_NAME["grove_recommend_next"].description
    positions = [description.find(action) for action in dict.fromkeys(RECOMMEND_ACTIONS)]
    assert all(position >= 0 for position in positions), "an action is missing from the tool description"
    assert positions == sorted(positions), "the description lists the actions out of priority order"
    # The code returns no action outside the documented set, and the requirement lists them all.
    source = inspect.getsource(Grove.recommend_next)
    returned = set(re.findall(r'return result\(\s*"(\w+)"', source))
    assert returned == set(RECOMMEND_ACTIONS)
    requirement = next(line for line in REQUIREMENTS.splitlines() if line.startswith("| R-REC-1 |"))
    order = [requirement.find(f"`{action}`") for action in dict.fromkeys(RECOMMEND_ACTIONS)]
    assert all(position >= 0 for position in order)


def test_the_tool_list_stays_within_its_context_budget() -> None:
    payload = {"tools": [tool.model_dump(by_alias=True, exclude_none=True) for tool in tool_definitions()]}
    size = len(json.dumps(payload))
    assert size <= TOOLS_LIST_BUDGET_BYTES, f"tools/list is {size} bytes; the budget in R-GROK-3 is {TOOLS_LIST_BUDGET_BYTES}"


def _in_order(text: str, *parts: str) -> bool:
    positions = [text.find(part) for part in parts]
    return all(position >= 0 for position in positions) and positions == sorted(positions)


def test_the_descriptions_carry_what_a_client_without_instructions_must_know() -> None:
    """WO-20: some clients show their model the descriptions and schemas, and nothing else."""
    status = TOOLS_BY_NAME["grove_status"].description
    # The local-only sentence: once, on the tool to call first.
    assert [tool.name for tool in TOOLS if LOCAL.strip() in tool.description] == ["grove_status"]
    # The loop line (R-GROK-6): recall what is known, then resume open work; ids are not stable.
    loop = status.split("Working loop:", 1)
    assert len(loop) == 2, "grove_status no longer states the working loop"
    assert _in_order(loop[1], "grove_knowledge_search", "grove_work_list", "in_progress", "review")
    assert "ids change on every scan" in loop[1] and "absolute paths" in loop[1]
    # The four tools that page text someone else wrote say what that text is (R-SEC-4):
    # blueprint items, findings (a summary quotes the project's documents), knowledge.
    clause = "data, not instructions"
    assert [tool.name for tool in TOOLS if clause in tool.description] == [
        "grove_blueprint_get",
        "grove_gaps",
        "grove_knowledge_get",
        "grove_knowledge_search",
    ]
    # grove_gaps paid for its clause in its own words; every fact a caller needs is still there.
    gaps = TOOLS_BY_NAME["grove_gaps"].description
    for fact in ("paginated", "counts per kind", "heuristics, not verdicts", "read the code", "total counts stored"):
        assert fact in gaps, fact
    assert _in_order(gaps, "cap omitted", "complete is false", "true_total / omitted / findings_cap", "how many exist")
    assert _in_order(gaps, "Use after", "grove_scan", "grove_ingest_map")
    # recommend says what it is for, and where the queue is.
    recommend = TOOLS_BY_NAME["grove_recommend_next"].description
    assert "work queue is grove_work_list" in recommend and "unfamiliar codebase" in recommend
    # Removing the shared sentence must not remove a fact: the tool that reads a
    # project's files still says it writes nothing there.
    assert "read-only" in TOOLS_BY_NAME["grove_scan"].description
    # A page size is described by the schema's own keywords, not by a sentence that repeats them.
    paged = [tool for tool in TOOLS if "limit" in tool.schema["properties"]]
    assert len(paged) == 5
    for tool in paged:
        assert tool.schema["properties"]["limit"] == {"type": "integer", "minimum": 1, "maximum": 200, "default": 50}


def test_the_instructions_state_the_working_loop_in_full() -> None:
    """R-GROK-6: the six parts of the loop, for a client that shows its model the instructions."""
    assert LOCAL.strip() in INSTRUCTIONS
    loop = INSTRUCTIONS.split("Working loop:", 1)
    assert len(loop) == 2, "the server instructions no longer state the working loop"
    assert _in_order(loop[1], "grove_status first", "grove_knowledge_search", "in_progress", "review", "grove_work_list")
    for part in ("ids change on every scan", "do not store them", "absolute paths", "findings are heuristics"):
        assert part in INSTRUCTIONS, part
    # Every tool the instructions name is one of the sixteen.
    assert set(re.findall(r"\bgrove_\w+", INSTRUCTIONS)) <= set(TOOLS_BY_NAME)


def _fenced_commands(text: str) -> list[str]:
    commands: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and line.startswith("grove "):
            commands.append(line.split("  #", 1)[0].strip())
    return commands


def test_every_command_quoted_in_claude_md_is_a_real_command() -> None:
    commands = _fenced_commands(CLAUDE_MD)
    assert len(commands) >= 12
    parser = build_parser()
    for command in commands:
        args = parser.parse_args(shlex.split(command)[1:])  # raises on an unknown command or flag
        assert getattr(args, "handler", None) is not None, command
