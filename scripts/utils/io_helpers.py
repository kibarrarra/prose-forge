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
    
    # Fix common character substitutions - these are UTF-8 mojibake patterns
    # that occur when Windows-1252 characters are incorrectly decoded as UTF-8
    replacements = {
        # Em dash variants
        'â€"': '—',  # em dash (U+2014)
        'â€"': '–',  # en dash (U+2013)
        'â€•': '—',  # horizontal bar (alternate em dash)
        
        # Quote variants
        'â€˜': ''',  # left single quotation mark (U+2018)
        'â€™': ''',  # right single quotation mark (U+2019)
        'â€œ': '"',  # left double quotation mark (U+201C)
        'â€': '"',   # right double quotation mark (U+201D)
        'â€š': '‚',  # single low-9 quotation mark (U+201A)
        'â€ž': '„',  # double low-9 quotation mark (U+201E)
        
        # Other punctuation
        'â€¦': '…',  # horizontal ellipsis (U+2026)
        'â€¢': '•',  # bullet (U+2022)
        'â€º': '›',  # single right-pointing angle quotation mark
        'â€¹': '‹',  # single left-pointing angle quotation mark
        
        # Accented characters
        'Ã¡': 'á',   # a with acute
        'Ã©': 'é',   # e with acute
        'Ã­': 'í',   # i with acute
        'Ã³': 'ó',   # o with acute
        'Ãº': 'ú',   # u with acute
        'Ã±': 'ñ',   # n with tilde
        'Ã¼': 'ü',   # u with diaeresis
        
        # Spaces and non-breaking characters
        'Â ': ' ',   # non-breaking space encoded as UTF-8 mojibake
        'Â': '',     # standalone mojibake byte
        
        # Additional problematic sequences
        'â€‹': '',   # zero-width space (often appears as mojibake)
        'â€Ž': '',   # left-to-right mark
        'â€': '',    # right-to-left mark
    }
    
    # Apply replacements
    for bad, good in replacements.items():
        if bad in text:
            text = text.replace(bad, good)
    
    # Additional cleanup: remove any remaining mojibake patterns
    # Look for sequences that start with â and contain non-ASCII
    # Using a more compatible regex pattern
    mojibake_pattern = re.compile(r'â[\x80-\xff][\x80-\xff]?[\x80-\xff]?')
    problematic_matches = mojibake_pattern.findall(text)
    
    if problematic_matches:
        # Log the problematic sequences for debugging
        import logging
        logger = logging.getLogger(__name__)
        unique_matches = set(problematic_matches)
        logger.warning(f"Found unhandled mojibake sequences in text: {unique_matches}")
        
        # For now, replace with a placeholder to avoid breaking the text
        for match in unique_matches:
            text = text.replace(match, '?')
    
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
