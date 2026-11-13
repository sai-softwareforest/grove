"""Deterministic, read-only scan of a project tree.

The scan only ever opens files for reading. It produces blueprint items in
three layers:

* ``declared`` - headings and sentences from README/docs files (changelogs
  and release notes are walked and listed, but contribute no declared items);
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
from typing import Any, Iterator, Sequence

from pathspec import GitIgnoreSpec

from .claims import FINDING_CLASSES, classify

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
# Declared items kept per document. When a document has more, headings and
# behaviour/limit sentences are kept before setup/prose sentences (see
# _cap_declared), and the scan reports the file with kept and dropped counts.
MAX_DECLARED_PER_FILE = 1000
MAX_LISTED_PATHS = 50  # skipped files and changelogs named in a scan result
MAX_SYMBOLS_PER_FILE = 500
# Lines longer than this are not analysed. Some of the patterns below take
# time quadratic in the line length on unlucky input, so an unbounded line
# (minified code, embedded data) could outlast the scan's time cap by itself.
# The scan reports how many lines were skipped, and in which files.
MAX_LINE_CHARS = 5000
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
# Changelogs and release notes record what happened, not what the product
# promises. They are walked and listed but never enter the declared layer.
_CHANGELOG_STEM = re.compile(
    r"^(?:changelog|changes|history|news|release[-_ ]?notes|releases)(?:[-_.].*)?$", re.IGNORECASE
)
_CHANGELOG_DIRS = frozenset(
    {"changelog", "changelogs", "changelog.d", "changes", "release-notes", "release_notes", "releasenotes",
     "releases", "newsfragments"}
)
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
    skipped_files: list[dict[str, Any]] = field(default_factory=list)  # {"path", "reason", "bytes"?}
    changelog_files: list[str] = field(default_factory=list)
    declared_capped: list[dict[str, Any]] = field(default_factory=list)
    long_lines: list[dict[str, Any]] = field(default_factory=list)  # {"path", "lines"}
    exclude: list[str] = field(default_factory=list)  # the project's exclude patterns in effect
    excluded_files: int = 0  # files those patterns kept out; they are not part of files_seen

    def summary(self) -> dict[str, Any]:
        return {
            "files_seen": self.files_seen,
            "files_read": self.files_read,
            "excluded": {"patterns": list(self.exclude), "files": self.excluded_files},
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "caps": {
                "max_files": self.max_files,
                "max_seconds": self.max_seconds,
                "hit": list(self.caps_hit),
                "max_declared_per_file": MAX_DECLARED_PER_FILE,
                "declared_capped": [dict(entry) for entry in self.declared_capped],
            },
            "warnings": list(self.warnings),
            "skipped_files": _listing(self.skipped_files),
            "long_lines": {
                "max_line_chars": MAX_LINE_CHARS,
                "lines": sum(entry["lines"] for entry in self.long_lines),
                "files": _listing(self.long_lines),
            },
            "changelog_files": {
                **_listing(self.changelog_files),
                "why": "changelogs and release notes are not product promises; they add no declared items",
            },
        }


def _listing(entries: list[Any]) -> dict[str, Any]:
    """A bounded list plus the true count, so a long list never hides its size."""
    shown = entries[:MAX_LISTED_PATHS]
    return {"total": len(entries), "items": list(shown), "omitted": len(entries) - len(shown)}


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


class ExcludeError(ValueError):
    """An exclude pattern that cannot be compiled."""


def exclude_spec(patterns: Sequence[str]) -> GitIgnoreSpec | None:
    """A project's exclude list as one matcher, or None for an empty list.

    The patterns are gitignore-style and relative to the project root. They
    are matched against each file's path, so unlike git a later ``!pattern``
    can bring back a file under an excluded directory.
    """
    if not patterns:
        return None
    try:
        return GitIgnoreSpec.from_lines(patterns)
    except ValueError as exc:  # pathspec's pattern errors are ValueError subclasses
        raise ExcludeError(str(exc)) from exc


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


def is_changelog_file(rel_path: str) -> bool:
    """CHANGELOG/CHANGES/HISTORY/NEWS/RELEASE-NOTES files, or a doc under a changelog directory."""
    parts = rel_path.split("/")
    stem, ext = os.path.splitext(parts[-1])
    if ext.lower() in DOC_EXTENSIONS and _CHANGELOG_STEM.match(stem):
        return True
    if stem.lower().startswith("readme"):
        return False
    return ext.lower() in DOC_DIR_EXTENSIONS and any(part.lower() in _CHANGELOG_DIRS for part in parts[:-1])


def language_of(rel_path: str) -> str | None:
    return LANGUAGES.get(os.path.splitext(rel_path)[1].lower())


# --------------------------------------------------------------------------
# Declared layer: markdown-ish prose

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^\s{0,3}(=+|-+)\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?")
# The leading "(?:\|\s*)?" must not be written "\|?\s*": two adjacent \s* runs
# make the match quadratic on a long run of spaces.
_TABLE_SEP = re.compile(r"^\s*(?:\|\s*)?:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
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


class Clock:
    """The scan's time cap, checked between lines so one large file cannot outlast it."""

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self.expired = False

    def over(self) -> bool:
        if not self.expired and time.monotonic() >= self.deadline:
            self.expired = True
        return self.expired


def long_line_count(text: str) -> int:
    """How many lines of ``text`` are too long to be analysed (see MAX_LINE_CHARS)."""
    return sum(1 for line in text.splitlines() if len(line) > MAX_LINE_CHARS)


def extract_declared(rel_path: str, text: str, clock: Clock | None = None) -> list[Item]:
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
        line_index = 0  # offsets only grow, so the line of each sentence is found by walking forward once
        for sentence in _SENTENCE_END.split(joined):
            offset = joined.find(sentence, position)
            if offset < 0:
                offset = position
            position = offset + len(sentence)
            sentence = sentence.strip()
            if len(_ALPHA_WORD.findall(sentence)) < 3 or _LICENCE_TEXT.search(sentence):
                continue
            while line_index + 1 < len(starts) and starts[line_index + 1][0] <= offset:
                line_index += 1
            line_no = starts[line_index][1]
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
        if clock is not None and clock.over():
            break  # the scan reports the time cap; what was read so far is kept
        if len(raw) > MAX_LINE_CHARS:
            flush()  # not analysed; the scan counts and reports these lines
            continue
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


def extract_symbols(language: str, text: str, clock: Clock | None = None) -> list[Symbol]:
    """Definitions in a source file. Rust ``#[test]`` functions are flagged as tests."""
    symbols: list[Symbol] = []
    pending_rust_test = False
    for index, line in enumerate(text.splitlines()):
        if len(symbols) >= MAX_SYMBOLS_PER_FILE or (clock is not None and clock.over()):
            break
        if len(line) > MAX_LINE_CHARS:
            continue
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


def extract_test_names(language: str, text: str, clock: Clock | None = None) -> list[Symbol]:
    """Test names in a file whose name matches a test-file pattern."""
    if language == "rust":
        return [symbol for symbol in extract_symbols("rust", text, clock) if symbol.is_test]
    tests: list[Symbol] = []
    for index, line in enumerate(text.splitlines()):
        if len(tests) >= MAX_SYMBOLS_PER_FILE or (clock is not None and clock.over()):
            break
        if len(line) > MAX_LINE_CHARS:
            continue
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


def _read_text(path: str) -> tuple[str | None, str]:
    """Read a file as text. Returns (text, "") or (None, reason) with reason
    ``too_large``, ``binary`` or ``unreadable``."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None, "unreadable"
    if len(data) > MAX_FILE_BYTES:
        return None, "too_large"
    if b"\0" in data[:4096]:
        return None, "binary"
    # utf-8-sig drops a leading byte order mark, which would otherwise hide
    # the first line from every pattern anchored at the start of a line.
    return data.decode("utf-8-sig", errors="replace"), ""


def _keep_first(item: Item) -> bool:
    """Inside the per-file cap, headings and possible claims beat setup and prose."""
    extra = item.extra
    return extra.get("kind") == "heading" or extra.get("class") in FINDING_CLASSES


def _cap_declared(items: list[Item], cap: int) -> tuple[list[Item], dict[str, int]]:
    """Keep at most ``cap`` items: headings and behaviour/limit sentences first
    (in document order), then setup/prose sentences in document order.
    Returns the kept items, still in document order, and dropped counts by class."""
    if len(items) <= cap:
        return items, {}
    first = [index for index, item in enumerate(items) if _keep_first(item)]
    rest = [index for index, item in enumerate(items) if not _keep_first(item)]
    keep = set((first + rest)[:cap])
    dropped: dict[str, int] = {}
    for index, item in enumerate(items):
        if index not in keep:
            name = item.extra.get("class") or item.extra.get("kind", "other")
            dropped[name] = dropped.get(name, 0) + 1
    return [item for index, item in enumerate(items) if index in keep], dict(sorted(dropped.items()))


def scan_tree(
    root: str | os.PathLike[str],
    max_files: int = DEFAULT_MAX_FILES,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    exclude: Sequence[str] = (),
) -> ScanResult:
    """Walk ``root`` and return blueprint items. Never writes inside ``root``.

    Files matching one of the ``exclude`` patterns are walked and counted but
    never read; a pattern that cannot be compiled raises :class:`ExcludeError`
    before anything is walked.
    """
    root = str(Path(root))
    excluding = exclude_spec(exclude)
    excluded_files = 0
    started = time.monotonic()
    deadline = started + max_seconds
    clock = Clock(deadline)  # also checked between the lines of each file
    items: list[Item] = []
    caps_hit: list[str] = []
    warnings: list[str] = []
    files_seen = 0
    files_read = 0
    skipped: list[dict[str, Any]] = []
    changelogs: list[str] = []
    declared_capped: list[dict[str, Any]] = []
    long_lines: list[dict[str, Any]] = []

    for rel in walk_files(root):
        if excluding is not None and excluding.match_file(rel):
            # Not a file of this blueprint: it does not use up the file cap. The
            # time cap still holds while a large excluded tree is passed over.
            if clock.over():
                break
            excluded_files += 1
            continue
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
        if language is None and is_changelog_file(rel):
            changelogs.append(rel)  # walked and counted, never read into the declared layer
            continue
        if language is None and not doc:
            continue
        path = os.path.join(root, rel)
        text, reason = _read_text(path)
        if text is None:
            entry: dict[str, Any] = {"path": rel, "reason": reason}
            if reason == "too_large":
                try:
                    entry["bytes"] = os.stat(path).st_size
                except OSError:
                    pass
            skipped.append(entry)
            continue
        files_read += 1
        too_long = long_line_count(text)
        if too_long:
            long_lines.append({"path": rel, "lines": too_long})

        if doc:
            declared = extract_declared(rel, text, clock)
            total = len(declared)
            declared, dropped = _cap_declared(declared, MAX_DECLARED_PER_FILE)
            if dropped:
                declared_capped.append(
                    {
                        "path": rel,
                        "total": total,
                        "kept": len(declared),
                        "dropped": total - len(declared),
                        "cap": MAX_DECLARED_PER_FILE,
                        "dropped_by_class": dropped,
                    }
                )
                warnings.append(
                    f"{rel}: kept {len(declared)} of {total} declared items (per-file cap {MAX_DECLARED_PER_FILE}); "
                    f"dropped {total - len(declared)}, setup and prose sentences first"
                )
            items.extend(declared)
            continue

        assert language is not None
        if is_test_file(rel):
            tests = extract_test_names(language, text, clock)
            items.append(
                Item("tests", rel, _names_body(tests), rel, 1, {"kind": "test_file", "language": language, "tests": len(tests)})
            )
            for test in tests:
                items.append(Item("tests", test.name, test.text, rel, test.line, {"kind": "test", "language": language}))
            continue

        symbols = extract_symbols(language, text, clock)
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

    if clock.expired and "max_seconds" not in caps_hit:
        # The cap ran out inside the last file walked, or while passing over
        # excluded files, so the loop ended without reporting it.
        caps_hit.append("max_seconds")
        warnings.append(
            f"stopped after {max_seconds:g} seconds (max_seconds cap) with {files_seen} files seen; "
            "the blueprint is partial"
        )

    if skipped:
        names = ", ".join(entry["path"] for entry in skipped[:10])
        more = f" (+{len(skipped) - 10} more; see skipped_files)" if len(skipped) > 10 else ""
        warnings.append(
            f"{len(skipped)} file(s) skipped as unreadable, binary or larger than {MAX_FILE_BYTES} bytes: {names}{more}"
        )

    if long_lines:
        total_lines = sum(entry["lines"] for entry in long_lines)
        names = ", ".join(entry["path"] for entry in long_lines[:10])
        more = f" (+{len(long_lines) - 10} more; see long_lines)" if len(long_lines) > 10 else ""
        warnings.append(
            f"{total_lines} line(s) longer than {MAX_LINE_CHARS} characters in {len(long_lines)} file(s) "
            f"were not analysed: {names}{more}"
        )

    return ScanResult(
        items=items,
        files_seen=files_seen,
        files_read=files_read,
        elapsed_seconds=time.monotonic() - started,
        max_files=max_files,
        max_seconds=max_seconds,
        caps_hit=caps_hit,
        warnings=warnings,
        skipped_files=skipped,
        changelog_files=changelogs,
        declared_capped=declared_capped,
        long_lines=long_lines,
        exclude=list(exclude),
        excluded_files=excluded_files,
    )


def _names_body(symbols: list[Symbol]) -> str:
    if not symbols:
        return ""
    names = [symbol.name for symbol in symbols[:40]]
    more = len(symbols) - len(names)
    return ", ".join(names) + (f" (+{more} more)" if more > 0 else "")
