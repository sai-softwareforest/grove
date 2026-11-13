"""How often a finding is right, and whether a search finds the note (R-QUAL-10, WO-23).

The corpus is `fixtures/measure/`: three small projects, each with a list of
its true gaps written by hand, and sixteen notes with twenty-six queries and
the notes each one should find. `fixtures/measure/README.md` says what counts
as a true gap and when a finding counts for one. The lists were written by
reading the projects; no rule of the product was asked.

Each number is held to a floor: the value measured on the date below, cut to
two decimals. A change that lowers a number fails and prints the findings or
queries behind it. A change that raises one fails too, more quietly: the
floor is then stale, and a stale floor no longer catches the next regression.
Raise it in the same change and record the new numbers with a date.

To print today's numbers, the wrong findings and the missed gaps:

    uv run python tests/test_measure.py

The numbers describe this corpus. It is small and was written by someone who
knew the heuristic, so they are a line to hold, not an estimate for other
projects.
"""

from __future__ import annotations

import json
import math
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pytest

from conftest import REPO
from sf_grove.scan import is_test_file
from sf_grove.service import FINDING_KINDS, SCAN_FINDING_KINDS, Grove

MEASURE = REPO / "fixtures" / "measure"
PROJECTS = ("parcel", "shelf", "tally")
NOTES = MEASURE / "notes"
QUERIES = MEASURE / "queries.json"
TOP = 10  # a search is judged on its first ten results

MEASURED_ON = "2026-11-13"
# kind: (precision, recall), over the three projects together.
FINDING_FLOORS: dict[str, tuple[float, float]] = {
    "declared_untested": (0.33, 0.29),  # 7 of 21 findings right; 7 of 24 true gaps found
    "declared_unseen": (0.09, 0.33),  # 2 of 22; 2 of 6
    "actual_undocumented": (0.50, 0.75),  # 3 of 6; 3 of 4
    "map_untested": (0.92, 0.76),  # 13 of 14; 13 of 17
}
# 26 queries, 25 with a relevant note: 18 found all of theirs and 7 found none; 23 of the 31 notes returned were relevant.
SEARCH_FLOORS = {"recall": 0.72, "precision": 0.74, "reciprocal_rank": 0.72}
STEP = 0.01  # a floor is the measured value cut to this step


# --------------------------------------------------------------------------
# Findings


@dataclass
class Score:
    """Findings of one kind against the list of true gaps of that kind."""

    findings: int = 0
    labels: int = 0
    wrong: list[str] = field(default_factory=list)  # findings that are no true gap
    missed: list[str] = field(default_factory=list)  # true gaps without a finding

    @property
    def precision(self) -> float:
        return (self.findings - len(self.wrong)) / self.findings

    @property
    def recall(self) -> float:
        return (self.labels - len(self.missed)) / self.labels

    def __add__(self, other: "Score") -> "Score":
        return Score(
            self.findings + other.findings, self.labels + other.labels, self.wrong + other.wrong, self.missed + other.missed
        )


def words(text: str) -> str:
    """The text as lower-case words and numbers with one space around each, so
    that punctuation, Markdown marks and line breaks do not count."""
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def same_statement(label: str, found: str) -> bool:
    """A finding is about a listed statement when one holds the other, whole
    words only. A finding may carry more than the statement (a map block with
    its labels) or less (a statement the scanner cut in two)."""
    a, b = words(label), words(found)
    return a in b or b in a


def score(labels: list[dict[str, Any]], found: list[tuple[str, str]], project: str = "") -> Score:
    """`found` is one `(path, text)` per finding; the text is empty for a
    finding about a whole file. A label matches on its path and, when it has
    a statement, on the statement."""

    def match(label: dict[str, Any], path: str, text: str) -> bool:
        return label["path"] == path and ("statement" not in label or same_statement(label["statement"], text))

    result = Score(findings=len(found), labels=len(labels))
    for path, text in found:
        if not any(match(label, path, text) for label in labels):
            result.wrong.append(f"{project}/{path}: {text}".rstrip(": "))
    for label in labels:
        if not any(match(label, path, text) for path, text in found):
            result.missed.append(f"{project}/{label['path']}: {label.get('statement', '')}".rstrip(": "))
    return result


def labels_of(project: str) -> dict[str, Any]:
    return json.loads((MEASURE / f"{project}.labels.json").read_text(encoding="utf-8"))


def everything(fetch: Callable[..., dict[str, Any]], **arguments: Any) -> list[dict[str, Any]]:
    """Every item of a paged result."""
    items: list[dict[str, Any]] = []
    while True:
        result = fetch(**arguments, limit=200, offset=len(items))
        items += result["items"]
        if len(items) >= result["total"] or not result["items"]:
            return items


def findings_of(grove: Grove, project: str, kind: str, root: Path) -> list[tuple[str, str]]:
    """The findings of one kind as `(path, text)`, read the way a client reads them."""
    result = grove.gaps(project, kind=kind)
    assert result["complete"], f"{project}: a cap dropped {kind} findings, so the measure would be partial"
    declared = {item["id"]: item["body"] or item["title"] for item in everything(grove.blueprint_get, project=project, layer="declared")}
    found: list[tuple[str, str]] = []
    for finding in everything(grove.gaps, project=project, kind=kind):
        evidence = finding["evidence"]
        if kind == "actual_undocumented":
            found.append((evidence["paths"][0], ""))
        elif kind == "map_untested":
            found.append((Path(evidence["source_path"]).relative_to(root.resolve()).as_posix(), evidence["text"]))
        else:
            found.append((evidence["source_path"], declared[evidence["item_ids"][0]]))
    return found


def measure_findings(home: Path) -> dict[tuple[str, str], Score]:
    """`(project, kind)` to its score. The three kinds a scan computes are read
    after the scan and before the map is ingested: a map adds declared and
    actual items of its own, and the lists were made from the projects' own
    documents."""
    scores: dict[tuple[str, str], Score] = {}
    with Grove(home) as grove:
        for project in PROJECTS:
            root = MEASURE / project
            labels = labels_of(project)
            grove.project_create(project, str(root))
            grove.scan(project)
            for kind in SCAN_FINDING_KINDS:
                scores[project, kind] = score(labels[kind], findings_of(grove, project, kind, root), project)
            grove.ingest_map(project, str(root / labels["map"]))
            scores[project, "map_untested"] = score(
                labels["map_untested"], findings_of(grove, project, "map_untested", root), project
            )
    return scores


def together(scores: dict[tuple[str, str], Score], kind: str) -> Score:
    return sum((scores[project, kind] for project in PROJECTS), Score())


# --------------------------------------------------------------------------
# Search


@dataclass
class Asked:
    query: str
    relevant: list[str]
    returned: list[str]  # keys, best first, at most TOP

    @property
    def hits(self) -> int:
        return len(set(self.relevant) & set(self.returned))

    @property
    def first_rank(self) -> int:
        """The place of the first relevant note, from 1; 0 when none came back."""
        return next((place for place, key in enumerate(self.returned, 1) if key in self.relevant), 0)


def notes() -> dict[str, tuple[str, str]]:
    """key to (title, body): the key is the file name, the title its first line."""
    found = {}
    for path in sorted(NOTES.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        found[path.stem] = (text.splitlines()[0].lstrip("# ").strip(), text)
    return found


def queries() -> list[dict[str, Any]]:
    return json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]


def measure_search(home: Path) -> list[Asked]:
    """Every query asked of a data directory that holds the notes and nothing else."""
    with Grove(home) as grove:
        for key, (title, body) in notes().items():
            grove.knowledge_write(None, key, title, body)
        return [
            Asked(
                entry["query"],
                entry["relevant"],
                [item["key"] for item in grove.knowledge_search(entry["query"], limit=TOP)["items"]],
            )
            for entry in queries()
        ]


def search_numbers(asked: list[Asked]) -> dict[str, float]:
    """recall: the share of a query's relevant notes in its first ten results,
    averaged over the queries that have a relevant note. reciprocal_rank: one
    over the place of the first relevant note (0 when none), averaged the same
    way. precision: of all the notes returned, for every query, the share that
    was relevant."""
    judged = [entry for entry in asked if entry.relevant]
    returned = sum(len(entry.returned) for entry in asked)
    return {
        "recall": sum(entry.hits / len(entry.relevant) for entry in judged) / len(judged),
        "precision": sum(entry.hits for entry in asked) / returned,
        "reciprocal_rank": sum(1 / entry.first_rank if entry.first_rank else 0.0 for entry in judged) / len(judged),
    }


# --------------------------------------------------------------------------
# Tests


@pytest.fixture(scope="module")
def finding_scores(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str], Score]:
    return measure_findings(tmp_path_factory.mktemp("measure-findings") / "home")


@pytest.fixture(scope="module")
def asked(tmp_path_factory: pytest.TempPathFactory) -> list[Asked]:
    return measure_search(tmp_path_factory.mktemp("measure-search") / "home")


def cut(value: float) -> float:
    """The value cut to two decimals, as a floor is written."""
    return math.floor(value / STEP + 1e-9) * STEP


def test_the_lists_describe_the_corpus() -> None:
    """A label that points at nothing would count as a missed gap for ever."""
    for project in PROJECTS:
        root = MEASURE / project
        labels = labels_of(project)
        assert labels["project"] == project and (root / labels["map"]).is_file()
        assert {key for key, value in labels.items() if isinstance(value, list)} == set(FINDING_KINDS)
        for kind in FINDING_KINDS:
            assert labels[kind], f"{project}: no true gap of kind {kind} is listed"
            for label in labels[kind]:
                assert label["why"].strip(), label
                path = root / label["path"]
                assert path.is_file(), f"{project}: {label['path']} does not exist"
                if kind == "actual_undocumented":
                    assert not is_test_file(label["path"]), label
                    continue
                assert len(words(label["statement"]).split()) >= 3, label
                lines = path.read_text(encoding="utf-8").splitlines()
                nearby = " ".join(lines[label["line"] - 1 : label["line"] + 3])
                assert words(label["statement"]) in words(nearby), f"{project}: not at {label['path']}:{label['line']}: {label['statement']}"
    known = notes()
    assert len(known) >= 12
    listed = queries()
    assert 18 <= len(listed) <= 30, "about twenty queries"
    assert len({entry["query"] for entry in listed}) == len(listed)
    for entry in listed:
        assert set(entry["relevant"]) <= set(known), entry
    assert any(not entry["relevant"] for entry in listed), "one query at least should find nothing"


def test_a_finding_counts_only_for_its_own_statement() -> None:
    """The measure itself: a rule that matched everything would report 1.00 for ever."""
    labels = [
        {"path": "README.md", "statement": "Refuses a box over 150 cm."},
        {"path": "README.md", "statement": "Sends an email."},
    ]
    found = [
        ("README.md", "- Refuses a box over `150 cm` (observed-in-code, untested)"),  # more than the statement
        ("docs/other.md", "Refuses a box over 150 cm."),  # the same words in another file
        ("README.md", "Refuses a boxer over 150 cm."),  # not the same words
        ("README.md", "Thanks to the night shift."),
    ]
    result = score(labels, found, "p")
    assert (result.findings, result.labels) == (4, 2)
    assert result.wrong == ["p/docs/other.md: Refuses a box over 150 cm.", "p/README.md: Refuses a boxer over 150 cm.", "p/README.md: Thanks to the night shift."]
    assert result.missed == ["p/README.md: Sends an email."]
    assert (result.precision, result.recall) == (0.25, 0.5)
    # A finding about a file matches on the path alone.
    files = score([{"path": "src/a.py"}, {"path": "src/b.py"}], [("src/a.py", ""), ("src/c.py", "")], "p")
    assert (files.wrong, files.missed) == (["p/src/c.py"], ["p/src/b.py"])
    assert cut(0.6666) == pytest.approx(0.66) and cut(1.0) == pytest.approx(1.0) and cut(0.29) == pytest.approx(0.29)


@pytest.mark.parametrize("kind", FINDING_KINDS)
def test_precision_and_recall_of_each_finding_kind_hold_their_floor(
    kind: str, finding_scores: dict[tuple[str, str], Score]
) -> None:
    result = together(finding_scores, kind)
    precision, recall = FINDING_FLOORS[kind]
    detail = (
        f"\nfindings that are no true gap ({len(result.wrong)} of {result.findings}):\n  " + "\n  ".join(result.wrong)
        + f"\ntrue gaps without a finding ({len(result.missed)} of {result.labels}):\n  " + "\n  ".join(result.missed)
    )
    assert result.precision >= precision, f"{kind}: precision {result.precision:.3f} is below its floor {precision}{detail}"
    assert result.recall >= recall, f"{kind}: recall {result.recall:.3f} is below its floor {recall}{detail}"


def test_search_holds_its_floor(asked: list[Asked]) -> None:
    numbers = search_numbers(asked)
    detail = "\n" + "\n".join(
        f"  {entry.query!r}: wanted {entry.relevant}, got {entry.returned}"
        for entry in asked
        if set(entry.returned) != set(entry.relevant) or entry.first_rank > 1
    )
    for name, floor in SEARCH_FLOORS.items():
        assert numbers[name] >= floor, f"search {name} {numbers[name]:.3f} is below its floor {floor}{detail}"


def test_no_floor_is_stale(finding_scores: dict[tuple[str, str], Score], asked: list[Asked]) -> None:
    """A number that rose leaves its floor behind, and the next fall back to
    the old value would pass. Raise the floor in the change that raised the
    number, and record the new numbers with a date."""
    measured = {f"search {name}": (value, SEARCH_FLOORS[name]) for name, value in search_numbers(asked).items()}
    for kind in FINDING_KINDS:
        result = together(finding_scores, kind)
        measured[f"{kind} precision"] = (result.precision, FINDING_FLOORS[kind][0])
        measured[f"{kind} recall"] = (result.recall, FINDING_FLOORS[kind][1])
    stale = [
        f"{name}: measured {value:.3f}, floor {floor}; write {cut(value):.2f}"
        for name, (value, floor) in measured.items()
        if cut(value) > floor + 1e-9
    ]
    assert not stale, "floors below today's numbers (see the top of this file):\n  " + "\n  ".join(stale)


# --------------------------------------------------------------------------
# The numbers, printed


def report() -> str:
    """Today's numbers as the tables the documents hold, then what is behind them."""
    with tempfile.TemporaryDirectory() as directory:
        scores = measure_findings(Path(directory) / "findings")
        asked = measure_search(Path(directory) / "search")
    lines = ["| Kind | True gaps | Findings | Right | Precision | Recall |", "|---|---|---|---|---|---|"]
    for kind in FINDING_KINDS:
        result = together(scores, kind)
        right = result.findings - len(result.wrong)
        found = result.labels - len(result.missed)
        lines.append(
            f"| `{kind}` | {result.labels} | {result.findings} | {right} | "
            f"{right}/{result.findings} = {result.precision:.3f} | {found}/{result.labels} = {result.recall:.3f} |"
        )
    lines += ["", "| Project | Kind | True gaps | Findings | Right | Gaps found |", "|---|---|---|---|---|---|"]
    for project in PROJECTS:
        for kind in FINDING_KINDS:
            result = scores[project, kind]
            lines.append(
                f"| {project} | `{kind}` | {result.labels} | {result.findings} | "
                f"{result.findings - len(result.wrong)} | {result.labels - len(result.missed)} |"
            )
    numbers = search_numbers(asked)
    judged = [entry for entry in asked if entry.relevant]
    lines += [
        "",
        f"search, first {TOP} results, {len(asked)} queries ({len(judged)} with a relevant note), {len(notes())} notes:",
        f"  recall {numbers['recall']:.3f}  precision {numbers['precision']:.3f}  reciprocal rank {numbers['reciprocal_rank']:.3f}",
        f"  queries that found every relevant note: {sum(entry.hits == len(entry.relevant) for entry in judged)} of {len(judged)}",
        f"  queries that found none: {sum(entry.hits == 0 for entry in judged)} of {len(judged)}",
        f"  queries that should find nothing and found something: {sum(bool(entry.returned) for entry in asked if not entry.relevant)}",
        "",
    ]
    for kind in FINDING_KINDS:
        result = together(scores, kind)
        lines += [f"{kind}: findings that are no true gap"] + [f"  {entry}" for entry in result.wrong]
        lines += [f"{kind}: true gaps without a finding"] + [f"  {entry}" for entry in result.missed]
    lines.append("search: each query, the place of the first relevant note, what came back")
    for entry in asked:
        lines.append(f"  {entry.query!r}: place {entry.first_rank or '-'}; wanted {entry.relevant}; got {entry.returned}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.write(report() + "\n")
