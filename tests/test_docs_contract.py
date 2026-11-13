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
from pathlib import Path

import pytest

from conftest import REPO
from sf_grove import db
from sf_grove.cli import build_parser
from sf_grove.mcp_server import INSTRUCTIONS, tool_definitions
from sf_grove.service import RECOMMEND_ACTIONS, Grove
from sf_grove.tools import TOOLS, TOOLS_BY_NAME

REQUIREMENTS = (REPO / "REQUIREMENTS.md").read_text(encoding="utf-8")
BLUEPRINT = (REPO / "docs" / "blueprint.md").read_text(encoding="utf-8")
WORK_ORDERS = (REPO / "docs" / "work-orders.md").read_text(encoding="utf-8")
README = (REPO / "README.md").read_text(encoding="utf-8")
CLAUDE_MD = (REPO / "CLAUDE.md").read_text(encoding="utf-8")

TOOLS_LIST_BUDGET_BYTES = 16_384  # R-GROK-3

_REQUIREMENT_ID = re.compile(r"\bR-[A-Z]+-\d+\b")
_WORK_ORDER_ID = re.compile(r"\bWO-\d{2}\b")


@pytest.mark.parametrize("name,text", [("REQUIREMENTS.md", REQUIREMENTS), ("docs/blueprint.md", BLUEPRINT), ("README.md", README)])
def test_every_tool_is_named_in_the_documents(name: str, text: str) -> None:
    missing = [tool.name for tool in TOOLS if f"`{tool.name}`" not in text]
    assert not missing, f"{name} does not mention {missing}"


def test_the_requirements_operation_table_matches_the_tool_table_and_the_cli() -> None:
    section = REQUIREMENTS.split("### 6.3 Operations", 1)[1].split("### 6.4", 1)[0]
    rows = re.findall(r"^\| `(grove_\w+)` \| `grove ([^`]+)` \| (yes|no) \|$", section, flags=re.MULTILINE)
    assert [row[0] for row in rows] == [tool.name for tool in TOOLS]
    parser = build_parser()
    for tool_name, command, writes in rows:
        # "Writes" in the table is the opposite of the tool's read-only hint.
        assert (writes == "no") is TOOLS_BY_NAME[tool_name].read_only, tool_name
        # The command words (before any placeholder or option) are real CLI commands.
        words = []
        for word in command.split():
            if word.isupper() or word.startswith(("[", "-")):
                break
            words.append(word)
        action = parser._subparsers._group_actions[0]  # noqa: SLF001 - argparse has no public lookup
        sub = action.choices[words[0]]
        if len(words) > 1:
            assert words[1] in sub._subparsers._group_actions[0].choices, command  # noqa: SLF001
        # Every --flag the table shows is accepted by that command.
        leaf = sub if len(words) == 1 else sub._subparsers._group_actions[0].choices[words[1]]  # noqa: SLF001
        known = {option for act in leaf._actions for option in act.option_strings}  # noqa: SLF001
        for flag in re.findall(r"--[a-z-]+", command):
            assert flag in known, f"{command}: {flag} is not a flag of the command"


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
    assert tables == ["blueprint_items", "findings", "knowledge", "knowledge_fts", "projects", "work_items"]
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
    assert len(defined_requirements) > 80
    defined_orders = set(re.findall(r"^### (WO-\d{2}) ", WORK_ORDERS, flags=re.MULTILINE))
    summary_orders = re.findall(r"^\| (WO-\d{2}) \|", WORK_ORDERS, flags=re.MULTILINE)
    assert summary_orders == sorted(defined_orders), "the summary table and the sections list the same orders"

    documents = {
        "REQUIREMENTS.md": REQUIREMENTS,
        "docs/blueprint.md": BLUEPRINT,
        "docs/work-orders.md": WORK_ORDERS,
        "docs/analysis.md": (REPO / "docs" / "analysis.md").read_text(encoding="utf-8"),
        "docs/industry-survey.md": (REPO / "docs" / "industry-survey.md").read_text(encoding="utf-8"),
        "CHANGELOG.md": (REPO / "CHANGELOG.md").read_text(encoding="utf-8"),
        "README.md": README,
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
    assert str(TOOLS_LIST_BUDGET_BYTES)[:2] + " " + str(TOOLS_LIST_BUDGET_BYTES)[2:] in REQUIREMENTS  # "16 384"
    assert 100 < len(INSTRUCTIONS) < 2000


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


def test_the_documents_agree_on_the_data_directory_rule() -> None:
    for name, text in (("README.md", README), ("CLAUDE.md", CLAUDE_MD), ("REQUIREMENTS.md", REQUIREMENTS)):
        assert "home_source" in text, f"{name} does not tell the reader to check home_source"
        assert "~/.grove" in text, name
    # No tracked document tells an agent to rely on an exported variable persisting.
    assert "export GROVE_HOME=~/.grove" not in CLAUDE_MD
