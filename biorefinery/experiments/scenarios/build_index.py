"""Build a CSV index of legacy initialization JSON files.

Scans for *_initialization.json files in selected source folders and produces
`index.csv` with columns: filename,relative_path,category,purpose,notes

Heuristics applied to categorize:
 - If 'validation' in name -> purpose=validation
 - If 'feas' in name or 'feasibility' -> purpose=feasibility
 - If 'final' or 'optimal' or 'best' -> purpose=final
 - Else -> purpose=unsorted

Category guesses (editable):
 - fermentation / hydrolisis / distillation / scheduling / mixed
Determined by substring presence.

This is a first pass; user can manually refine index.csv.
"""
from __future__ import annotations
import csv
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[3]
OUTPUT = pathlib.Path(__file__).parent / "index.csv"

SOURCE_DIRS = [
    REPO / "biorefinery_models",
    REPO / "functions",
]

CATEGORY_PATTERNS = [
    (re.compile(r"hydro|hydrol"), "hydrolisis"),
    (re.compile(r"ferm"), "fermentation"),
    (re.compile(r"distill"), "distillation"),
    (re.compile(r"sched"), "scheduling"),
]

PURPOSE_RULES = [
    (re.compile(r"validation"), "validation"),
    (re.compile(r"feas"), "feasibility"),
    (re.compile(r"final|best|optimal"), "final"),
]


def guess_category(name: str) -> str:
    hits = {label for pattern, label in CATEGORY_PATTERNS if pattern.search(name)}
    if not hits:
        return "unspecified"
    if len(hits) == 1:
        return hits.pop()
    return "+".join(sorted(hits))


def guess_purpose(name: str) -> str:
    for pattern, label in PURPOSE_RULES:
        if pattern.search(name):
            return label
    return "unsorted"


def main():
    rows = []
    for base in SOURCE_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*_initialization.json"):
            rel = path.relative_to(REPO)
            name = path.name.lower()
            category = guess_category(name)
            purpose = guess_purpose(name)
            rows.append({
                "filename": path.name,
                "relative_path": str(rel),
                "category": category,
                "purpose": purpose,
                "notes": "",
            })
    rows.sort(key=lambda r: (r["category"], r["purpose"], r["filename"]))
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filename","relative_path","category","purpose","notes"])
        w.writeheader()
        w.writerows(rows)
    print(f"Index written to {OUTPUT} with {len(rows)} entries")


if __name__ == "__main__":  # pragma: no cover
    main()
