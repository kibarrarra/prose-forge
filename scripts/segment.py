#!/usr/bin/env python
"""
segment.py – slice chapters into numbered paragraphs or sentences.

Examples
--------
# Paragraph-split a single JSON novel
python scripts/segment.py --in data/raw/lotm/lotm_full.json --out data/segments

# Sentence-split every .txt/.json in a folder, recurse, and emit a CSV
python scripts/segment.py --in data/raw/lotm --out data/segments \
                          --mode sent --csv data/segments/summary.csv --recursive
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, List, Literal

SPLIT_MODE = Literal["para", "sent"]

# ──────────────────────────────────────────────────────────────────────────────
# Loading & normalisation helpers
# ──────────────────────────────────────────────────────────────────────────────
def load_text(path: Path) -> str:
    """
    Return plain text from either a .txt file or a crawler .json bundle.
    – Removes UTF-8 BOM.
    – Accepts any reasonable field name ('content', 'CONTENT', 'body', …).
    """

    raw_bytes = path.read_bytes()
    text_decoded = raw_bytes.lstrip(b"\xef\xbb\xbf").decode("utf-8")

    if path.suffix.lower() != ".json":
        return text_decoded

    data = json.loads(text_decoded)

    if not isinstance(data, list):
        data = data.get("chapters", [])  # older crawler format

    def extract(ch: dict) -> str | None:
        # preferred key list, then fallback to first long string value
        preferred = ["content", "CONTENT", "body", "text", "chapter"]
        for key in preferred:
            if key in ch and isinstance(ch[key], str) and ch[key].strip():
                return ch[key]
        # fallback: first string value > 20 chars
        for v in ch.values():
            if isinstance(v, str) and len(v) > 20:
                return v
        return None

    pieces = [extract(ch) for ch in data if isinstance(ch, dict)]
    prose = "\n\n".join(p for p in pieces if p)

    if not prose:
        raise ValueError(
            f"No prose found – check JSON keys inside {path.name}. "
            f"Available keys in first object: {list(data[0].keys())}"
        )

    return prose


def normalise(text: str) -> str:
    """Unify Unicode, CRLF, and nbsp."""
    text = text.replace("\r\n", "\n").replace("\u00A0", " ")
    return unicodedata.normalize("NFKC", text)


# ──────────────────────────────────────────────────────────────────────────────
# Splitters
# ──────────────────────────────────────────────────────────────────────────────
_SENTENCE_END = (
    r"(?<!\b[A-Z]\.)(?<!\b[eE][gG]\.)(?<!\b[iI][eE]\.)"  # ignore initials/abbrev.
    r"(?<=[.!?！？])\s+"                                  # real sentence end → space
)


def split_paragraphs(text: str) -> List[str]:
    """
    Split on one + blank line(s) – works whether paragraphs are separated
    by '\n', '\n\n', or '\r\n   \r\n'.  Strips leading/trailing whitespace.
    """
    paras = re.split(r"\r?\n\s*\r?\n", text)   # ← key change
    return [p.strip() for p in paras if p.strip()]

def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(_SENTENCE_END, text) if s.strip()]


def filter_short(units: List[str], min_len: int = 4) -> List[str]:
    """Drop stray artefacts (***, —, etc.)."""
    return [u for u in units if len(u) >= min_len]


# ──────────────────────────────────────────────────────────────────────────────
# Core logic
# ──────────────────────────────────────────────────────────────────────────────
def segment_file(
    path: Path,
    dest: Path,
    mode: SPLIT_MODE,
    csv_writer: csv.writer | None = None,
) -> None:
    chapter_tag = path.stem  # e.g. lotm_full or lotm_0001-0100
    dest.mkdir(parents=True, exist_ok=True)

    raw_text = normalise(load_text(path))
    splitter = split_sentences if mode == "sent" else split_paragraphs
    units = filter_short(splitter(raw_text))

    for idx, chunk in enumerate(units, start=1):
        seg_id = f"{chapter_tag}_{mode[0]}{idx:03d}"
        (dest / f"{seg_id}.txt").write_text(chunk, encoding="utf-8")
        if csv_writer:
            csv_writer.writerow([seg_id, chunk])

    print(f"{path.name}: {len(units)} segments")


# Gather candidate files (single path or folder walk)
def iter_files(root: Path, recursive: bool) -> Iterable[Path]:
    if root.is_file():
        yield root
    else:
        pattern = "**/*" if recursive else "*"
        for p in root.glob(pattern):
            if p.suffix.lower() in {".txt", ".json"} and p.is_file():
                yield p


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry-point
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Segment chapters for ProseForge.")
    parser.add_argument("--in", dest="inp", type=Path, required=True,
                        help="Source file or folder (.txt / .json).")
    parser.add_argument("--out", type=Path, required=True,
                        help="Destination folder for segment files.")
    parser.add_argument("--mode", choices=["para", "sent"], default="para",
                        help="Paragraph (default) or sentence splitting.")
    parser.add_argument("--csv", type=Path,
                        help="Optional CSV summary (seg_id,text).")
    parser.add_argument("--recursive", action="store_true",
                        help="Recurse into sub-directories when --in is a folder.")
    args = parser.parse_args()

    csv_file = None
    csv_writer = None
    try:
        if args.csv:
            args.csv.parent.mkdir(parents=True, exist_ok=True)
            csv_file = args.csv.open("w", encoding="utf-8", newline="")
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(["seg_id", "text"])

        for file in iter_files(args.inp, args.recursive):
            segment_file(file, args.out, args.mode, csv_writer)

    except Exception as exc:  # pragma: no cover
        print(f"✖ Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        if csv_file:
            csv_file.close()

    print("✔ All done")


if __name__ == "__main__":
    main()
