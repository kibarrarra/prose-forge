#!/usr/bin/env python
"""
io_helpers.py – tiny utilities for BOM-safe UTF-8 reading / writing.

All project code should import these instead of calling Path.read_text().
"""

from pathlib import Path

BOM = b"\xef\xbb\xbf"

# ── public API ─────────────────────────────────────────────────────────────
def read_utf8(path: Path) -> str:
    """
    Return file contents as str, decoded UTF-8, stripping BOM if present.
    Uses 'replace' error-handling so curly quotes / smart dashes never crash.
    """
    raw = path.read_bytes()
    if raw.startswith(BOM):
        raw = raw[len(BOM):]
    return raw.decode("utf-8", errors="replace")

def write_utf8(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
