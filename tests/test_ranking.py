import json
import site
import sys
from pathlib import Path
import pytest

# Ensure packages installed in the local virtualenv are available
repo_root = Path(__file__).resolve().parents[1]
venv_site = repo_root / ".venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
if venv_site.exists():
    site.addsitedir(str(venv_site))

# Ensure project root itself is importable so the "scripts" package can be found
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "scripts"))

from scripts.core.elo_ranking import rank_chapter_versions, smart_rank_chapter_versions
from scripts.utils.llm_client import _StubClient

# Pre-crafted JSON the stub LLM will return
FIXED_JSON = {
    "table": [
        {"rank": 1, "id": "DRAFT_A", "clarity": 9, "tone": 8, "plot_fidelity": 9, "tone_fidelity": 8, "overall": 9},
        {"rank": 2, "id": "DRAFT_B", "clarity": 8, "tone": 7, "plot_fidelity": 8, "tone_fidelity": 7, "overall": 8}
    ],
    "analysis": "A wins",
    "feedback": {"DRAFT_B": "Needs work"}
}

# Wrap JSON in a code block like the real model would
RESPONSE_TEXT = "Discussion...\n```json\n" + json.dumps(FIXED_JSON) + "\n```"


def stub_client():
    """Return a client whose create() always yields RESPONSE_TEXT."""
    return _StubClient(RESPONSE_TEXT)


def patch_client(monkeypatch):
    stub = lambda test_mode=None: stub_client()
    monkeypatch.setattr("scripts.utils.llm_client.get_llm_client", stub)
    # Also patch the already-imported reference inside elo_ranking
    monkeypatch.setattr("scripts.core.elo_ranking.get_llm_client", stub)


def test_rank_chapter_versions(monkeypatch):
    patch_client(monkeypatch)
    result = rank_chapter_versions(
        "chapter1",
        [("A", "text A", ""), ("B", "text B", "")],
    )
    assert result["table"][0]["persona"] == "A"
    assert result["table"][1]["persona"] == "B"
    assert result["table"][0]["rank"] == 1
    assert result["analysis"] == "A wins"


def test_smart_rank_chapter_versions(monkeypatch):
    patch_client(monkeypatch)
    result = smart_rank_chapter_versions(
        "chapter1",
        [("A", "text A", ""), ("B", "text B", "")],
        initial_runs=1,
        top_candidates=2,
        temperature=0.1,
    )
    table = result["table"]
    assert len(table) == 2
    assert table[0]["rank"] == 1
    assert table[0]["persona"] == "A"
