"""A small parser for architecture maps (MAP.md) that carry evidence labels.

Recognised labels: ``documented``, ``observed-in-code`` and ``untested``,
matched as whole words, case-insensitively, with or without backticks.

The map is cut into blocks: a paragraph, a list item (with its continuation
lines) or a table row. A block that mentions a label is seeded as

* ``documented``       -> a ``declared`` blueprint item,
* ``observed-in-code`` -> an ``actual`` blueprint item,
* ``untested``         -> a ``map_untested`` finding.

A block inherits the labels of its nearest heading and of its table header
row. Blocks that merely define a label (they begin with it) are treated as
the legend and skipped. Fenced code is ignored. Limits are listed in
BUILD_NOTES.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .scan import BODY_CHARS, TITLE_CHARS, clean_inline

LABELS = ("documented", "observed-in-code", "untested")
_LABEL = re.compile(r"(?<![\w-])(documented|observed-in-code|untested)(?![\w-])", re.IGNORECASE)
_LEGEND = re.compile(r"^[\s|>*_`\-+\d.)(\[\]]*(documented|observed-in-code|untested)(?![\w-])", re.IGNORECASE)
_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_RULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")


@dataclass
class MapBlock:
    line: int
    text: str  # cleaned text of the block
    heading: str  # "Section > Subsection"
    labels: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.text if len(self.text) <= TITLE_CHARS else self.text[: TITLE_CHARS - 1].rstrip() + "…"

    @property
    def body(self) -> str:
        return self.text if len(self.text) <= BODY_CHARS else self.text[: BODY_CHARS - 1].rstrip() + "…"


def labels_in(text: str) -> list[str]:
    found = {match.group(1).lower() for match in _LABEL.finditer(text)}
    return [label for label in LABELS if label in found]


def map_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) == 1:
            title = clean_inline(match.group(2))
            if title:
                return title[:300]
    return fallback


def parse_map(text: str) -> list[MapBlock]:
    """Return the labelled blocks of a map, in document order."""
    blocks: list[MapBlock] = []
    headings: list[tuple[int, str]] = []  # (level, title)
    heading_labels: list[str] = []
    table_labels: list[str] = []
    in_table = False
    in_fence = False
    current: list[str] = []
    current_line = 0
    lines = text.splitlines()

    def emit(raw: str, line_no: int, inherited: list[str]) -> None:
        if _LEGEND.match(raw):
            return
        own = labels_in(raw)
        labels = [label for label in LABELS if label in own or label in inherited]
        if not labels:
            return
        cleaned = clean_inline(raw)
        if len(cleaned) < 8:
            return
        blocks.append(
            MapBlock(line=line_no, text=cleaned, heading=" > ".join(title for _, title in headings), labels=labels)
        )

    def flush() -> None:
        nonlocal current
        if current:
            emit(" ".join(current), current_line, heading_labels)
            current = []

    for index, raw in enumerate(lines):
        line_no = index + 1
        if _FENCE.match(raw):
            flush()
            in_fence = not in_fence
            in_table = False
            continue
        if in_fence:
            continue
        stripped = raw.strip()
        if not stripped:
            flush()
            in_table = False
            table_labels = []
            continue
        match = _HEADING.match(raw)
        if match:
            flush()
            in_table = False
            level = len(match.group(1))
            title = clean_inline(match.group(2))
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, title))
            heading_labels = labels_in(title)
            continue
        if _RULE.match(raw) and not stripped.startswith("|"):
            flush()
            continue
        if stripped.startswith("|"):
            flush()
            if _TABLE_SEP.match(raw):
                continue
            if not in_table:
                in_table = True
                following = lines[index + 1] if index + 1 < len(lines) else ""
                if _TABLE_SEP.match(following):
                    # Header row: its labels apply to every row beneath it.
                    table_labels = labels_in(stripped)
                    continue
                table_labels = []
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            row = " | ".join(cell for cell in cells if cell)
            inherited = [label for label in LABELS if label in table_labels or label in heading_labels]
            emit(row, line_no, inherited)
            continue
        in_table = False
        if _BULLET.match(raw):
            flush()
            current = [_BULLET.sub("", raw, count=1).strip()]
            current_line = line_no
            continue
        if not current:
            current_line = line_no
        current.append(stripped.lstrip("> ").strip())
    flush()
    return blocks
