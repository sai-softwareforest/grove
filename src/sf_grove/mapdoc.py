"""A small parser for architecture maps (MAP.md) that carry evidence labels.

Recognised labels: ``documented``, ``observed-in-code`` and ``untested``,
matched as whole words, case-insensitively, with or without backticks.

The map is cut into blocks: a paragraph, a list item (with its continuation
lines) or a table row. A block that mentions a label is seeded as

* ``documented``       -> a ``declared`` blueprint item,
* ``observed-in-code`` -> an ``actual`` blueprint item,
* ``untested``         -> a ``map_untested`` finding.

A block inherits the labels of its nearest heading, of its table header row,
and of a short lead-in line ending in ":" ("Missing — untested:") for the
list items directly under it.

The legend is never seeded. A block is taken to be legend, not a claim, when

1. it sits under a legend heading ("Legend", "Evidence labels", "Labels",
   "Notation", "Key", "How to read this map");
2. it begins with a label ("`untested` — no test was found"). A real claim
   written as "Untested: ..." is therefore skipped too; write the label after
   the claim instead;
3. it defines or lists the labels: it names two or more labels and either
   uses legend words (label, legend, means, stands for, denotes, used below)
   or follows two or more labels with a definition ("documented: ...",
   "untested (no test found)"), or it says "the label X" / "X means ...";
4. it is a short lead-in that only introduces labels: it ends with ":" (or is
   wholly bold) and has at most four words besides the labels. Its labels
   pass to the list below it; the lead-in itself is not seeded.

A heading that is itself a legend heading, or that names all three labels,
passes no labels down. Fenced code is ignored. Limits are listed in
BUILD_NOTES.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .scan import BODY_CHARS, MAX_LINE_CHARS, TITLE_CHARS, clean_inline
from .scan import _FENCE, _LIST_MARKER, _RULE, _TABLE_SEP, atx_heading  # the line patterns are defined once, in scan.py

LABELS = ("documented", "observed-in-code", "untested")
_LABEL = re.compile(r"(?<![\w-])(documented|observed-in-code|untested)(?![\w-])", re.IGNORECASE)
_LEGEND = re.compile(r"^[\s|>*_`\-+\d.)(\[\]]*(documented|observed-in-code|untested)(?![\w-])", re.IGNORECASE)
_BULLET = re.compile(_LIST_MARKER)  # a map keeps a task-list box in the text
_LABEL_WORDS = r"(?:documented|observed-in-code|untested)"
_LEGEND_HEADING = re.compile(
    r"\blegend\b|\b(?:evidence )?labels?\b|\bnotation\b|\bhow to read\b|^(?:key|evidence)$", re.IGNORECASE
)
_LEGEND_WORDS = re.compile(
    r"\b(?:labels?|labelled|legend|means|meaning|stands for|denotes|defined as|to mean|"
    r"used (?:below|here|throughout|in this (?:map|document|file)))\b",
    re.IGNORECASE,
)
# A label followed by a definition: "documented: ...", "untested — ...", "observed-in-code (read in source)".
_LABEL_DEFINED = re.compile(
    r"(?<![\w-])" + _LABEL_WORDS + r"(?![\w-])[`*_'\"]*\s*(?:—|–|:|=|\(|-\s|means\b|stands for\b|denotes\b)",
    re.IGNORECASE,
)
_ONE_LABEL_DEFINED = re.compile(
    r"\blabels?\s+[`*_'\"]*" + _LABEL_WORDS + r"(?![\w-])|"
    r"(?<![\w-])" + _LABEL_WORDS + r"(?![\w-])[`*_'\"]*\s+(?:means|stands for|denotes|is used to|is used for)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
MAX_LEAD_IN_WORDS = 4


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


def is_legend_heading(title: str) -> bool:
    """A heading that introduces the legend rather than a part of the codebase."""
    return bool(_LEGEND_HEADING.search(title)) or len(labels_in(title)) == len(LABELS)


def legend_reason(raw: str) -> str | None:
    """Why a block reads as the legend rather than a labelled claim, or None."""
    if _LEGEND.match(raw):
        return "begins with a label"
    labels = labels_in(raw)
    if len(labels) >= 2 and (_LEGEND_WORDS.search(raw) or len(_LABEL_DEFINED.findall(raw)) >= 2):
        return "defines or lists the labels"
    if labels and _ONE_LABEL_DEFINED.search(raw):
        return "defines a label"
    return None


def is_lead_in(raw: str) -> bool:
    """A short line that only introduces what follows: ends with ':' or is wholly bold,
    with at most MAX_LEAD_IN_WORDS words besides the labels."""
    stripped = raw.strip()
    bold = len(stripped) > 4 and stripped[:2] in ("**", "__") and stripped[-2:] == stripped[:2]
    cleaned = clean_inline(stripped).rstrip(" *_")
    if not (cleaned.endswith(":") or bold):
        return False
    words = [word for word in _WORD.findall(_LABEL.sub(" ", cleaned)) if len(word) > 1 or word.isupper()]
    return len(words) <= MAX_LEAD_IN_WORDS


def map_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        atx = atx_heading(line)
        if atx and atx[0] == 1:
            title = clean_inline(atx[1])
            if title:
                return title[:300]
    return fallback


def parse_map(text: str) -> list[MapBlock]:
    """Return the labelled blocks of a map, in document order."""
    blocks: list[MapBlock] = []
    headings: list[tuple[int, str]] = []  # (level, title)
    heading_labels: list[str] = []
    table_labels: list[str] = []
    lead_labels: list[str] = []  # from a lead-in such as "Missing — untested:"
    lead_indent = -1  # -1: the lead-in was a paragraph; else the indent of the list item that was one
    in_legend = False  # under a legend heading
    in_table = False
    in_fence = False
    current: list[str] = []
    current_line = 0
    current_indent: int | None = None  # None: paragraph; else the list item's indent
    lines = text.splitlines()

    def emit(raw: str, line_no: int, inherited: list[str], indent: int | None = None, row: bool = False) -> None:
        nonlocal lead_labels, lead_indent
        if in_legend:
            return
        if not row and is_lead_in(raw):
            # Not a claim itself; its labels (unless it is the legend's own
            # lead-in) apply to the list items directly beneath it.
            own = labels_in(raw)
            lead_labels = [] if _LEGEND_WORDS.search(raw) or len(own) == len(LABELS) else own
            lead_indent = -1 if indent is None else indent
            return
        if indent is None or indent <= lead_indent:
            lead_labels = []  # a paragraph, row or sibling item ends the lead-in's list
        elif lead_labels:
            inherited = [label for label in LABELS if label in inherited or label in lead_labels]
        if legend_reason(raw):
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
            emit(" ".join(current), current_line, heading_labels, current_indent)
            current = []

    for index, raw in enumerate(lines):
        line_no = index + 1
        if len(raw) > MAX_LINE_CHARS:
            flush()  # too long to analyse; ingest reports the count (see scan.MAX_LINE_CHARS)
            in_table = False
            continue
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
        atx = atx_heading(raw)
        if atx:
            flush()
            in_table = False
            level = atx[0]
            title = clean_inline(atx[1])
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, title))
            in_legend = any(is_legend_heading(name) for _, name in headings)
            heading_labels = [] if is_legend_heading(title) else labels_in(title)
            lead_labels = []
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
                if len(following) <= MAX_LINE_CHARS and _TABLE_SEP.match(following):
                    # Header row: its labels apply to every row beneath it.
                    table_labels = labels_in(stripped)
                    continue
                table_labels = []
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            row = " | ".join(cell for cell in cells if cell)
            inherited = [label for label in LABELS if label in table_labels or label in heading_labels]
            emit(row, line_no, inherited, row=True)
            continue
        in_table = False
        if _BULLET.match(raw):
            flush()
            current = [_BULLET.sub("", raw, count=1).strip()]
            current_line = line_no
            current_indent = len(raw) - len(raw.lstrip())
            continue
        if not current:
            current_line = line_no
            current_indent = None
        current.append(stripped.lstrip("> ").strip())
    flush()
    return blocks
