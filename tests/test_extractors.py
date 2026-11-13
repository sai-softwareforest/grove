"""The per-language regexes and the markdown reader, on small inline samples."""

from __future__ import annotations

import pytest

from conftest import REPO
from sf_grove.mapdoc import parse_map
from sf_grove.scan import extract_declared, extract_symbols, extract_test_names, is_doc_file, is_test_file
from sf_grove.tokens import tokens


def names(symbols) -> list[str]:
    return [symbol.name for symbol in symbols]


def test_test_file_patterns() -> None:
    yes = [
        "test_x.py", "pkg/x_test.py", "x_tests.py", "src/x_test.rs", "x_tests.rs",
        "a.test.ts", "a.test.js", "a.spec.ts", "x_test.go", "test_x.go",
    ]
    no = ["x.py", "testing.py", "contest.rs", "latest.go", "a.ts", "tests/helpers.py"]
    assert all(is_test_file(path) for path in yes)
    assert not any(is_test_file(path) for path in no)


def test_doc_file_patterns() -> None:
    assert all(is_doc_file(path) for path in ["README.md", "README", "CHANGELOG.md", "docs/a/b.md", "pkg/README.rst"])
    assert not any(is_doc_file(path) for path in ["LICENSE", "src/readme_parser.py", "notes.md", "docs/conf.py"])


def test_python_symbols_and_tests() -> None:
    source = "class Store:\n    def get(self):\n        pass\n\nasync def fetch_all():\n    pass\n# def commented():\n"
    symbols = extract_symbols("python", source)
    assert [(s.name, s.kind, s.line, s.nested) for s in symbols] == [
        ("Store", "class", 1, False),
        ("get", "function", 2, True),
        ("fetch_all", "function", 5, False),
    ]
    tests = extract_test_names("python", "class TestStore:\n    def test_get(self): ...\ndef helper(): ...\nasync def test_async(): ...\n")
    assert names(tests) == ["TestStore", "test_get", "test_async"]


def test_rust_symbols_and_inline_tests() -> None:
    source = (
        "pub struct Engine;\n"
        "pub(crate) async fn run_engine() {}\n"
        "enum Mode { A }\n"
        "#[cfg(test)]\n"
        "mod tests {\n"
        "    #[test]\n"
        "    fn starts_cleanly() {}\n"
        "    #[tokio::test]\n"
        "    #[ignore]\n"
        "    async fn stops_cleanly() {}\n"
        "    fn test_helper_named_like_a_test() {}\n"
        "    fn plain_helper() {}\n"
        "}\n"
    )
    symbols = extract_symbols("rust", source)
    assert names([s for s in symbols if not s.is_test]) == ["Engine", "run_engine", "Mode", "tests", "plain_helper"]
    assert names([s for s in symbols if s.is_test]) == ["starts_cleanly", "stops_cleanly", "test_helper_named_like_a_test"]
    assert names(extract_test_names("rust", source)) == ["starts_cleanly", "stops_cleanly", "test_helper_named_like_a_test"]


def test_typescript_and_javascript() -> None:
    source = (
        "export async function loadUser(id: string) {}\n"
        "export default class UserStore {}\n"
        "export interface User { id: string }\n"
        "type Id = string\n"
        "export const toId = (user: User): Id => user.id\n"
        "const count = 3\n"
    )
    assert names(extract_symbols("typescript", source)) == ["loadUser", "UserStore", "User", "Id", "toId"]
    tests = extract_test_names(
        "javascript",
        "describe('store', () => {\n  it('loads a user', () => {})\n  test.skip(\"saves a user\", () => {})\n  submit('x')\n})\n",
    )
    assert names(tests) == ["loads a user", "saves a user"]


def test_go() -> None:
    source = "type Client struct {}\nfunc (c *Client) Do() error { return nil }\nfunc NewClient() *Client { return nil }\n"
    assert names(extract_symbols("go", source)) == ["Client", "Do", "NewClient"]
    tests = extract_test_names("go", "func TestDo(t *testing.T) {}\nfunc helper() {}\nfunc BenchmarkDo(b *testing.B) {}\n")
    assert names(tests) == ["TestDo"]


def test_declared_reader_keeps_claims_and_drops_boilerplate() -> None:
    text = (
        "---\ntitle: front matter\n---\n"
        "# Widget\n"
        "\n"
        "[![build](https://example.invalid/badge.svg)](https://example.invalid)\n"
        "\n"
        "Widget parses config files. It also\nwatches them for changes.\n"
        "\n"
        "```\nthis fenced line is not a claim at all\n```\n"
        "\n"
        "Setext heading\n==============\n"
        "\n"
        "- Supports **TOML** and [YAML](https://example.invalid/yaml) input.\n"
        "\n"
        "## License\n"
        "\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy.\n"
    )
    items = extract_declared("README.md", text)
    got = [(item.extra["kind"], item.title, item.source_line) for item in items]
    assert got == [
        ("heading", "Widget", 4),
        ("sentence", "Widget parses config files.", 8),
        ("sentence", "It also watches them for changes.", 8),
        ("heading", "Setext heading", 15),
        ("sentence", "Supports TOML and YAML input.", 18),
        ("heading", "License", 20),
    ]
    assert items[4].extra["heading"] == "Setext heading"


# WO-24: the README lists which Markdown constructs are read and which are
# not ("Which Markdown is read"). One sample for each line of that list:
# (the text, the titles of the declared items it gives). A heading is marked "#".
MARKDOWN_READ = {
    "front matter": ("---\ntitle: The hidden title here\n---\nThe widget frobs on demand.\n", ["The widget frobs on demand."]),
    "ATX heading": ("  ## The widget frobs ##\n", ["# The widget frobs"]),
    "setext heading": ("The widget frobs\n----------------\n", ["# The widget frobs"]),
    "paragraph": ("The widget frobs. It also\nspins on demand.\n", ["The widget frobs.", "It also spins on demand."]),
    "list items": (
        "- The widget frobs on demand.\n  It also spins around.\n  * [x] The gadget spins on demand.\n1. The gizmo hums on demand.\n",
        ["The widget frobs on demand.", "It also spins around.", "The gadget spins on demand.", "The gizmo hums on demand."],
    ),
    "block quote": ("> The widget frobs on demand.\n> > The gadget spins on demand.\n", ["The widget frobs on demand.", "The gadget spins on demand."]),
    "table": ("| Part | What it does |\n|---|---|\n| widget | frobs on demand |\n", ["Part; What it does", "widget; frobs on demand"]),
    "fenced code": ("```python\nThe fenced widget never frobs.\n```\n~~~\nNor does this one.\n~~~\nThe widget frobs on demand.\n", ["The widget frobs on demand."]),
    "thematic break": ("The widget frobs on demand.\n\n***\n\nThe gadget spins on demand.\n", ["The widget frobs on demand.", "The gadget spins on demand."]),
    "link reference definition": (
        "The widget [frobs][f] on demand.[^1]\n\n[f]: https://example.invalid/frob\n[^1]: The footnote text is here.\n",
        ["The widget frobs on demand.[^1]"],
    ),
    "inline": (
        "The **widget** [frobs](https://example.invalid/Frob_(verb)) `on` _demand_ ![x](y.png) <b>now</b>.\n",
        ["The widget frobs on demand now ."],
    ),
}
MARKDOWN_NOT_READ = {
    "indented code": ("    The indented widget code frobs.\n", ["The indented widget code frobs."]),
    "fence length": ("````\n```\nThe inner widget frobs daily.\n```\n````\n", ["The inner widget frobs daily."]),
    "HTML block": ('<div align="center">\nThe centred widget frobs.\n</div>\n', ["The centred widget frobs."]),
    "comment over several lines": ("<!--\nThe hidden widget frobs daily.\n-->\n", ["The hidden widget frobs daily."]),
    "autolink": ("See <https://example.invalid/page> for the widget.\n", ["See for the widget."]),
    "wrapped link": (
        "The widget [frobs on\ndemand](https://example.invalid/frob) every day.\n",
        ["The widget [frobs on demand](https://example.invalid/frob) every day."],
    ),
    "link text with a bracket": ("The widget [frobs [x](https://example.invalid/a(b(c))) daily.\n", ["The widget [frobs [x](https://example.invalid/a(b(c))) daily."]),
    "opener that never closes": ("The widget [frobs on demand (and spins <daily.\n", ["The widget [frobs on demand (and spins <daily."]),
    "shortcut reference": ("The widget [frobs] on demand.\n", ["The widget [frobs] on demand."]),
    "escapes and entities": ("The widget \\*frobs\\* on demand &amp; more.\n", ["The widget \\frobs\\ on demand &amp; more."]),
    "heading in a list item or a quote": ("- # The listed heading here\n> # The quoted heading here\n", ["# The listed heading here # The quoted heading here"]),
    "table without leading pipes": ("Part | What it does here\n---|---\nwidget | frobs on demand\n", ["Part | What it does here", "widget | frobs on demand"]),
    "reStructuredText": ("The widget\n==========\n\n.. note:: The widget frobs daily.\n", ["# The widget", ".. note:: The widget frobs daily."]),
}


@pytest.mark.parametrize("name", sorted(MARKDOWN_READ) + sorted(MARKDOWN_NOT_READ))
def test_markdown_constructs_are_read_as_the_readme_says(name: str) -> None:
    text, titles = {**MARKDOWN_READ, **MARKDOWN_NOT_READ}[name]
    items = extract_declared("README.md", text)
    assert [("# " if item.extra["kind"] == "heading" else "") + item.title for item in items] == titles


def test_a_map_reads_markdown_with_the_four_differences_the_readme_names() -> None:
    blocks = parse_map(
        "---\nThe front part is documented.\n---\n\n"
        "The setext part is documented\n-----------------------------\n\n"
        "- [x] The boxed part is documented.\n\n"
        "[part]: https://example.invalid/part (documented)\n\n"
        "The wrapped part is [documented\nhere](https://example.invalid/wrapped) in full.\n"
    )
    assert [(block.line, block.text, block.heading) for block in blocks] == [
        (2, "The front part is documented.", ""),
        (5, "The setext part is documented", ""),
        (8, "[x] The boxed part is documented.", ""),
        (10, "[part]: https://example.invalid/part (documented)", ""),
        (12, "The wrapped part is documented here in full.", ""),
    ]


def test_the_readme_names_the_markdown_it_reads() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    section = readme[readme.index("**Which Markdown is read.**") : readme.index("**The gap heuristic")]
    assert "CommonMark" in section and "GitHub Flavored Markdown" in section
    assert "\nRead:\n" in section and "\nNot read as Markdown" in section and "A map (`ingest-map`)" in section


def test_tokens_are_crude_but_stable() -> None:
    assert tokens("Adds two integers") == {"add", "two", "integer"}
    assert tokens("test_add_two_integers") == {"add", "two", "integer"}
    assert tokens("src/tiny/greet.py") == {"tiny", "greet"}
    assert tokens("parseHTTPResponse") == {"parse", "http", "response"}
    assert tokens("the and of to") == frozenset()
