"""The sixteen input schemas, compared with a stored copy (R-INV-9, R-COMPAT-2).

`tests/snapshots/tool_input_schemas.json` holds the input schema of every
tool as an MCP client receives it. The test fails when the tool table and the
file differ, so a schema never changes by accident: whoever changes one also
updates the file, and the reviewer sees the change to the contract as a diff
of its own.

To update the file after an intended change:

    uv run python tests/test_tool_schemas.py --write

Without `--write` the same command prints what differs and changes nothing.
The test never writes the file, and no environment variable makes it pass.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from conftest import REPO
from sf_grove.tools import TOOLS

SNAPSHOT = REPO / "tests" / "snapshots" / "tool_input_schemas.json"
UPDATE = "uv run python tests/test_tool_schemas.py --write"


def current_schemas() -> dict[str, Any]:
    return {tool.name: tool.schema for tool in TOOLS}


def render(schemas: dict[str, Any]) -> str:
    """The one layout of the stored file: key order kept, two spaces, a final newline."""
    return json.dumps(schemas, indent=2, ensure_ascii=False) + "\n"


def stored_schemas() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def differences(stored_text: str, schemas: dict[str, Any]) -> list[str]:
    """What differs between a stored file and the schemas, one line each; empty when nothing does."""
    stored = json.loads(stored_text)
    found = [f"{name}: in the stored file, not in the tool table" for name in stored if name not in schemas]
    found += [f"{name}: in the tool table, not in the stored file" for name in schemas if name not in stored]
    for name in schemas:
        if name in stored and stored[name] != schemas[name]:
            found.append(f"{name}: the schema differs")
        elif name in stored and render({name: stored[name]}) != render({name: schemas[name]}):
            found.append(f"{name}: the same schema with its keys in another order")
    if not found and list(stored) != list(schemas):
        found.append("the tools are in another order")
    if not found and stored_text != render(schemas):
        found.append("the file is laid out differently")
    return found


def test_the_input_schemas_match_the_stored_snapshot() -> None:
    found = differences(SNAPSHOT.read_text(encoding="utf-8"), current_schemas())
    assert not found, (
        f"the input schemas differ from tests/snapshots/{SNAPSHOT.name}:\n  "
        + "\n  ".join(found)
        + f"\nIf the change is intended (additive only, R-COMPAT-2), run `{UPDATE}` and commit the file with it."
    )
    assert len(stored_schemas()) == 16


def test_the_comparison_reports_every_kind_of_change() -> None:
    """A snapshot test that cannot fail is decoration: each kind of change is seen."""
    schemas = current_schemas()
    stored_text = render(schemas)
    assert differences(stored_text, schemas) == []

    def after(edit) -> list[str]:
        copy = json.loads(stored_text)
        edit(copy)
        return differences(stored_text, copy)

    # A new optional parameter, a reworded parameter description, a changed bound, a new required name.
    assert after(lambda s: s["grove_scan"]["properties"].update(surprise={"type": "string"})) == [
        "grove_scan: the schema differs"
    ]
    assert after(lambda s: s["grove_project_list"]["properties"]["limit"].update(description="Reworded.")) == [
        "grove_project_list: the schema differs"
    ]
    assert after(lambda s: s["grove_project_list"]["properties"]["limit"].update(maximum=500)) == [
        "grove_project_list: the schema differs"
    ]
    assert after(lambda s: s["grove_work_list"]["required"].append("status")) == ["grove_work_list: the schema differs"]
    assert after(lambda s: s["grove_status"].update(additionalProperties=True)) == ["grove_status: the schema differs"]
    # A tool added to the table, and one removed from it.
    assert after(lambda s: s.update(grove_new={"type": "object"})) == ["grove_new: in the tool table, not in the stored file"]
    assert after(lambda s: s.pop("grove_gaps")) == ["grove_gaps: in the stored file, not in the tool table"]
    # The same content in another order: the bytes a client receives change, so this is seen too.
    create = schemas["grove_project_create"]
    reordered = {**schemas, "grove_project_create": {**create, "properties": dict(reversed(create["properties"].items()))}}
    assert differences(stored_text, reordered) == ["grove_project_create: the same schema with its keys in another order"]
    assert differences(stored_text, dict(reversed(schemas.items()))) == ["the tools are in another order"]
    assert differences(json.dumps(schemas), schemas) == ["the file is laid out differently"]


def main(argv: list[str]) -> int:
    if argv not in ([], ["--write"]):
        print(f"usage: {UPDATE}", file=sys.stderr)
        return 2
    schemas = current_schemas()
    found = differences(SNAPSHOT.read_text(encoding="utf-8"), schemas) if SNAPSHOT.exists() else ["there is no stored file"]
    for line in found:
        print(line)
    if not found:
        print("the stored input schemas match the tool table")
        return 0
    if argv != ["--write"]:
        print(f"nothing written; to update the file: {UPDATE}")
        return 1
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(render(schemas), encoding="utf-8", newline="\n")
    print(f"wrote tests/snapshots/{SNAPSHOT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
