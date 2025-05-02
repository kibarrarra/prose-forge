#!/usr/bin/env python
"""
export_original.py – write cleaned plaintext versions of every raw chapter
                      into data/context/<chap_id>.txt

Run:
    python scripts/export_original.py             # process all chapters
    python scripts/export_original.py lotm_0001   # just one

The cleaning logic is identical to load_raw_text() in writer.py.
"""

from __future__ import annotations
import argparse, json, pathlib, re
from pathlib import Path
from utils.io_helpers import read_utf8, write_utf8
from utils.paths import RAW_DIR, SEG_DIR, CTX_DIR
from utils.logging_helper import get_logger
from ftfy import fix_text

log = get_logger()


# ---------------------------------------------------------------------------
# fallback cleaners if segment_chapters is not available
try:
    from scripts.segment_chapters import strip_html, normalise  # type: ignore
except ImportError:
    import html, unicodedata
    _TAG = re.compile(r"<[^>]+>")
    def strip_html(s: str) -> str:       # noqa: D401
        return _TAG.sub("", html.unescape(s))
    def normalise(s: str) -> str:
        return unicodedata.normalize("NFKC", s.replace("\r\n", "\n"))

def format_paragraphs(text: str) -> str:
    """Format text with proper paragraph breaks and spacing."""
    # Normalize all whitespace first
    text = re.sub(r'\s+', ' ', text)
    
    # Split into paragraphs based on common paragraph markers
    paragraphs = re.split(r'(?:\n\s*){2,}|(?:\r\n\s*){2,}', text)
    
    # Clean and format each paragraph
    formatted_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Remove excessive internal whitespace
        para = re.sub(r'\s+', ' ', para)
        # Ensure proper sentence spacing
        para = re.sub(r'\.([A-Z])', r'. \1', para)
        formatted_paragraphs.append(para)
    
    return '\n\n'.join(formatted_paragraphs)

def clean_json(path: Path) -> str:
    """Extract plaintext from crawler JSON with improved formatting."""
    blocks = json.loads(read_utf8(path))
    if not isinstance(blocks, list):
        blocks = [blocks]
    parts = []
    for chapter in blocks:
        text = next(
            (chapter.get(k) for k in ("content", "body", "text", "chapter") if k in chapter),
            ""
        )
        if text:
            # Apply ftfy fixes and strip HTML
            text = fix_text(strip_html(text))
            parts.append(text)
    
    # Join all parts and format paragraphs
    combined = "\n\n".join(parts)
    return format_paragraphs(normalise(combined))

def source_paths(single_id: str | None, all_chapters: bool) -> list[Path]:
    log.info("Searching in directory: %s", RAW_DIR)
    if single_id and not all_chapters:
        cand = RAW_DIR / f"{single_id}.json"
        log.info("Looking for specific chapter: %s", cand)
        if cand.exists():
            log.info("Found chapter file: %s", cand)
            return [cand]
        log.warning("Chapter file not found: %s", cand)
        return []
    
    log.info("Searching for all JSON files in %s", RAW_DIR)
    files = sorted(RAW_DIR.glob("*.json"))
    if files:
        log.info("Found %d JSON files", len(files))
        for f in files:
            log.debug("Found file: %s", f)
    else:
        log.warning("No JSON files found in %s", RAW_DIR)
    return files

def export_one(json_path: Path) -> None:
    chap_id = json_path.stem
    # prefer segments if they exist (e.g., hand-cleaned)
    segs = sorted(SEG_DIR.glob(f"{chap_id}_p*.txt"))
    if segs:
        text = "\n\n".join(read_utf8(p) for p in segs)
        log.info("using %d segment files for %s", len(segs), chap_id)
    else:
        text = clean_json(json_path)
        log.info("cleaned %s", json_path.name)

    CTX_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CTX_DIR / f"{chap_id}.txt"
    write_utf8(out_path, text)
    log.info("wrote %s (%d chars)", out_path, len(text))

# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter_id", nargs="?",
                    help="Process only this chapter id (e.g., lotm_0001)")
    ap.add_argument("--all", action="store_true",
                    help="Process all chapters regardless of chapter_id")
    args = ap.parse_args()

    todo = source_paths(args.chapter_id, args.all)
    if not todo:
        log.error("No raw JSON found for that chapter id.")
        return
    for p in todo:
        export_one(p)

if __name__ == "__main__":
    main()
