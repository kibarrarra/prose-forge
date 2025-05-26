"""
file_helpers.py - Common file and path utilities

Provides utilities for finding chapters, validating paths, and
other file operations commonly used across scripts.
"""

import pathlib
from typing import Dict, List, Optional, Tuple
from .paths import RAW_DIR, SEG_DIR, CTX_DIR
from .logging_helper import get_logger

log = get_logger()


def validate_paths(paths: Dict[str, pathlib.Path]) -> List[str]:
    """Validate that all required paths exist.
    
    Args:
        paths: Dictionary mapping description to path
        
    Returns:
        List of missing file descriptions
    """
    missing = []
    for desc, path in paths.items():
        if not path.exists():
            missing.append(f"{desc}: {path}")
    return missing


def find_chapter_source(chapter: str) -> Optional[pathlib.Path]:
    """Find the source file for a chapter.
    
    Checks in order: raw directory, segments directory, context directory
    
    Args:
        chapter: Chapter name/ID
        
    Returns:
        Path to chapter source or None if not found
    """
    # Check raw directory first (preferred)
    for ext in ['.json', '.txt']:
        path = RAW_DIR / f"{chapter}{ext}"
        if path.exists():
            return path
    
    # Check segments directory
    segment_files = list(SEG_DIR.glob(f"{chapter}_p*.txt"))
    if segment_files:
        return segment_files[0].parent  # Return directory
    
    # Check context directory
    ctx_path = CTX_DIR / f"{chapter}.txt"
    if ctx_path.exists():
        return ctx_path
    
    return None


def find_editor_feedback(round_dir: pathlib.Path, round_num: int) -> Optional[pathlib.Path]:
    """Find editor feedback file in a round directory.
    
    Args:
        round_dir: Directory to search
        round_num: Round number for standard naming
        
    Returns:
        Path to feedback file or None
    """
    # Try standard naming first
    standard_path = round_dir / f"editor_round{round_num}.json"
    if standard_path.exists():
        return standard_path
    
    # Look for any editor feedback files
    editor_files = list(round_dir.glob("editor_*.json"))
    if editor_files:
        log.info(f"Using alternate feedback file: {editor_files[0]}")
        return editor_files[0]
    
    return None


def gather_chapter_files(chapter_id: str, pattern: str = "*.txt") -> List[pathlib.Path]:
    """Gather all files for a chapter matching a pattern.
    
    Args:
        chapter_id: Chapter ID to search for
        pattern: Glob pattern for files (default: "*.txt")
        
    Returns:
        List of paths to chapter files
    """
    files = []
    
    # Check raw directory
    raw_pattern = f"{chapter_id}*"
    files.extend(RAW_DIR.glob(raw_pattern))
    
    # Check segments
    seg_pattern = f"{chapter_id}_p*{pattern}"
    files.extend(SEG_DIR.glob(seg_pattern))
    
    # Check context
    ctx_file = CTX_DIR / f"{chapter_id}.txt"
    if ctx_file.exists():
        files.append(ctx_file)
    
    return sorted(files)


def resolve_draft_path(
    chapter_id: str,
    persona: str,
    version: Optional[int] = None,
    sample: bool = False,
    audition_dir: Optional[pathlib.Path] = None
) -> pathlib.Path:
    """Resolve the path for a draft file.
    
    Args:
        chapter_id: Chapter ID
        persona: Persona/experiment name
        version: Version number (None for latest)
        sample: Whether this is a sample draft
        audition_dir: Audition directory override
        
    Returns:
        Path to the draft file
    """
    if audition_dir:
        # Audition mode uses simple chapter ID as filename
        return audition_dir / f"{chapter_id}.txt"
    
    # Standard draft directory structure
    from .paths import DRAFT_DIR
    draft_dir = DRAFT_DIR / chapter_id
    
    if version is None:
        # Find latest version
        tag = "_sample" if sample else ""
        drafts = sorted(draft_dir.glob(f"{persona}{tag}_v*.txt"))
        if not drafts:
            version = 1
        else:
            import re
            version = int(re.search(r"_v(\d+)", drafts[-1].stem)[1])
    
    tag = "_sample" if sample else ""
    return draft_dir / f"{persona}{tag}_v{version}.txt"


def extract_chapter_metadata(path: pathlib.Path) -> Dict[str, str]:
    """Extract metadata from a chapter file path.
    
    Args:
        path: Path to analyze
        
    Returns:
        Dictionary with keys: chapter_id, persona, version, type
    """
    import re
    
    metadata = {
        "chapter_id": "",
        "persona": "",
        "version": "",
        "type": "unknown"
    }
    
    stem = path.stem
    
    # Try to parse as a draft file (e.g., cosmic_clarity_v2, lovecraft_sample_v1)
    draft_match = re.match(r"^(.+?)(?:_sample)?_v(\d+)$", stem)
    if draft_match:
        metadata["persona"] = draft_match.group(1)
        metadata["version"] = draft_match.group(2)
        metadata["type"] = "draft"
        # Chapter ID comes from parent directory name
        metadata["chapter_id"] = path.parent.name
        return metadata
    
    # Otherwise assume it's a chapter source file
    metadata["chapter_id"] = stem
    metadata["type"] = "source"
    
    return metadata 