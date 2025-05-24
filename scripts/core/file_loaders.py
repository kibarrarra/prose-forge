"""
file_loaders.py - File loading and text processing utilities

This module handles:
- Loading version texts from various directory structures
- Loading original source texts for fidelity comparison
- Managing voice specifications and metadata
- Directory traversal and file discovery
"""

import pathlib
from typing import Dict, List, Tuple
from utils.io_helpers import read_utf8
from utils.paths import ROOT, CTX_DIR
from utils.logging_helper import get_logger

log = get_logger()

def load_version_text(version: str, chapter: str) -> Tuple[str, str]:
    """Load chapter text and voice spec for a given version."""
    # Check if this is a final version
    if not any(c.isdigit() for c in version):
        path = ROOT / "drafts" / "auditions" / version / "final" / f"{chapter}.txt"
        spec_path = ROOT / "drafts" / "auditions" / version / "final" / "voice_spec.md"
        
        # Fall back to old path structure if files don't exist
        if not path.exists():
            path = ROOT / "drafts" / "final" / version / f"{chapter}.txt"
            spec_path = ROOT / "drafts" / "final" / version / "voice_spec.md"
    else:
        # Parse audition round
        if "_" in version:
            persona, round_num = version.rsplit("_", 1)
            # Check new structure first (auditions/persona/round_N/)
            path = ROOT / "drafts" / "auditions" / persona / f"round_{round_num}" / f"{chapter}.txt"
            spec_path = ROOT / "drafts" / "auditions" / persona / f"round_{round_num}" / "voice_spec.md"
            
            # Fall back to old structure if files don't exist
            if not path.exists():
                path = ROOT / "drafts" / "auditions" / f"{persona}_{round_num}" / f"{chapter}.txt"
                spec_path = ROOT / "drafts" / "auditions" / f"{persona}_{round_num}" / "voice_spec.md"
        else:
            raise ValueError(f"Invalid version format: {version}")
    
    if not path.exists():
        raise ValueError(f"Version {version} not found for chapter {chapter} at {path}")
    
    return read_utf8(path), read_utf8(spec_path)

def load_texts_from_dir(directory: pathlib.Path) -> List[Tuple[str, str, str]]:
    """Load all text files and voice spec from a directory.
    Returns a list of (chapter_id, chapter_text, voice_spec) tuples.
    """
    directory = pathlib.Path(directory)
    if not directory.exists():
        raise ValueError(f"Directory not found: {directory}")
    
    # Find voice spec file
    spec_path = directory / "voice_spec.md"
    if not spec_path.exists():
        log.warning(f"Voice spec not found in {directory}, using empty spec")
        voice_spec = ""
    else:
        voice_spec = read_utf8(spec_path)
    
    # Find all text files (assuming they're chapter files)
    results = []
    for text_file in directory.glob("*.txt"):
        # Skip files that aren't likely chapters
        if text_file.name == "voice_spec.md" or "editor" in text_file.name or "sanity" in text_file.name:
            continue
        
        chapter_id = text_file.stem
        chapter_text = read_utf8(text_file)
        results.append((chapter_id, chapter_text, voice_spec))
    
    if not results:
        raise ValueError(f"No text files found in {directory}")
    
    return results

def load_original_text(chapter_id: str) -> str:
    """Return raw source text for *chapter_id* if available."""
    path = CTX_DIR / f"{chapter_id}.txt"
    if not path.exists():
        log.warning(f"Context not found for {chapter_id} at {path}")
        return ""
    return read_utf8(path)

def gather_final_versions(
    root_dir: pathlib.Path = ROOT / "drafts" / "auditions"
) -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Gather all final versions of chapters from experiment directories.
    
    Args:
        root_dir: Root directory where experiment audition folders are located
        
    Returns:
        Dictionary mapping chapter IDs to lists of (persona_name, chapter_text, voice_spec) tuples
    """
    # Organize by chapter for easy comparison
    chapters: Dict[str, List[Tuple[str, str, str]]] = {}
    
    # Walk through all audition directories
    for persona_dir in root_dir.iterdir():
        if not persona_dir.is_dir():
            continue
            
        final_dir = persona_dir / "final"
        if not final_dir.exists() or not final_dir.is_dir():
            continue
            
        # Look for voice spec in final directory
        spec_path = final_dir / "voice_spec.md"
        if spec_path.exists():
            voice_spec = read_utf8(spec_path)
        else:
            log.warning(f"Voice spec not found in {final_dir}, using empty spec")
            voice_spec = ""
            
        # Find all chapter files in final directory
        for chapter_file in final_dir.glob("*.txt"):
            # Skip non-chapter files
            if "editor" in chapter_file.name or "sanity" in chapter_file.name:
                continue
                
            chapter_id = chapter_file.stem
            chapter_text = read_utf8(chapter_file)
            
            # Organize by chapter
            if chapter_id not in chapters:
                chapters[chapter_id] = []
                
            chapters[chapter_id].append((persona_dir.name, chapter_text, voice_spec))
    
    return chapters 