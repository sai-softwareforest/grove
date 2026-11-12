"""Classify declared sentences before the gap heuristic looks at them.

A README mixes testable promises with install notes, lead-ins and slogans.
Each declared sentence gets one class, decided by fixed rules checked in this
order (the first rule that matches wins):

1. ``prose``     - a lead-in that ends with ":" (the list after it carries the
                   content), or a short fragment (at most six words) with no
                   verb-like word that is not an instruction ("Not a judge.").
2. ``limit``     - the sentence sits under a heading about limits or caveats,
                   or uses limit phrasing ("can be missed", "not supported").
3. ``behaviour`` - promise language: never, always, must, only, does not,
                   cannot, will not, "no <noun>", refuses, rejects.
4. ``prose``     - positioning: "<Name> is a/an/the/<someone>'s ..." with no
                   promise language.
5. ``setup``     - the sentence sits under an install/setup/requirements/
                   development/usage-example heading, starts with an
                   instruction verb ("Run ...", "Install ..."), or names a
                   path, file name, version number or dependency.
6. ``behaviour`` - everything else.

Only ``behaviour`` and ``limit`` sentences produce gap findings; ``limit``
findings rank below ``behaviour`` ones. ``setup`` and ``prose`` sentences stay
in the blueprint, with their class and reason, but produce no finding.

Like everything else in Grove this is a heuristic over words, not grammar.
"""

from __future__ import annotations

import re

BEHAVIOUR = "behaviour"
LIMIT = "limit"
SETUP = "setup"
PROSE = "prose"
CLASSES = (BEHAVIOUR, LIMIT, SETUP, PROSE)
FINDING_CLASSES = (BEHAVIOUR, LIMIT)

_LIMIT_HEADING = re.compile(r"\b(limits?|limitations?|caveats?|known issues?|gotchas?)\b", re.IGNORECASE)
_LIMIT_PHRASE = re.compile(
    r"\b(?:can|may|might|could) (?:be )?miss(?:ed)?\b|\bnot (?:yet )?supported\b|\bbest[- ]effort\b",
    re.IGNORECASE,
)
_SETUP_HEADING = re.compile(
    r"^(?:\d+[.)]?\s*)?(install(?:ation|ing)?|set ?up|setting up|getting started|quick ?start|requirements?|"
    r"prerequisites?|dependencies|development|developing|contributing|building|build(?:ing)? from source|"
    r"running (?:the )?tests|testing|usage examples?|examples?)\b",
    re.IGNORECASE,
)
_PROMISE = re.compile(
    r"(?<!-)\b(?:never|always|must|only|cannot|can't|won't|doesn't|don't|isn't|refuses?|rejects?)\b|"
    r"\b(?:does|do|will|shall|should) not\b|\bno\s+(?!longer\b|matter\b|one\b)[a-z]+",
    re.IGNORECASE,
)
_INSTRUCTION = re.compile(
    r"^(?:run|install|clone|type|set|add|copy|open|start|execute|export|see|cd|pip|npm|uv|cargo|make|go to)\b",
    re.IGNORECASE,
)
_PATH = re.compile(r"(?:^|\s)[\w.~-]*/[\w./-]*|\b[\w-]+\.(?:toml|lock|json|ya?ml|txt|cfg|ini|sh|env|db)\b")
_VERSION = re.compile(r"\b\d+\.\d+(?:\.\d+)*\b")
_DEPENDENCY = re.compile(
    r"\b(?:requires?|required|requirements?|depends? on|dependencies|dependency|pinned|installed|installs?)\b",
    re.IGNORECASE,
)
_POSITIONING = re.compile(r"^[A-Z][\w-]* is (?:an?\b|the\b|[\w ]+?'s\b)")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_AUXILIARY = frozenset(
    "is are was were be been has have had can could will would shall should may might must do does did".split()
)
_NOT_VERB_ENDINGS = ("ss", "us", "is", "ics")
TAGLINE_MAX_WORDS = 6


def _has_verb(words: list[str]) -> bool:
    """Crude: an auxiliary, or a word that looks like a 3rd-person or past form."""
    for word in words:
        lower = word.lower()
        if lower in _AUXILIARY:
            return True
        if len(lower) > 3 and lower.endswith("ed"):
            return True
        if len(lower) > 3 and lower.endswith("s") and not lower.endswith(_NOT_VERB_ENDINGS) and not lower.endswith("ous"):
            return True
    return False


def classify(text: str, heading: str = "") -> tuple[str, str]:
    """Return ``(class, reason)`` for one declared sentence."""
    sentence = text.strip()
    heading = heading or ""
    words = _WORD.findall(sentence)

    if sentence.endswith(":"):
        return PROSE, "lead-in ending with ':'"
    if len(words) <= TAGLINE_MAX_WORDS and not _has_verb(words) and not _INSTRUCTION.match(sentence):
        return PROSE, "short fragment with no verb"

    if _LIMIT_HEADING.search(heading):
        return LIMIT, f"under a limits heading ({heading!r})"
    match = _LIMIT_PHRASE.search(sentence)
    if match:
        return LIMIT, f"limit phrasing ({match.group(0)!r})"

    match = _PROMISE.search(sentence)
    if match:
        return BEHAVIOUR, f"promise language ({match.group(0).strip()!r})"

    if _POSITIONING.match(sentence):
        return PROSE, "positioning: '<Name> is a/the ...' with no promise language"

    if _SETUP_HEADING.match(heading.strip()):
        return SETUP, f"under a setup heading ({heading!r})"
    if _INSTRUCTION.match(sentence):
        return SETUP, "starts with an instruction verb"
    for pattern, what in ((_PATH, "a path or file name"), (_VERSION, "a version number"), (_DEPENDENCY, "dependency wording")):
        match = pattern.search(sentence)
        if match:
            return SETUP, f"names {what} ({match.group(0).strip().rstrip('.,;')!r})"

    return BEHAVIOUR, "default: no setup, prose or limit signal"
