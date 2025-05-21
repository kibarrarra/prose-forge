#!/usr/bin/env python
"""
paths.py – single source of truth for project folders.
           Import these constants everywhere.
"""

import os
from pathlib import Path

# Try to get root from environment variable first
ROOT = os.environ.get('PROSE_FORGE_ROOT')
if ROOT:
    ROOT = Path(ROOT).resolve()
else:
    # Fallback: look for a marker file (like .git or pyproject.toml) in parent directories
    current = Path(__file__).resolve()
    while current.parent != current:
        if any((current / marker).exists() for marker in ['.git', 'pyproject.toml', 'README.md']):
            ROOT = current
            break
        current = current.parent
    else:
        raise RuntimeError("Could not determine project root. Set PROSE_FORGE_ROOT environment variable or ensure you're in the project directory.")

DATA        = ROOT / "data"
RAW_DIR     = DATA / "raw" / "chapters"
SEG_DIR     = DATA / "segments"
CTX_DIR     = DATA / "context"

DRAFT_DIR   = ROOT / "drafts"
OUTPUT_DIR  = ROOT / "outputs"
EXP_SUMM_DIR = DRAFT_DIR / "experiment_summaries"
NOTES_DIR   = ROOT / "notes"
LOG_DIR     = ROOT / "logs"
CONFIG_DIR  = ROOT / "config"
VOICE_DIR   = CONFIG_DIR / "voice_specs"

# guarantee critical folders exist at import-time
for p in (LOG_DIR,):
    p.mkdir(exist_ok=True)
