#!/usr/bin/env python
"""
fix_encoding.py - Fix encoding issues in files.

This script normalizes text in existing files to fix common encoding issues
with special characters like em dashes, smart quotes, etc.

Usage:
    python scripts/fix_encoding.py [filepath]
    python scripts/fix_encoding.py --all-drafts
"""

import argparse
import pathlib
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from utils.paths import ROOT, DRAFT_DIR, SEG_DIR
from scripts.utils.io_helpers import read_utf8, write_utf8, normalize_text
from utils.logging_helper import get_logger

log = get_logger()

def process_file(filepath: Path) -> bool:
    """Process a file to fix encoding issues."""
    if not filepath.exists():
        log.error(f"File not found: {filepath}")
        return False
    
    try:
        # Read the file
        content = read_utf8(filepath)
        
        # Normalize the text
        normalized = normalize_text(content)
        
        # Only write if changed
        if content != normalized:
            write_utf8(filepath, normalized)
            log.info(f"Fixed encoding issues in: {filepath}")
            return True
        else:
            log.info(f"No encoding issues found in: {filepath}")
            return False
    except Exception as e:
        log.error(f"Error processing {filepath}: {e}")
        return False

def process_all_drafts() -> int:
    """Process all draft files in the drafts directory."""
    count = 0
    
    # Process all files in the drafts directory with .txt extension
    for filepath in DRAFT_DIR.glob("**/*.txt"):
        if process_file(filepath):
            count += 1
    
    return count

def main() -> None:
    parser = argparse.ArgumentParser(description="Fix encoding issues in files")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("filepath", nargs="?", type=Path, help="Path to file to fix")
    group.add_argument("--all-drafts", action="store_true", help="Fix all draft files")
    
    args = parser.parse_args()
    
    if args.all_drafts:
        count = process_all_drafts()
        log.info(f"Fixed encoding issues in {count} files")
    else:
        process_file(args.filepath)

if __name__ == "__main__":
    main() 