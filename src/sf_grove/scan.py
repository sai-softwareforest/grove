"""Deterministic, read-only scan of a project tree.

The scan only ever opens files for reading. It produces blueprint items in
three layers:

* ``declared`` - headings and sentences from README/CHANGELOG/docs files;
* ``actual``   - a module inventory plus symbol names found by per-language
  regular expressions (Python, Rust, TypeScript/JavaScript, Go);
* ``tests``    - test files and the test names found in them.

None of this is a parser. The regexes look at one line at a time, so text
inside strings or block comments can be mistaken for a definition, and
definitions split over several lines can be missed. See BUILD_NOTES.md.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Iterator

from pathspec import GitIgnoreSpec

from .claims import classify

DEFAULT_MAX_FILES = 4000
DEFAULT_MAX_SECONDS = 8.0

ALWAYS_SKIP = frozenset(
    {
        ".git",
        "node_modules",
        "target",
        "venv",
        ".venv",
        "dist",
        "build",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
    }
)

MAX_FILE_BYTES = 512 * 1024  # larger files are counted but not read
MAX_DECLARED_PER_FILE = 400
MAX_SYMBOLS_PER_FILE = 500
TITLE_CHARS = 160
BODY_CHARS = 2000

LANGUAGES = {
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
}

TEST_FILE_PATTERNS = (
    "test_*.py",
    "*_test.py",
    "*_tests.py",
    "*_test.rs",
    "*_tests.rs",
    "*.test.ts",
    "*.test.tsx",
    "*.test.js",
    "*.test.jsx",
    "*.test.mjs",
    "*.test.cjs",
    "*.spec.ts",
    "*.spec.tsx",
    "*.spec.js",
    "*.spec.jsx",
    "*_test.go",
    "test_*.go",
)

DOC_PREFIXES = ("readme", "changelog", "changes", "history", "contributing", "architecture", "design")
DOC_EXTENSIONS = ("", ".md", ".markdown", ".mdx", ".rst", ".txt")
DOC_DIR_EXTENSIONS = (".md", ".markdown", ".mdx", ".rst")
DOC_DIRS = ("docs", "doc")


@dataclass
class Item:
    layer: str
    title: str
    body: str
    source_path: str
    source_line: int
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResult:
    items: list[Item]
    files_seen: int
    files_read: int
    elapsed_seconds: float
    max_files: int
    max_seconds: float
    caps_hit: list[str]
    warnings: list[str]

    def summary(self) -> dict[str, Any]:
        return {
            "files_seen": self.files_seen,
            "files_read": self.files_read,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "caps": {
                "max_files": self.max_files,
                "max_seconds": self.max_seconds,
                "hit": list(self.caps_hit),
            },
            "warnings": list(self.warnings),
        }


# --------------------------------------------------------------------------
# Walking


def _load_gitignore(directory: str) -> GitIgnoreSpec | None:
    try:
        with open(os.path.join(directory, ".gitignore"), "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    try:
        return GitIgnoreSpec.from_lines(lines)
    except Exception:  # a malformed pattern must not abort the scan
        return None


def _ignored(rel_path: str, is_dir: bool, specs: dict[str, GitIgnoreSpec]) -> bool:
    """Check ``rel_path`` against every .gitignore found in one of its ancestors.

    Each file's patterns are matched relative to its own directory. A negation
    in a deeper .gitignore does not re-include something a shallower one
    ignored; that part of git's behaviour is not reproduced.
    """
    for base, spec in specs.items():
        if base == "":
            candidate = rel_path
        elif rel_path.startswith(base + "/"):
            candidate = rel_path[len(base) + 1 :]
        else:
            continue
        if spec.match_file(candidate + "/" if is_dir else candidate):
            return True
    return False


def walk_files(root: str) -> Iterator[str]:
    """Yield project-relative POSIX paths of candidate files, in a stable order."""
    specs: dict[str, GitIgnoreSpec] = {}
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""
        if ".gitignore" in filenames:
            spec = _load_gitignore(dirpath)
            if spec is not None:
                specs[rel_dir] = spec
        prefix = rel_dir + "/" if rel_dir else ""
        kept: list[str] = []
        for name in sorted(dirnames):
            if name in ALWAYS_SKIP:
                continue
            if os.path.islink(os.path.join(dirpath, name)):
                continue
            if _ignored(prefix + name, True, specs):
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            if name in ALWAYS_SKIP:
                continue
            rel = prefix + name
            if _ignored(rel, False, specs):
                continue
            if os.path.islink(os.path.join(dirpath, name)):
                continue
            yield rel


# --------------------------------------------------------------------------
# Classification


def is_test_file(rel_path: str) -> bool:
    name = rel_path.rsplit("/", 1)[-1]
    return any(fnmatchcase(name, pattern) for pattern in TEST_FILE_PATTERNS)


def is_doc_file(rel_path: str) -> bool:
    parts = rel_path.split("/")
    name = parts[-1].lower()
    stem, ext = os.path.splitext(name)
    if ext in DOC_EXTENSIONS and stem.startswith(DOC_PREFIXES):
        return True
    return ext in DOC_DIR_EXTENSIONS and any(part.lower() in DOC_DIRS for part in parts[:-1])


def language_of(rel_path: str) -> str | None:
    return LANGUAGES.get(os.path.splitext(rel_path)[1].lower())


# --------------------------------------------------------------------------
# Declared layer: markdown-ish prose

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^\s{0,3}(=+|-+)\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_RULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)|!\[[^\]]*\]\[[^\]]*\]")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REF_LINK = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_LINK_DEF = re.compile(r"^\s*\[[^\]]+\]:\s+\S+")
_HTML = re.compile(r"<[^>]+>")
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[A-Z0-9`\"'(\[])")
_ALPHA_WORD = re.compile(r"[A-Za-z]{2,}")
_LICENCE_HEADING = re.compile(r"^(licen[cs]e|licensing|copyright|legal)\b", re.IGNORECASE)
_LICENCE_TEXT = re.compile(
    r"permission is hereby granted|the software is provided|without warranty of any kind|"
    r"all rights reserved|licen[cs]ed under|copyright \(c\)|copyright ©|redistribution and use",
    re.IGNORECASE,
)


def clean_inline(text: str) -> str:
    """Strip markdown decoration, leaving the words."""
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _REF_LINK.sub(r"\1", text)
    text = _HTML.sub(" ", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def extract_declared(rel_path: str, text: str) -> list[Item]:
    items: list[Item] = []
    heading = ""
    in_licence = False
    in_fence = False
    block: list[tuple[int, str]] = []  # (line number, cleaned text)
    lines = text.splitlines()

    def add_heading(title: str, level: int, line_no: int) -> None:
        nonlocal heading, in_licence
        title = clean_inline(title)
        if not title:
            return
        heading = title
        in_licence = bool(_LICENCE_HEADING.match(title))
        items.append(Item("declared", _clip(title, TITLE_CHARS), "", rel_path, line_no, {"kind": "heading", "level": level}))

    def flush() -> None:
        if not block:
            return
        pieces = list(block)
        block.clear()
        if in_licence:
            return
        joined = ""
        starts: list[tuple[int, int]] = []  # (offset in joined, line number)
        for line_no, piece in pieces:
            if joined:
                joined += " "
            starts.append((len(joined), line_no))
            joined += piece
        position = 0
        for sentence in _SENTENCE_END.split(joined):
            offset = joined.find(sentence, position)
            if offset < 0:
                offset = position
            position = offset + len(sentence)
            sentence = sentence.strip()
            if len(_ALPHA_WORD.findall(sentence)) < 3 or _LICENCE_TEXT.search(sentence):
                continue
            line_no = pieces[0][0]
            for start, candidate in starts:
                if start <= offset:
                    line_no = candidate
            claim_class, reason = classify(sentence, heading)
            items.append(
                Item(
                    "declared",
                    _clip(sentence, TITLE_CHARS),
                    _clip(sentence, BODY_CHARS) if len(sentence) > TITLE_CHARS else "",
                    rel_path,
                    line_no,
                    {"kind": "sentence", "heading": heading, "class": claim_class, "class_reason": reason},
                )
            )

    start_index = 0
    if lines and lines[0].strip() == "---":  # YAML front matter
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                start_index = index + 1
                break

    for index in range(start_index, len(lines)):
        raw = lines[index]
        line_no = index + 1
        if _FENCE.match(raw):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not raw.strip():
            flush()
            continue
        match = _HEADING.match(raw)
        if match:
            flush()
            add_heading(match.group(2), len(match.group(1)), line_no)
            continue
        if _SETEXT.match(raw) and len(raw.strip()) >= 3 and len(block) == 1:
            underlined_line, underlined = block[0]
            block.clear()
            add_heading(underlined, 1 if raw.strip().startswith("=") else 2, underlined_line)
            continue
        if _RULE.match(raw) or _TABLE_SEP.match(raw) or _LINK_DEF.match(raw):
            flush()
            continue
        stripped = raw.strip()
        if stripped.startswith("|"):
            flush()
            cells = [clean_inline(cell) for cell in stripped.strip("|").split("|")]
            row = "; ".join(cell for cell in cells if cell)
            if row:
                block.append((line_no, row))
                flush()
            continue
        if _BULLET.match(raw):
            flush()
            raw = _BULLET.sub("", raw, count=1)
        cleaned = clean_inline(raw.lstrip("> ").rstrip())
        if cleaned and _ALPHA_WORD.search(cleaned):
            block.append((line_no, cleaned))
    flush()
    return items


# --------------------------------------------------------------------------
# Actual and tests layers: per-language regexes, one line at a time

_PY_DEF = re.compile(r"^(?P<indent>[ \t]*)(?:async[ \t]+)?def[ \t]+(?P<name>[A-Za-z_]\w*)")
_PY_CLASS = re.compile(r"^(?P<indent>[ \t]*)class[ \t]+(?P<name>[A-Za-z_]\w*)")

_RS_VIS = r"(?:pub(?:\([^)]*\))?\s+)?"
_RS_FN = re.compile(
    r"^(?P<indent>\s*)" + _RS_VIS + r"(?:(?:default|const|async|unsafe|extern(?:\s+\"[^\"]*\")?)\s+)*"
    r"fn\s+(?P<name>[A-Za-z_]\w*)"
)
_RS_TYPE = re.compile(
    r"^(?P<indent>\s*)" + _RS_VIS + r"(?P<kind>struct|enum|trait|union|mod|type)\s+(?P<name>[A-Za-z_]\w*)"
)
_RS_MACRO = re.compile(r"^(?P<indent>\s*)macro_rules!\s+(?P<name>[A-Za-z_]\w*)")
_RS_TEST_ATTR = re.compile(r"^\s*#\[\s*(?:[\w:]+::)?(?:test|rstest|test_case)\b")
_RS_ATTR = re.compile(r"^\s*#\[")

_JS_NAME = r"(?P<name>[A-Za-z_$][\w$]*)"
_JS_FN = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:async\s+)?function\s*\*?\s*" + _JS_NAME
)
_JS_CLASS = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?class\s+" + _JS_NAME
)
_JS_TYPE = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?:declare\s+)?(?:const\s+)?"
    r"(?P<kind>interface|enum|namespace|type)\s+" + _JS_NAME + r"\s*(?:[=<{]|extends\b|$)"
)
_JS_CONST_FN = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?:const|let|var)\s+" + _JS_NAME + r"\s*(?::[^=]+)?=\s*"
    r"(?:async\s+)?(?:function\b|\([^)]*\)\s*(?::[^=]+?)?=>|[A-Za-z_$][\w$]*\s*=>)"
)
_JS_TEST = re.compile(
    r"(?:^|[^\w.$])(?:test|it)(?:\.[A-Za-z]+)*\s*(?:\([^)]*\)\s*)?\(\s*"
    r"(?P<quote>['\"`])(?P<name>(?:\\.|(?!(?P=quote)).)+)(?P=quote)"
)

_GO_FUNC = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_]\w*)")
_GO_TYPE = re.compile(r"^type\s+(?P<name>[A-Za-z_]\w*)\b")
_GO_TEST = re.compile(r"^func\s+(?P<name>Test\w*)\s*\(")

_PY_TEST_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+(?P<name>test\w*)")
_PY_TEST_CLASS = re.compile(r"^[ \t]*class[ \t]+(?P<name>Test\w*)")


@dataclass
class Symbol:
    name: str
    kind: str
    line: int
    text: str
    nested: bool = False
    is_test: bool = False


def extract_symbols(language: str, text: str) -> list[Symbol]:
    """Definitions in a source file. Rust ``#[test]`` functions are flagged as tests."""
    symbols: list[Symbol] = []
    pending_rust_test = False
    for index, line in enumerate(text.splitlines()):
        if len(symbols) >= MAX_SYMBOLS_PER_FILE:
            break
        line_no = index + 1
        found: tuple[re.Match[str], str] | None = None
        is_test = False
        if language == "python":
            for pattern, kind in ((_PY_DEF, "function"), (_PY_CLASS, "class")):
                match = pattern.match(line)
                if match:
                    found = (match, kind)
                    break
        elif language == "rust":
            if _RS_TEST_ATTR.match(line):
                pending_rust_test = True
                continue
            match = _RS_FN.match(line)
            if match:
                is_test = pending_rust_test or match.group("name").startswith("test_")
                found = (match, "function")
            else:
                match = _RS_TYPE.match(line)
                if match:
                    found = (match, match.group("kind"))
                else:
                    match = _RS_MACRO.match(line)
                    if match:
                        found = (match, "macro")
            stripped = line.strip()
            if stripped and not _RS_ATTR.match(line) and not stripped.startswith("//"):
                pending_rust_test = False
        elif language in ("typescript", "javascript"):
            for pattern, kind in ((_JS_FN, "function"), (_JS_CLASS, "class"), (_JS_TYPE, ""), (_JS_CONST_FN, "function")):
                match = pattern.match(line)
                if match:
                    found = (match, kind or match.group("kind"))
                    break
        elif language == "go":
            match = _GO_FUNC.match(line)
            if match:
                found = (match, "function")
            else:
                match = _GO_TYPE.match(line)
                if match:
                    found = (match, "type")
        if found is None:
            continue
        match, kind = found
        indent = match.groupdict().get("indent") or ""
        symbols.append(
            Symbol(
                name=match.group("name"),
                kind=kind,
                line=line_no,
                text=_clip(line.strip(), 200),
                nested=bool(indent),
                is_test=is_test,
            )
        )
    return symbols


def extract_test_names(language: str, text: str) -> list[Symbol]:
    """Test names in a file whose name matches a test-file pattern."""
    if language == "rust":
        return [symbol for symbol in extract_symbols("rust", text) if symbol.is_test]
    tests: list[Symbol] = []
    for index, line in enumerate(text.splitlines()):
        if len(tests) >= MAX_SYMBOLS_PER_FILE:
            break
        line_no = index + 1
        if language == "python":
            match = _PY_TEST_DEF.match(line) or _PY_TEST_CLASS.match(line)
            if match:
                tests.append(Symbol(match.group("name"), "test", line_no, _clip(line.strip(), 200), is_test=True))
        elif language == "go":
            match = _GO_TEST.match(line)
            if match:
                tests.append(Symbol(match.group("name"), "test", line_no, _clip(line.strip(), 200), is_test=True))
        elif language in ("typescript", "javascript"):
            for match in _JS_TEST.finditer(line):
                tests.append(Symbol(match.group("name"), "test", line_no, _clip(line.strip(), 200), is_test=True))
    return tests


# --------------------------------------------------------------------------
# The scan itself


def _read_text(path: str) -> str | None:
    """Read a file as text, or None when it is too large, binary or unreadable."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if len(data) > MAX_FILE_BYTES or b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def scan_tree(
    root: str | os.PathLike[str],
    max_files: int = DEFAULT_MAX_FILES,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> ScanResult:
    """Walk ``root`` and return blueprint items. Never writes inside ``root``."""
    root = str(Path(root))
    started = time.monotonic()
    deadline = started + max_seconds
    items: list[Item] = []
    caps_hit: list[str] = []
    warnings: list[str] = []
    files_seen = 0
    files_read = 0
    skipped = 0

    for rel in walk_files(root):
        if files_seen >= max_files:
            caps_hit.append("max_files")
            warnings.append(f"stopped after {max_files} files (max_files cap); the blueprint is partial")
            break
        if time.monotonic() >= deadline:
            caps_hit.append("max_seconds")
            warnings.append(
                f"stopped after {max_seconds:g} seconds (max_seconds cap) with {files_seen} files seen; "
                "the blueprint is partial"
            )
            break
        files_seen += 1

        language = language_of(rel)
        doc = is_doc_file(rel)
        if language is None and not doc:
            continue
        text = _read_text(os.path.join(root, rel))
        if text is None:
            skipped += 1
            continue
        files_read += 1

        if doc:
            declared = extract_declared(rel, text)
            if len(declared) > MAX_DECLARED_PER_FILE:
                warnings.append(
                    f"{rel}: kept the first {MAX_DECLARED_PER_FILE} of {len(declared)} declared items"
                )
                declared = declared[:MAX_DECLARED_PER_FILE]
            items.extend(declared)
            continue

        assert language is not None
        if is_test_file(rel):
            tests = extract_test_names(language, text)
            items.append(
                Item("tests", rel, _names_body(tests), rel, 1, {"kind": "test_file", "language": language, "tests": len(tests)})
            )
            for test in tests:
                items.append(Item("tests", test.name, test.text, rel, test.line, {"kind": "test", "language": language}))
            continue

        symbols = extract_symbols(language, text)
        inline_tests = [symbol for symbol in symbols if symbol.is_test]
        symbols = [symbol for symbol in symbols if not symbol.is_test]
        items.append(
            Item(
                "actual",
                rel,
                _names_body(symbols),
                rel,
                1,
                {"kind": "module", "language": language, "symbols": len(symbols), "depth": rel.count("/")},
            )
        )
        for symbol in symbols:
            extra: dict[str, Any] = {"kind": symbol.kind, "language": language}
            if symbol.nested:
                extra["nested"] = True
            items.append(Item("actual", symbol.name, symbol.text, rel, symbol.line, extra))
        for test in inline_tests:
            items.append(
                Item("tests", test.name, test.text, rel, test.line, {"kind": "test", "language": language, "inline": True})
            )

    if skipped:
        warnings.append(f"{skipped} file(s) skipped as unreadable, binary or larger than {MAX_FILE_BYTES} bytes")

    return ScanResult(
        items=items,
        files_seen=files_seen,
        files_read=files_read,
        elapsed_seconds=time.monotonic() - started,
        max_files=max_files,
        max_seconds=max_seconds,
        caps_hit=caps_hit,
        warnings=warnings,
    )


def _names_body(symbols: list[Symbol]) -> str:
    if not symbols:
        return ""
    names = [symbol.name for symbol in symbols[:40]]
    more = len(symbols) - len(names)
    return ", ".join(names) + (f" (+{more} more)" if more > 0 else "")
