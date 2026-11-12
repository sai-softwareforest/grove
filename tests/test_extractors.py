"""The per-language regexes and the markdown reader, on small inline samples."""

from __future__ import annotations

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


def test_tokens_are_crude_but_stable() -> None:
    assert tokens("Adds two integers") == {"add", "two", "integer"}
    assert tokens("test_add_two_integers") == {"add", "two", "integer"}
    assert tokens("src/tiny/greet.py") == {"tiny", "greet"}
    assert tokens("parseHTTPResponse") == {"parse", "http", "response"}
    assert tokens("the and of to") == frozenset()
