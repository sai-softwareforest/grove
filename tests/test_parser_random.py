"""R-SCAN-7 (WO-24): whatever the input, the extractors do not raise, give the
same output twice and take time within a linear bound.

The input is generated, not collected. A seeded generator from the standard
library builds lines and documents from a small alphabet: the characters and
words the patterns act on, and a dozen hand-picked awkward strings. A line is
a few pieces, each repeated a random number of times, because every slow path
found so far was a long run of one piece. A document is random lines, or one
line repeated (a long paragraph, list or table), or lines filled to the line
cap. Chance alone would leave most pieces without a long paragraph of their
own, so each piece also gets one. The seed is fixed: every machine runs the
same cases, and a failure names a case that can be built again. To explore,
change SEED; no seed may fail.

What the time bound can and cannot see is worked out beside its two constants.
"""

from __future__ import annotations

import random
import time
from functools import cache
from typing import Any, Callable

import pytest

from sf_grove import mapdoc, service
from sf_grove.claims import classify
from sf_grove import prism
from sf_grove.scan import (
    LANGUAGES,
    MAX_LINE_CHARS,
    extract_declared,
    extract_imports,
    extract_symbols,
    extract_test_names,
    manifest_dependencies,
)
from sf_grove.tokens import tokens

SEED = 24  # the work order's number

ALPHABET = (
    # Markdown: what the line and inline patterns look for
    "#", "# ", "[", "]", "(", ")", "![", "](", "][", "<", ">", "> ", "|", "| ", "-", "- ", "1. ", "[x] ",
    "=", "~", "`", "```", "*", "_", ":", "---",
    # sentences, quoting and white space
    ".", ". ", "!", "?", "'", '"', "\\", "/", ",", " ", "\t", "a", "B", "7", "word ",
    # words the map reader and the claim classes act on
    "untested", "documented", "observed-in-code", "label ", "means ", "Legend", "never ", "no ", "is a ",
    "limits", "licence", "install ", "1.2", "a.toml",
    # definitions and tests in the four languages
    "def a", "class A", "async ", "fn a", "pub ", "pub(", "struct A", "#[test]", "function a", "export ",
    "const a = ", "=>", "it('a'", "test(", "func (a) A", "func Test", "type A", "{", "}", "$", ";",
    # imports, manifests and list entries (WO-41)
    "import ", "from ", "require(", "use ", "::", "import (", "require ", " v1", "a.b/c", "[project]", "a = ",
    "- [", "](https://a", ") - ",
)  # fmt: skip
# Instead of a vendored corpus: a byte order mark, NUL, line ends that are not
# "\n", a no-break space, a combining accent, a right-to-left override, two
# non-ASCII letters that match ASCII ones when a pattern ignores case, a
# character outside the basic plane, a lone surrogate, a zero-width space.
AWKWARD = (
    "\ufeff", "\x00", "\r", "\r\n", "\x0c", "\u2028", "\u00a0", "e\u0301", "\u202e", "\u017f", "\u0130",
    "\U0001d518", "\ud800", "\u200b",
)  # fmt: skip
PIECES = ALPHABET + AWKWARD
REPEATS = (1, 1, 1, 1, 2, 2, 3, 5, 8, 40, 300)  # mostly short, sometimes a long run of one piece

# (characters, documents) of random shape: many small documents, fewer of each
# larger size. PARAGRAPH_CHARS is the size of the paragraph each piece gets.
# The cases run smallest first, so a path that grows faster than linearly
# fails at the first size that shows it and not at the largest.
SIZES = ((300, 160), (3_000, 60), (30_000, 12), (300_000, 2))
PARAGRAPH_CHARS = 20_000

# The bound is FLOOR_SECONDS + SECONDS_PER_CHAR * characters, for the faster
# of the two runs. On the machine that wrote this the slowest input found
# costs 1.5 microseconds a character (thousands of lines of one character),
# and no case of this seed uses more than a tenth of its bound. The floor is
# for small inputs, where a pause of the machine is longer than the work.
#
# What the bound sees: a path whose cost is q * n * n, once q * n is well over
# SECONDS_PER_CHAR. The map reader's paragraph of "[" that this test was
# written against (q about 6e-9: 9 seconds for 40 000 characters) is caught
# from 10 000 characters on. What it does not see: a milder quadratic (the
# paragraph defect of WO-06 had q about 2e-11 and needs more than a megabyte),
# and a pattern that is slow only on one line up to the line cap. Those are
# held by the fixed cases in test_scan_robustness.py.
FLOOR_SECONDS = 0.25
SECONDS_PER_CHAR = 10e-6


def random_line(rng: random.Random, pieces: int = 8) -> str:
    return "".join(rng.choice(PIECES) * rng.choice(REPEATS) for _ in range(rng.randint(1, pieces)))


def random_lines(rng: random.Random, size: int) -> tuple[str, str]:
    parts: list[str] = []
    length = 0
    while length < size:
        parts += [random_line(rng), rng.choice(("\n", "\n", "\n", "\n\n"))]
        length += len(parts[-2]) + len(parts[-1])
    return "random lines", "".join(parts)


def repeated_line(rng: random.Random, size: int, unit: str, between: str) -> tuple[str, str]:
    """One short line many times over: a paragraph, a list item with its
    continuation lines, a table or a run of headings, under a first line that
    may be a heading or a lead-in."""
    head = rng.choice(("", random_line(rng, 3) + "\n", random_line(rng, 3) + "\n\n"))
    unit = unit[:80] or "a"
    text = head + between.join([unit] * (size // len(unit + between) + 1)) + "\n"
    return f"{unit!r} repeated, joined by {between!r}, under {head[:40]!r}", text


def filled_lines(rng: random.Random, size: int) -> tuple[str, str]:
    """Lines filled with one piece, to the line cap when the document is that
    large (the longest line that is analysed) and, now and then, to one
    character more (the shortest that is not)."""
    lines: list[str] = []
    for _ in range(max(1, size // MAX_LINE_CHARS)):
        start = random_line(rng, 2)[:40]
        piece = rng.choice(PIECES)
        width = min(size, MAX_LINE_CHARS) + (1 if rng.random() < 0.1 else 0)
        lines.append((start + piece * (width // len(piece) + 1))[:width])
    return f"{len(lines)} line(s) filled with one piece each", "\n".join(lines) + "\n"


def random_document(rng: random.Random, size: int) -> tuple[str, str]:
    """``(how it was built, text)`` of roughly ``size`` characters."""
    shape = rng.choice(("lines", "lines", "repeated", "repeated", "filled"))
    if shape == "lines":
        return random_lines(rng, size)
    if shape == "repeated":
        return repeated_line(rng, size, random_line(rng, 3), rng.choice(("\n", "\n", "\n  ", " ", "\n\n")))
    return filled_lines(rng, size)


@cache
def cases() -> tuple[tuple[str, str], ...]:
    rng = random.Random(SEED)
    built = [("an awkward string alone", piece) for piece in ("",) + AWKWARD]
    built += [("front matter or a fence that never closes", text) for text in ("---\n", "---\na: b\n", "```\n# a\n", "~~~")]
    for size, documents in SIZES:
        built += [random_document(rng, size) for _ in range(documents)]
    for piece in PIECES:  # one block of nothing but this piece: no blank line ends it
        unit = piece * rng.choice((1, 30, 30, 30))
        built.append(repeated_line(rng, PARAGRAPH_CHARS, unit, rng.choice(("\n", "\n", " ", "\n  "))))
    return tuple(sorted(built, key=lambda case: len(case[1])))


def _symbols(language: str) -> Callable[[str], Any]:
    return lambda text: extract_symbols(language, text)


def _test_names(language: str) -> Callable[[str], Any]:
    return lambda text: extract_test_names(language, text)


def _imports(language: str) -> Callable[[str], Any]:
    return lambda text: extract_imports(language, text)


def _manifest(name: str) -> Callable[[str], Any]:
    return lambda text: manifest_dependencies(name, text)


EXTRACTORS: dict[str, Callable[[str], Any]] = {
    "declared": lambda text: extract_declared("README.md", text),
    "map": lambda text: (mapdoc.map_title(text, "fallback"), mapdoc.parse_map(text)),
    # One sentence under one heading, both as long as the line cap allows.
    "classify": lambda text: classify(text[:MAX_LINE_CHARS], text[-MAX_LINE_CHARS:]),
    "tokens": tokens,
    "outline": service._outline,  # the headings of a knowledge document; no line cap applies there
    **{f"symbols-{language}": _symbols(language) for language in sorted(set(LANGUAGES.values()))},
    **{f"tests-{language}": _test_names(language) for language in sorted(set(LANGUAGES.values()))},
    # WO-41: what a scan reads for Prism, a list entry, and the head of a verdict note.
    **{f"imports-{language}": _imports(language) for language in sorted(set(LANGUAGES.values()))},
    **{f"manifest-{name}": _manifest(name) for name in ("pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "go.mod")},
    "prism-list": lambda text: prism.parse_list(text, "awesome-testing", ()),
    "prism-verdict": prism.parse_verdict,
}


def timed(extract: Callable[[str], Any], text: str) -> tuple[Any, float]:
    started = time.perf_counter()
    result = extract(text)
    return result, time.perf_counter() - started


@pytest.mark.parametrize("name", sorted(EXTRACTORS))
def test_random_input_never_raises_never_differs_and_costs_linear_time(name: str) -> None:
    extract = EXTRACTORS[name]
    for number, (how, text) in enumerate(cases()):
        where = f"{name}, case {number} of seed {SEED} ({how}; {len(text)} characters), starting {text[:80]!r}"
        try:
            first, seconds = timed(extract, text)
            again, seconds_again = timed(extract, text)
        except Exception as error:
            raise AssertionError(f"raised {error!r}: {where}") from error
        assert first == again, f"two runs differ: {where}"
        allowed = FLOOR_SECONDS + SECONDS_PER_CHAR * len(text)
        assert min(seconds, seconds_again) <= allowed, f"{min(seconds, seconds_again):.2f} s, over the linear bound of {allowed:.2f} s: {where}"


def test_the_generator_is_seeded_and_reaches_what_it_should() -> None:
    cases.cache_clear()
    first = cases()
    cases.cache_clear()
    assert cases() == first, "the same seed must give the same cases"
    texts = [text for _, text in first]
    assert [len(text) for text in texts] == sorted(len(text) for text in texts), "smallest first"
    everything = "\n".join(texts)
    assert all(piece in everything for piece in PIECES), "every piece of the alphabet is used"
    widths = {len(line) for text in texts for line in text.split("\n")}
    assert MAX_LINE_CHARS in widths and MAX_LINE_CHARS + 1 in widths, "a line at the cap and one over it"
    assert max(len(text) for text in texts) >= SIZES[-1][0], "a document of the largest size"
    assert sum(len(text) >= PARAGRAPH_CHARS for text in texts) >= len(PIECES), "a long paragraph for every piece"
