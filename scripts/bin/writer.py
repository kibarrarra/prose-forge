#!/usr/bin/env python
"""
writer.py - Create or revise a chapter draft according to voice_spec.md.

Core modes
──────────
1. First draft            $ writer.py lotm_0006
2. Audition (first 2k w)  $ writer.py lotm_0001 --sample 2000 --persona lovecraft
3. Revision pass          $ writer.py lotm_0006 --revise notes/lotm_0006.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import os

print("Writer.py script loaded")

# Add project root to path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from scripts.utils.paths import RAW_DIR, SEG_DIR, CTX_DIR, DRAFT_DIR, CONFIG_DIR
from scripts.utils.io_helpers import read_utf8, write_utf8
from scripts.utils.logging_helper import get_logger
from scripts.utils.file_helpers import find_chapter_source, resolve_draft_path
from scripts.core.writing import PromptBuilder, DraftWriter, RevisionHandler, SourceLoader

# ── logging setup ────────────────────────────────────────────────────────────
log = get_logger()

# ── utilities ────────────────────────────────────────────────────────────────
def die(msg: str) -> None:
    """Log error and exit with failure status."""
    log.error(msg)
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)

def resolve_chapter(arg: str) -> pathlib.Path:
    """Resolve chapter argument to a path."""
    p = pathlib.Path(arg)
    if p.exists():
        return p
    
    # Check if it's a known chapter ID
    source_path = find_chapter_source(arg)
    if source_path:
        # Return a stub path with the chapter ID as stem
        return pathlib.Path(f"{arg}.stub")
    
    # Try as raw JSON
    if (RAW_DIR / f"{arg}.json").exists():
        return RAW_DIR / f"{arg}.json"
    
    die(f"Cannot locate chapter '{arg}'.")

# ── main actions ────────────────────────────────────────────────────────────
def make_first_draft(text: str, chap_id: str, args, voice_spec: str,
                     prev_final: str | None, source_loader: SourceLoader) -> pathlib.Path:
    """Create a first draft using the DraftWriter."""
    
    # Initialize draft writer
    test_mode = bool(os.getenv("PF_TEST_MODE"))
    draft_writer = DraftWriter(source_loader, test_mode=test_mode)
    
    # Determine output path first to get the folder
    if args.audition_dir:
        folder = args.audition_dir
        path = folder / f"{chap_id}.txt"
    else:
        # Regular mode uses the chapter directory
        folder = DRAFT_DIR / chap_id
        folder.mkdir(parents=True, exist_ok=True)
        
        # Find next version number
        version = 1
        if not args.sample:
            # Look for existing drafts
            import re
            existing = sorted(folder.glob(f"{args.persona}_v*.txt"))
            if existing:
                last_version = int(re.search(r"_v(\d+)", existing[-1].stem)[1])
                version = last_version + 1
        
        tag = "_sample" if args.sample else ""
        path = folder / f"{args.persona}{tag}_v{version}.txt"
    
    # Create the draft with output directory for prompt logging
    draft = draft_writer.create_first_draft(
        text=text,
        chap_id=chap_id,
        voice_spec=voice_spec,
        persona=args.persona,
        prev_final=prev_final,
        target_words=args.target_words,
        target_ratio=args.target_ratio,
        sample_words=args.sample,
        segmented=args.segmented_first_draft,
        chunk_size=args.chunk_size or 250,
        model=args.model,
        temperature=args.temperature,
        output_dir=folder  # Pass the output folder for prompt logging
    )
    
    # Write the draft
    log.info(f"About to write draft to {path}, draft length: {len(draft)} chars")
    write_utf8(path, draft)
    log.info(f"Draft written successfully to {path}")
    return path

def make_revision(chap_id: str, args, voice_spec: str, 
                  source_loader: SourceLoader) -> pathlib.Path:
    """Create a revision using the RevisionHandler."""
    
    if not args.critic_feedback or not args.critic_feedback.exists():
        die("Revision mode requires --critic-feedback JSON file produced by editor_panel.")
    
    # Initialize revision handler
    test_mode = bool(os.getenv("PF_TEST_MODE"))
    revision_handler = RevisionHandler(source_loader, test_mode=test_mode)
    
    # Load feedback
    try:
        feedback = revision_handler.load_feedback(args.critic_feedback)
    except ValueError as e:
        die(str(e))
    
    # Determine current draft location
    if args.audition_dir:
        # In audition mode, use the previous draft from --prev
        if not args.prev or not args.prev.exists():
            die(f"Revision in audition mode requires a valid --prev file.")
        current = read_utf8(args.prev)
        output_path = args.audition_dir / f"{chap_id}.txt"
    else:
        # Standard mode - find latest draft
        folder = DRAFT_DIR / chap_id
        
        # Find latest version
        import re
        tag = "_sample" if args.sample else ""
        drafts = sorted(folder.glob(f"{args.persona}{tag}_v*.txt"))
        if not drafts:
            die("No existing draft to revise.")
        
        current_path = drafts[-1]
        current = read_utf8(current_path)
        
        # Next version
        v_now = int(re.search(r"_v(\d+)", current_path.stem)[1])
        output_path = folder / f"{args.persona}{tag}_v{v_now + 1}.txt"
    
    # Apply revision
    revised_draft = revision_handler.revise_draft(
        current_draft=current,
        feedback=feedback,
        voice_spec=voice_spec,
        chap_id=chap_id,
        model=args.model,
        temperature=args.temperature
    )
    
    # Validate revision (optional logging)
    if not args.audition_dir:  # Skip validation in audition mode
        validation = revision_handler.validate_revision(current, revised_draft, feedback)
        if validation["warnings"]:
            for warning in validation["warnings"]:
                log.warning(f"Revision validation: {warning}")
    
    # Write revised draft
    write_utf8(output_path, revised_draft)
    return output_path

# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create or revise chapter drafts using voice specifications."
    )
    p.add_argument("chapter", help="Chapter id (lotm_0006) or path to JSON/TXT")
    p.add_argument("--spec", type=pathlib.Path, required=True,
                   help="Voice spec markdown file")
    p.add_argument("--persona", help="Persona label for auditions")
    p.add_argument("--sample", type=int,
                   help="Use only first N words of RAW SOURCE")
    p.add_argument("--target-words", type=int,
                   help="Target word count (overrides --target-ratio)")
    p.add_argument("--target-ratio", type=float, default=1.0,
                   help="Target length as ratio of source (default: 1.0)")
    p.add_argument("--prev", type=pathlib.Path, 
                   help="Previous locked chapter for consistency")
    p.add_argument("--audition-dir", type=pathlib.Path,
                   help="Directory for audition drafts")
    p.add_argument("--critic-feedback", type=pathlib.Path,
                   help="JSON file containing critic feedback for revision")
    p.add_argument("--model", type=str, 
                   default=os.getenv("WRITER_MODEL", "claude-opus-4-20250514"),
                   help="LLM model name to use")
    p.add_argument("--segmented-first-draft", action="store_true",
                   help="Enable segmented first draft mode")
    p.add_argument("--chunk-size", type=int,
                   help="Chunk size for segmented first draft mode")
    p.add_argument("--temperature", type=float, default=0.7,
                   help="Temperature for LLM generation (default: 0.7)")
    return p.parse_args()

def main() -> None:
    print("Starting writer.py...")
    args = parse_args()
    print(f"Args parsed: {args}")
    
    # Basic validation
    if not args.persona and not args.audition_dir:
        die("Either --persona or --audition-dir is required")
    
    # If audition-dir is provided, extract persona from directory name
    if args.audition_dir and not args.persona:
        args.persona = args.audition_dir.name
    
    # Initialize source loader
    source_loader = SourceLoader(RAW_DIR, SEG_DIR, CTX_DIR)
    
    # Resolve chapter and load text
    chap_path = resolve_chapter(args.chapter)
    raw_text, chap_id = source_loader.load_raw_text(chap_path)
    
    log.info("Writer args: critic_feedback=%s, prev=%s", 
             args.critic_feedback, args.prev)
    
    # Load voice spec
    if not args.spec.exists():
        die(f"Voice spec not found: {args.spec}")
    voice_spec = read_utf8(args.spec)
    
    # Load previous final if provided
    prev_final = read_utf8(args.prev) if args.prev and args.prev.exists() else None
    
    # Determine mode and execute
    if args.critic_feedback:
        # Revision mode
        out = make_revision(chap_id, args, voice_spec, source_loader)
        log.info("✔ revision → %s", out)
    else:
        # First draft mode
        out = make_first_draft(raw_text, chap_id, args, voice_spec, 
                               prev_final, source_loader)
        log.info("✔ draft → %s", out)

if __name__ == "__main__":
    main() 