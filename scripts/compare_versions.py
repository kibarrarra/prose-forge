#!/usr/bin/env python
"""
compare_versions.py – Compare multiple versions of chapters across authors/rounds

Usage:
    python scripts/compare_versions.py lotm_0001 lotm_0002 --versions cosmic_clarity_1 cosmic_clarity_3 lovecraft_2
    python scripts/compare_versions.py lotm_0001 --final-versions cosmic_clarity lovecraft
"""

import argparse, json, pathlib, textwrap, os
from utils.io_helpers import read_utf8, write_utf8
from utils.paths import ROOT, VOICE_DIR, CTX_DIR
from utils.logging_helper import get_logger
from utils.openai_client import get_openai_client

import tiktoken

log = get_logger()
MODEL = "gpt-4o-mini"   # cheap for discussion

client = get_openai_client()

def load_version_text(version: str, chapter: str) -> tuple[str, str]:
    """Load chapter text and voice spec for a given version."""
    # Check if this is a final version
    if not any(c.isdigit() for c in version):
        path = ROOT / "drafts" / "final" / version / f"{chapter}.txt"
        spec_path = ROOT / "drafts" / "final" / version / "voice_spec.md"
    else:
        # Parse audition round
        persona, round_num = version.rsplit("_", 1)
        path = ROOT / "drafts" / "auditions" / f"{persona}_{round_num}" / f"{chapter}.txt"
        spec_path = ROOT / "drafts" / "auditions" / f"{persona}_{round_num}" / "voice_spec.md"
    
    if not path.exists():
        raise ValueError(f"Version {version} not found for chapter {chapter}")
    
    return read_utf8(path), read_utf8(spec_path)

def chat(system: str, user: str) -> str:
    res = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}]
    )
    return res.choices[0].message.content.strip()

def compare_versions(chapters: list[str], versions: list[str]) -> dict:
    """Compare multiple versions of chapters and return critic feedback."""
    # Load all versions
    version_texts = {}
    for version in versions:
        version_texts[version] = []
        for chapter in chapters:
            text, spec = load_version_text(version, chapter)
            version_texts[version].append((chapter, text, spec))
    
    # Build comparison prompt
    comparison = []
    for version, texts in version_texts.items():
        version_comparison = [f"Version: {version}"]
        for chapter, text, spec in texts:
            version_comparison.append(f"\nChapter: {chapter}")
            version_comparison.append(f"Voice Spec:\n{spec}")
            version_comparison.append(f"Text:\n{text}")
        comparison.append("\n".join(version_comparison))
    
    comparison_text = "\n\n---\n\n".join(comparison)
    
    # Get critic feedback
    rubric = textwrap.dedent("""
        Compare these versions on:
        1. Clarity and readability (1-10)
        2. Tone and atmosphere (1-10)
        3. Consistency with voice spec (1-10)
        4. Overall effectiveness (1-10)
        
        For each version:
        - Provide specific scores
        - Highlight strengths and weaknesses
        - Suggest improvements
        - Note any particularly effective elements
        
        End with a summary of which version works best overall and why.
    """)
    
    critic_A = chat("You are Critic A, focused on technical writing quality and clarity.", 
                   f"{rubric}\n\n{comparison_text}")
    critic_B = chat("You are Critic B, focused on creative writing and atmosphere.",
                   f"{rubric}\n\n{comparison_text}")
    
    discussion = chat(
        "You are Critic A and Critic B in turn. Hold up to 3 back-and-forths. "
        "End with a clear recommendation of which version works best and why.",
        f"CRITIC A:\n{critic_A}\n\nCRITIC B:\n{critic_B}"
    )
    
    return {
        "critic_A_summary": critic_A,
        "critic_B_summary": critic_B,
        "discussion_transcript": discussion,
        "versions": versions,
        "chapters": chapters
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters", nargs="+", help="Chapter IDs to compare (e.g. lotm_0001)")
    ap.add_argument("--versions", nargs="+", help="Specific versions to compare (e.g. cosmic_clarity_1 cosmic_clarity_3)")
    ap.add_argument("--final-versions", nargs="+", help="Compare final versions of these personae")
    args = ap.parse_args()
    
    if not args.versions and not args.final_versions:
        print("Error: Must specify either --versions or --final-versions")
        sys.exit(1)
    
    versions = args.versions or args.final_versions
    
    # Create output directory
    out_dir = ROOT / "drafts" / "comparisons"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate comparison
    result = compare_versions(args.chapters, versions)
    
    # Save results
    version_str = "_".join(versions)
    chapter_str = "_".join(args.chapters)
    out_path = out_dir / f"compare_{version_str}_{chapter_str}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Comparison saved → %s", out_path)

if __name__ == "__main__":
    main() 