"""Gap findings from simple token overlap between the three blueprint layers.

Every finding here is a heuristic, not a verdict:

* ``declared_untested``   - a declared sentence shares no meaningful token with
  any test name or test file name;
* ``declared_unseen``     - a declared sentence shares no meaningful token with
  any module path or symbol name;
* ``actual_undocumented`` - a source module whose file name is never mentioned
  in the declared layer (capped, shallowest paths first).

"Meaningful token" is defined in :mod:`sf_grove.tokens`. One shared token is
enough to count as overlap, so the heuristic errs towards silence.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from .tokens import tokens

MAX_UNDOCUMENTED = 25
MIN_CLAIM_TOKENS = 2
CLAIM_KINDS = ("sentence", "map_block")


def _clip(text: str, limit: int = 140) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def compute_findings(
    read_items: Callable[[str | None], Iterable[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (findings, notes) for one project's blueprint items.

    ``read_items(layer)`` yields blueprint rows as dicts with ``extra`` already
    decoded; ``None`` means every layer. It is called twice (all items, then
    the declared layer again) so that a large blueprint is streamed rather
    than held in memory.
    """
    test_tokens: set[str] = set()
    actual_tokens: set[str] = set()
    declared_tokens: set[str] = set()
    declared_text: list[str] = []
    modules: list[dict[str, Any]] = []

    for item in read_items(None):
        kind = (item.get("extra") or {}).get("kind")
        layer = item["layer"]
        if layer == "tests":
            if kind == "test_file":
                test_tokens |= tokens(item["title"].rsplit("/", 1)[-1])
            else:
                test_tokens |= tokens(item["title"])
        elif layer == "actual":
            actual_tokens |= tokens(item["title"])
            if kind == "module" and item.get("origin") == "scan":
                modules.append(item)
        elif layer == "declared":
            text = item["body"] or item["title"]
            declared_tokens |= tokens(text)
            declared_text.append(text.lower())

    findings: list[dict[str, Any]] = []

    for item in read_items("declared"):
        if (item.get("extra") or {}).get("kind") not in CLAIM_KINDS:
            continue
        item_tokens = tokens(item["body"] or item["title"])
        if len(item_tokens) < MIN_CLAIM_TOKENS:
            continue
        where = f"{item.get('source_path')}:{item.get('source_line')}"
        seen = sorted(item_tokens & actual_tokens)
        evidence = {
            "item_ids": [item["id"]],
            "source_path": item.get("source_path"),
            "source_line": item.get("source_line"),
            "tokens": sorted(item_tokens),
        }
        if not item_tokens & test_tokens:
            findings.append(
                {
                    "kind": "declared_untested",
                    "summary": f"No test name overlaps this declared statement: \"{_clip(item['title'])}\" ({where})",
                    "evidence": {**evidence, "seen_in_actual": bool(seen), "actual_tokens": seen},
                }
            )
        if not seen:
            findings.append(
                {
                    "kind": "declared_unseen",
                    "summary": f"No module or symbol name overlaps this declared statement: \"{_clip(item['title'])}\" ({where})",
                    "evidence": evidence,
                }
            )

    joined_declared = "\n".join(declared_text)
    undocumented: list[dict[str, Any]] = []
    for module in modules:
        extra = module.get("extra") or {}
        if not extra.get("symbols"):
            continue
        path = module["title"]
        name = path.rsplit("/", 1)[-1]
        if path.lower() in joined_declared or name.lower() in joined_declared:
            continue
        stem_tokens = tokens(name.rsplit(".", 1)[0])
        if not stem_tokens:
            continue  # names like main.py or index.ts say too little to judge
        if stem_tokens <= declared_tokens:
            continue
        undocumented.append(module)
    undocumented.sort(key=lambda module: (module["title"].count("/"), module["title"]))
    for module in undocumented[:MAX_UNDOCUMENTED]:
        findings.append(
            {
                "kind": "actual_undocumented",
                "summary": f"Module {module['title']} is not mentioned in the declared layer",
                "evidence": {"item_ids": [module["id"]], "paths": [module["title"]]},
            }
        )

    notes = {
        "actual_undocumented_candidates": len(undocumented),
        "actual_undocumented_cap": MAX_UNDOCUMENTED,
        "actual_undocumented_omitted": max(0, len(undocumented) - MAX_UNDOCUMENTED),
    }
    return findings, notes
