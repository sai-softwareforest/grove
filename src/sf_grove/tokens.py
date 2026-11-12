"""Token helpers for the gap heuristic.

Deliberately crude: split identifiers and prose into lower-case words, drop
stop words and very short words, and strip a few English suffixes so that
"adds"/"add" and "greets"/"greeting" meet. This is not a real stemmer.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")

STOP_WORDS = frozenset(
    """
    a an and are as at be been but by can could did do does for from had has have how if in into is it its
    may might must no not of on or our shall should so such than that the their them then there these they
    this those to too use used using very was we were what when where which who why will with would you your
    all any both each also only just more most other some via per about above after again against between
    out over under up down off once here own same new get got let like one
    test tests testing tested spec specs src lib main mod init index readme docs doc md py rs ts tsx js jsx go
    """.split()
)


def stem(word: str) -> str:
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(text: str) -> frozenset[str]:
    """Meaningful tokens of a piece of prose, a path or an identifier."""
    found: set[str] = set()
    for word in _WORD.findall(text):
        for part in _CAMEL.findall(word):
            part = part.lower()
            if len(part) < 3 or part in STOP_WORDS or part.isdigit():
                continue
            stemmed = stem(part)
            if len(stemmed) >= 3 and stemmed not in STOP_WORDS:
                found.add(stemmed)
    return frozenset(found)
