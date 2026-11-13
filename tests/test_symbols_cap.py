"""The cap of 500 symbols or test names per file is reported, never silent (R-INV-11, WO-17).

Every test here writes a real file over the real cap; none lowers the cap.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sf_grove import scan as scan_module
from sf_grove.cli import main
from sf_grove.scan import MAX_SYMBOLS_PER_FILE, extract_symbols, extract_test_names, scan_tree
from sf_grove.service import Grove
from sf_grove.tools import call_tool

CAP = MAX_SYMBOLS_PER_FILE
OVER = CAP + 120

NOTHING_CAPPED = {"total": 0, "items": [], "omitted": 0}


def python_functions(count: int) -> str:
    return "".join(f"def function_{index}():\n    return {index}\n\n" for index in range(count))


def python_tests(count: int) -> str:
    return "".join(f"def test_case_{index}():\n    assert True\n\n" for index in range(count))


def project(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "proj"
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def file_item(result, path: str):
    """The module or test-file item of ``path``."""
    return next(item for item in result.items if item.title == path and item.extra["kind"] in ("module", "test_file"))


def capped(result) -> dict:
    return result.summary()["caps"]["symbols_capped"]


def test_the_cap_is_the_documented_number() -> None:
    assert CAP == 500
    assert scan_tree(Path(__file__).parent).summary()["caps"]["max_symbols_per_file"] == 500


def test_a_file_at_the_cap_is_whole_and_is_not_reported(tmp_path: Path) -> None:
    root = project(tmp_path, {"pkg/wide.py": python_functions(CAP), "tests/test_wide.py": python_tests(CAP)})
    result = scan_tree(root)
    assert capped(result) == NOTHING_CAPPED
    assert not [warning for warning in result.warnings if "per-file cap" in warning]
    assert file_item(result, "pkg/wide.py").extra == {"kind": "module", "language": "python", "symbols": CAP, "depth": 1}
    assert file_item(result, "tests/test_wide.py").extra == {"kind": "test_file", "language": "python", "tests": CAP}


def test_a_source_file_over_the_cap_is_named_with_the_true_count(tmp_path: Path) -> None:
    root = project(tmp_path, {"pkg/wide.py": python_functions(OVER), "pkg/small.py": python_functions(3)})
    result = scan_tree(root)
    assert capped(result) == {
        "total": 1,
        "items": [{"path": "pkg/wide.py", "kind": "symbols", "found": OVER, "kept": CAP, "dropped": 120}],
        "omitted": 0,
    }
    module = file_item(result, "pkg/wide.py")
    assert module.extra == {"kind": "module", "language": "python", "symbols": CAP, "symbols_found": OVER, "depth": 1}
    assert module.body.endswith(f"(+{CAP - 40} more)")  # the body counts the names kept, as before
    # The first 500, in file order, are the ones kept.
    kept = [item.title for item in result.items if item.source_path == "pkg/wide.py" and item.extra["kind"] == "function"]
    assert kept == [f"function_{index}" for index in range(CAP)]
    assert "symbols_found" not in file_item(result, "pkg/small.py").extra
    assert result.warnings == [
        f"1 file(s) hold more than {CAP} symbols or test names (per-file cap); "
        "120 were counted and not kept: pkg/wide.py"
    ]
    assert result.caps_hit == []  # the walk itself was not cut short


@pytest.mark.parametrize(
    "path,language,text",
    [
        ("tests/test_wide.py", "python", python_tests(OVER)),
        ("pkg/wide_test.go", "go", "".join(f"func TestCase{index}(t *testing.T) {{}}\n" for index in range(OVER))),
        ("web/wide.test.ts", "typescript", "".join(f"it('handles case {index}', () => {{}})\n" for index in range(OVER))),
    ],
)
def test_a_test_file_over_the_cap_is_named_with_the_true_count(tmp_path: Path, path: str, language: str, text: str) -> None:
    result = scan_tree(project(tmp_path, {path: text}))
    assert capped(result)["items"] == [{"path": path, "kind": "tests", "found": OVER, "kept": CAP, "dropped": 120}]
    assert file_item(result, path).extra == {"kind": "test_file", "language": language, "tests": CAP, "tests_found": OVER}
    assert sum(item.extra["kind"] == "test" for item in result.items) == CAP
    assert any(path in warning and "120 were counted and not kept" in warning for warning in result.warnings)


def test_several_test_names_on_one_line_do_not_pass_the_cap(tmp_path: Path) -> None:
    # The cap used to be checked once a line, so the last line could carry the count past it.
    lines = "".join(f"it('case {index}', () => {{}})\n" for index in range(CAP - 1))
    lines += "it('one', () => {}); it('two', () => {}); it('three', () => {})\n"
    result = scan_tree(project(tmp_path, {"web/wide.spec.js": lines}))
    assert capped(result)["items"] == [
        {"path": "web/wide.spec.js", "kind": "tests", "found": CAP + 2, "kept": CAP, "dropped": 2}
    ]
    names = [item.title for item in result.items if item.extra["kind"] == "test"]
    assert len(names) == CAP and names[-1] == "one"
    assert len(extract_test_names("javascript", lines)) == CAP


def test_inline_rust_tests_count_as_symbols_of_their_file(tmp_path: Path) -> None:
    # 400 functions, then 200 tests: the cap of 500 definitions keeps 400 and 100.
    source = "".join(f"pub fn function_{index}() {{}}\n" for index in range(400))
    source += "".join(f"#[test]\nfn checks_{index}() {{}}\n" for index in range(200))
    result = scan_tree(project(tmp_path, {"src/wide.rs": source}))
    assert capped(result)["items"] == [{"path": "src/wide.rs", "kind": "symbols", "found": 600, "kept": CAP, "dropped": 100}]
    # No symbol was lost, and the item says so: found equals kept.
    assert file_item(result, "src/wide.rs").extra == {
        "kind": "module", "language": "rust", "symbols": 400, "symbols_found": 400, "depth": 1
    }
    assert sum(item.layer == "tests" for item in result.items) == 100


def test_a_rust_test_file_reports_the_tests_it_lost(tmp_path: Path) -> None:
    # Helpers and tests alternate. The cap counts every definition of a Rust
    # file, so 250 of the 300 tests are kept: fewer than the cap.
    source = "".join(f"fn helper_{index}() {{}}\n#[test]\nfn checks_{index}() {{}}\n" for index in range(300))
    result = scan_tree(project(tmp_path, {"tests/wide_test.rs": source}))
    assert capped(result)["items"] == [{"path": "tests/wide_test.rs", "kind": "tests", "found": 300, "kept": 250, "dropped": 50}]
    assert file_item(result, "tests/wide_test.rs").extra == {
        "kind": "test_file", "language": "rust", "tests": 250, "tests_found": 300
    }
    # Helpers past the cap are not tests, and a test file records none of them: nothing to report.
    helpers_last = "".join(f"#[test]\nfn checks_{index}() {{}}\n" for index in range(300))
    helpers_last += "".join(f"fn helper_{index}() {{}}\n" for index in range(300))
    again = scan_tree(project(tmp_path / "second", {"tests/wide_test.rs": helpers_last}))
    assert capped(again) == NOTHING_CAPPED
    assert file_item(again, "tests/wide_test.rs").extra == {"kind": "test_file", "language": "rust", "tests": 300}


def test_a_long_list_of_capped_files_is_bounded_with_the_true_count(tmp_path: Path) -> None:
    text = python_functions(CAP + 1)
    result = scan_tree(project(tmp_path, {f"pkg/wide{index:02}.py": text for index in range(60)}))
    listing = capped(result)
    assert listing["total"] == 60 and len(listing["items"]) == 50 and listing["omitted"] == 10
    assert listing["items"][0] == {"path": "pkg/wide00.py", "kind": "symbols", "found": CAP + 1, "kept": CAP, "dropped": 1}
    warning = next(warning for warning in result.warnings if "per-file cap" in warning)
    assert warning.startswith(f"60 file(s) hold more than {CAP} symbols or test names")
    assert "60 were counted and not kept" in warning and "(+50 more; see caps.symbols_capped)" in warning
    # A file left out of the list still carries its own count.
    assert file_item(result, "pkg/wide59.py").extra["symbols_found"] == CAP + 1


def test_the_extractors_still_return_at_most_the_cap() -> None:
    assert len(extract_symbols("python", python_functions(OVER))) == CAP
    assert len(extract_test_names("python", python_tests(OVER))) == CAP
    assert len(extract_test_names("rust", "".join(f"#[test]\nfn checks_{index}() {{}}\n" for index in range(OVER)))) == CAP


def test_counting_past_the_cap_stops_at_the_time_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A clock that moves one millisecond every time it is read: 2.25 seconds
    # run out after about 2250 of the 3000 lines, which is past the cap of 500
    # symbols (line 1500) and before the end of the file. The count is then
    # what was found so far, and the scan says that it was cut short.
    root = project(tmp_path, {"pkg/wide.py": python_functions(1000)})
    ticks = itertools.count()
    monkeypatch.setattr(scan_module, "time", SimpleNamespace(monotonic=lambda: next(ticks) / 1000))
    result = scan_tree(root, max_seconds=2.25)
    assert result.caps_hit == ["max_seconds"]
    (entry,) = capped(result)["items"]
    assert entry["kept"] == CAP and 700 < entry["found"] < 800, entry
    assert entry["dropped"] == entry["found"] - CAP
    assert file_item(result, "pkg/wide.py").extra["symbols_found"] == entry["found"]


def test_the_report_is_the_same_on_every_scan(tmp_path: Path) -> None:
    root = project(tmp_path, {"pkg/wide.py": python_functions(OVER), "tests/test_wide.py": python_tests(OVER)})
    first, second = scan_tree(root), scan_tree(root)
    assert capped(first) == capped(second) and capped(first)["total"] == 2
    assert first.warnings == second.warnings
    assert [(item.title, item.extra) for item in first.items] == [(item.title, item.extra) for item in second.items]


# -- both surfaces -------------------------------------------------------------

EXPECTED = {
    "total": 2,
    "items": [
        {"path": "pkg/wide.py", "kind": "symbols", "found": OVER, "kept": CAP, "dropped": 120},
        {"path": "tests/test_wide.py", "kind": "tests", "found": OVER + 7, "kept": CAP, "dropped": 127},
    ],
    "omitted": 0,
}
EXPECTED_WARNING = (
    f"2 file(s) hold more than {CAP} symbols or test names (per-file cap); "
    "247 were counted and not kept: pkg/wide.py, tests/test_wide.py"
)


@pytest.fixture
def wide(tmp_path: Path) -> Path:
    return project(tmp_path, {"pkg/wide.py": python_functions(OVER), "tests/test_wide.py": python_tests(OVER + 7)})


def check_the_surface(scanned: dict, fetched: dict, module: dict, test_file: dict, stored_symbols: int, stored_tests: int) -> None:
    assert scanned["caps"]["max_symbols_per_file"] == CAP
    assert scanned["caps"]["symbols_capped"] == EXPECTED
    assert scanned["warnings"] == [EXPECTED_WARNING]
    assert scanned["caps"]["hit"] == []
    # One module item and one test-file item besides the names kept.
    assert scanned["items"]["actual"] == CAP + 1 and scanned["items"]["tests"] == CAP + 1
    # The project keeps the report until the next scan.
    assert fetched["last_scan"]["caps"]["symbols_capped"] == EXPECTED
    assert fetched["cap_warnings"] == [EXPECTED_WARNING]
    assert fetched["caps_hit"] == []
    # The blueprint items of the two files carry the true count next to the kept one.
    assert module["title"] == "pkg/wide.py"
    assert module["extra"] == {"kind": "module", "language": "python", "symbols": CAP, "symbols_found": OVER, "depth": 1}
    assert test_file["title"] == "tests/test_wide.py"
    assert test_file["extra"] == {"kind": "test_file", "language": "python", "tests": CAP, "tests_found": OVER + 7}
    assert stored_symbols == CAP + 1 and stored_tests == CAP + 1


def test_the_cap_is_reported_by_the_cli(wide: Path, home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def cli(*args: str) -> dict:
        assert main(["--home", str(home), *args]) == 0
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["ok"] is True
        return envelope["data"]

    cli("project", "create", "proj", "--root", str(wide))
    scanned = cli("scan", "proj")
    actual = cli("blueprint", "proj", "--layer", "actual", "--limit", "1")
    tests = cli("blueprint", "proj", "--layer", "tests", "--limit", "1")
    check_the_surface(scanned, cli("project", "get", "proj"), actual["items"][0], tests["items"][0], actual["total"], tests["total"])


def test_the_cap_is_reported_by_the_mcp_tools(wide: Path, home: Path) -> None:
    def tool(tool_name: str, **arguments) -> dict:
        envelope = call_tool(home, tool_name, arguments)
        assert envelope["ok"] is True, envelope
        return envelope["data"]

    tool("grove_project_create", name="proj", root_path=str(wide))
    scanned = tool("grove_scan", project="proj")
    actual = tool("grove_blueprint_get", project="proj", layer="actual", limit=1)
    tests = tool("grove_blueprint_get", project="proj", layer="tests", limit=1)
    check_the_surface(
        scanned, tool("grove_project_get", project="proj"), actual["items"][0], tests["items"][0], actual["total"], tests["total"]
    )


def test_a_rescan_without_the_wide_files_clears_the_report(grove: Grove, wide: Path) -> None:
    grove.project_create("proj", str(wide))
    assert grove.scan("proj")["caps"]["symbols_capped"]["total"] == 2
    scanned = grove.scan("proj", exclude=["wide.py", "test_wide.py"])
    assert scanned["caps"]["symbols_capped"] == NOTHING_CAPPED
    assert scanned["warnings"] == []
    assert grove.project_get("proj")["last_scan"]["caps"]["symbols_capped"] == NOTHING_CAPPED
