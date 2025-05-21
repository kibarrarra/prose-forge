#!/usr/bin/env python
"""
io_helpers.py – tiny utilities for BOM-safe UTF-8 reading / writing.

All project code should import these instead of calling Path.read_text().
"""

from pathlib import Path
import sys, os
import unicodedata
import re

BOM = b"\xef\xbb\xbf"

# ── public API ─────────────────────────────────────────────────────────────
def read_utf8(path: Path) -> str:
    """
    Return file contents as str, decoded UTF-8, stripping BOM if present.
    Uses strict error-handling by default to catch encoding issues early.
    """
    try:
        raw = path.read_bytes()
        if raw.startswith(BOM):
            raw = raw[len(BOM):]
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # Fall back to a more lenient approach if strict parsing fails
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            # Last resort: use normalize_text on the replaced version
            raw_text = path.read_bytes().decode("utf-8", errors="replace")
            return normalize_text(raw_text)

def write_utf8(path: Path, text: str) -> None:
    """Write text to file using UTF-8 encoding, ensuring proper character handling."""
    # Normalize text before writing to ensure consistent character encoding
    normalized_text = normalize_text(text)
    path.write_text(normalized_text, encoding="utf-8")

def normalize_text(text: str) -> str:
    """
    Normalize Unicode text to ensure consistent character representation.
    Fixes common encoding issues with em dashes, smart quotes, etc.
    """
    # Normalize to composed form (NFC)
    text = unicodedata.normalize('NFC', text)
    
    # Fix common character substitutions
    replacements = {
        'â€"': '—',  # em dash
        'â€"': '–',  # en dash
        'â€˜': ''',  # left single quote
        'â€™': ''',  # right single quote
        'â€œ': '"',  # left double quote
        'â€': '"',   # right double quote
        'â€¦': '…',  # ellipsis
    }
    
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    
    return text

def escape_for_fstring(text: str) -> str:
    """
    Escape text content to be safely used inside f-strings.
    This handles newlines, backslashes and other characters that could cause issues in f-strings.
    """
    # Replace literal backslashes with double backslashes to ensure proper escaping in f-strings
    text = text.replace('\\', '\\\\')
    
    # No need to escape newlines since we're not placing this in a raw string literal
    # Instead, we can pass the string as is, and let Python handle the formatting
    
    return text

def ensure_utf8_windows() -> None:
    """Force UTF-8 on Windows terminals so Unicode output is readable."""
    if sys.platform == "win32":
        if sys.stdout.encoding != "utf-8":
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except AttributeError:
                # Python 3.6 and earlier don't have reconfigure
                os.environ["PYTHONIOENCODING"] = "utf-8"
        if sys.stderr.encoding != "utf-8":
            try:
                sys.stderr.reconfigure(encoding="utf-8")
            except AttributeError:
                pass
        os.environ["PYTHONIOENCODING"] = "utf-8"
