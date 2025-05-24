#!/usr/bin/env python
"""Pairwise Elo ranking for chapter drafts.

This helper compares each pair of drafts using
``rank_chapter_versions`` and aggregates the results
via a simple Elo system. It can operate on arbitrary
directories containing ``<chapter>.txt`` and an optional
``voice_spec.md``.
"""

from __future__ import annotations

import argparse
import pathlib
from typing import List, Tuple, Dict

from utils.io_helpers import read_utf8
from utils.logging_helper import get_logger
from utils.llm_client import get_llm_client

# Reuse existing ranking helper

from compare_versions import rank_chapter_versions, load_original_text

log = get_logger()
client = get_llm_client()


class Elo:
    """Minimal Elo rating tracker."""

    def __init__(self, k: float = 20.0, base: float = 1000.0) -> None:
        self.k = k
        self.base = base
        self._ratings: Dict[str, float] = {}

    def rating(self, name: str) -> float:
        return self._ratings.get(name, self.base)

    def _expect(self, ra: float, rb: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))

    def update(self, winner: str, loser: str) -> None:
        ra, rb = self.rating(winner), self.rating(loser)
        ea = self._expect(ra, rb)
        eb = 1.0 - ea
        self._ratings[winner] = ra + self.k * (1.0 - ea)
        self._ratings[loser] = rb + self.k * (0.0 - eb)

    def leaderboard(self) -> List[Tuple[str, float]]:
        return sorted(self._ratings.items(), key=lambda x: x[1], reverse=True)


def load_draft(directory: pathlib.Path, chapter: str) -> Tuple[str, str, str]:
    """Return (name, text, voice_spec) for a draft directory."""
    text_path = directory / f"{chapter}.txt"
    if not text_path.exists():
        raise FileNotFoundError(f"{text_path} not found")
    spec_path = directory / "voice_spec.md"
    spec = read_utf8(spec_path) if spec_path.exists() else ""
    text = read_utf8(text_path)
    return directory.name, text, spec


def judge_pair(chapter: str, a: Tuple[str, str, str], b: Tuple[str, str, str]) -> str:
    """Return the winner's persona name from a pairwise comparison."""
    raw = load_original_text(chapter)
    result = rank_chapter_versions(chapter, [a, b], original_text=raw)
    table = result.get("table", [])
    if not table:
        # Fallback: pick left draft
        log.warning("Ranking failed for %s vs %s; defaulting to first", a[0], b[0])
        return a[0]
    table.sort(key=lambda x: x.get("rank", 0))
    top_id = table[0].get("id", "")
    winner = top_id.replace("DRAFT_", "")
    return winner


def pairwise_elo(chapter: str, drafts: List[Tuple[str, str, str]], repeats: int = 1) -> Elo:
    elo = Elo()
    n = len(drafts)
    for i in range(n):
        for j in range(i + 1, n):
            for r in range(repeats):
                first, second = drafts[i], drafts[j]
                if r % 2 == 1:
                    first, second = second, first
                winner = judge_pair(chapter, first, second)
                if winner == first[0]:
                    elo.update(first[0], second[0])
                else:
                    elo.update(second[0], first[0])
    return elo


def generate_html(chapter: str, elo: Elo) -> str:
    rows = []
    for rank, (name, rating) in enumerate(elo.leaderboard(), 1):
        rows.append(f"<tr><td>{rank}</td><td>{name}</td><td>{rating:.1f}</td></tr>")
    rows_text = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='UTF-8'>
<title>Pairwise Elo Ranking</title>
<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css' rel='stylesheet'>
</head>
<body>
<div class='container'>
<h1>Elo Ranking for {chapter}</h1>
<table class='table table-striped'><thead><tr><th>Rank</th><th>Version</th><th>Elo</th></tr></thead><tbody>
{rows_text}
</tbody></table>
</div>
</body>
</html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Pairwise Elo ranking")
    ap.add_argument("chapter", help="Chapter ID (e.g. lotm_0001)")
    ap.add_argument("--draft-dirs", nargs="+", required=True, help="Directories containing draft texts")
    ap.add_argument("--output", required=True, help="Output HTML file")
    ap.add_argument("--repeats", type=int, default=1, help="Left/right swaps per pair")
    args = ap.parse_args()

    drafts = [load_draft(pathlib.Path(d), args.chapter) for d in args.draft_dirs]
    elo = pairwise_elo(args.chapter, drafts, repeats=args.repeats)
    html = generate_html(args.chapter, elo)

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    log.info("Saved ranking → %s", out_path)


if __name__ == "__main__":
    main()
