#!/usr/bin/env python
"""
io_helpers.py – tiny utilities for BOM-safe UTF-8 reading / writing.

All project code should import these instead of calling Path.read_text().
"""

from pathlib import Path
import sys, os

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

def ensure_utf8_windows() -> None:
    """Force UTF-8 on Windows terminals so Unicode output is readable."""
    if sys.platform == "win32":
        if sys.stdout.encoding != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr.encoding != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8")
        os.environ["PYTHONIOENCODING"] = "utf-8"
