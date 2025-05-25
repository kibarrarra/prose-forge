import os
import sys
import importlib
from pathlib import Path

import pytest

# Ensure the project root is on the import path so ``scripts`` can be imported
root_path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(root_path / "scripts"))


def build_project_structure(root: Path) -> None:
    """Create a minimal drafts/auditions/<persona>/final structure."""
    hero_final = root / "drafts" / "auditions" / "hero" / "final"
    hero_final.mkdir(parents=True, exist_ok=True)
    (hero_final / "voice_spec.md").write_text("Hero Spec", encoding="utf-8")
    (hero_final / "chapter1.txt").write_text("Hero Text 1", encoding="utf-8")
    (hero_final / "chapter2.txt").write_text("Hero Text 2", encoding="utf-8")

    villain_final = root / "drafts" / "auditions" / "villain" / "final"
    villain_final.mkdir(parents=True, exist_ok=True)
    (villain_final / "voice_spec.md").write_text("Villain Spec", encoding="utf-8")
    (villain_final / "chapter1.txt").write_text("Villain Text 1", encoding="utf-8")


@pytest.fixture()
def file_loaders(tmp_path, monkeypatch):
    monkeypatch.setenv("PROSE_FORGE_ROOT", str(tmp_path))
    build_project_structure(tmp_path)

    paths = importlib.reload(importlib.import_module("scripts.utils.paths"))
    loaders = importlib.reload(importlib.import_module("scripts.core.file_loaders"))
    return loaders


def test_load_version_text(file_loaders):
    text, spec = file_loaders.load_version_text("hero", "chapter1")
    assert text == "Hero Text 1"
    assert spec == "Hero Spec"


def test_load_texts_from_dir(file_loaders, tmp_path):
    root = Path(os.environ["PROSE_FORGE_ROOT"])
    final_dir = root / "drafts" / "auditions" / "hero" / "final"
    results = file_loaders.load_texts_from_dir(final_dir)
    assert len(results) == 2
    results = sorted(results, key=lambda r: r[0])
    assert results[0] == ("chapter1", "Hero Text 1", "Hero Spec")
    assert results[1] == ("chapter2", "Hero Text 2", "Hero Spec")


def test_gather_final_versions(file_loaders):
    chapters = file_loaders.gather_final_versions()
    assert set(chapters.keys()) == {"chapter1", "chapter2"}

    ch1 = sorted(chapters["chapter1"])  # order not guaranteed
    expected_ch1 = sorted([
        ("hero", "Hero Text 1", "Hero Spec"),
        ("villain", "Villain Text 1", "Villain Spec"),
    ])
    assert ch1 == expected_ch1

    assert chapters["chapter2"] == [("hero", "Hero Text 2", "Hero Spec")]
