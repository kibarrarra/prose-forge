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
import html
import tqdm
from typing import TextIO
from ftfy import fix_text
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, List, Literal

# ─── Progress bar (optional) ─────────────────────────────────────────────────
try:
    from tqdm import tqdm  # type: ignore
except ImportError:        # noqa: D401
    tqdm = lambda x, **kw: x  # dummy: just return the iterable unchanged


SPLIT_MODE = Literal["para", "sent"]
_PREFERRED = ["content", "body", "text", "chapter"]     # all lowercase

_HTML_P   = re.compile(r"<\s*(p|br)[^>]*>", re.I)       # <p>, <br>, variants
_HTML_TAG = re.compile(r"<[^>]+>")
_CREDIT   = re.compile(r"(translator|editor)\s*:", re.I)

# ────────────────────────────────────────────────────────────────
# Loading & normalisation helpers
# ────────────────────────────────────────────────────────────────
def load_text(path: Path) -> str:
    """
    Return plain text from either a .txt file or a crawler .json bundle.
    – Removes UTF-8 BOM.
    – Accepts any reasonable field name (see _PREFERRED).
    """

    text_decoded = path.read_bytes().lstrip(b"\xef\xbb\xbf").decode("utf-8")

    if path.suffix.lower() != ".json":
        return text_decoded

    data = json.loads(text_decoded)
    if not isinstance(data, list):
        data = data.get("chapters", [])         # older crawler format

    def clean(raw: str) -> str:
        return fix_text(strip_html(raw))

    def extract(ch: dict) -> str | None:
        # case-fold keys once
        for key, val in ((k.lower(), v) for k, v in ch.items()):
            if key in _PREFERRED and isinstance(val, str) and val.strip():
                return strip_html(val)

        # fallback: first string value > 20 chars
        for val in ch.values():
            if isinstance(val, str) and len(val.strip()) > 20:
                return strip_html(val)

        return None

    pieces: list[str] = [
        cleaned for ch in data if isinstance(ch, dict)
        for cleaned in [extract(ch)] if cleaned
    ]

    if not pieces:
        first_keys = list(data[0].keys()) if data else []
        raise ValueError(
            f"No prose found – check JSON keys inside {path.name}. "
            f"First object keys: {first_keys}"
        )

    return "\n\n".join(pieces)


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


def strip_html(raw: str) -> str:
    """Unescape HTML, keep paragraph structure, drop credit lines, fix mojibake."""
    # 1) normalise &nbsp; &#39; etc.
    s = html.unescape(raw)
    # 2) turn any <p> / <br> into two newlines so split_paragraphs() can see them
    s = _HTML_P.sub("\n\n", s)
    # 3) strip all remaining tags
    s = _HTML_TAG.sub("", s)
    # 4) remove translator/editor credit lines
    s = "\n".join(line for line in s.splitlines() if not _CREDIT.search(line))
    # 5) ftfy to repair mojibake (â€™ → ’, etc.)
    return fix_text(s)

# ──────────────────────────────────────────────────────────────────────────────
# Core logic
# ──────────────────────────────────────────────────────────────────────────────
def segment_file(
    path: Path,
    dest: Path,
    mode: SPLIT_MODE,
    csv_writer: csv.writer | None = None,
) -> None:
    """
    Segment one .txt or .json file.
    • If it's a crawler JSON bundle, show an inner tqdm bar per chapter.
    • Otherwise, treat it as plain text.
    """

    chapter_tag = path.stem                    # e.g. lotm_full or lotm_0001-0100
    dest.mkdir(parents=True, exist_ok=True)

    # ─── Case A: crawler JSON bundle with many chapters ────────────────────
    if path.suffix.lower() == ".json":
        raw_bytes   = path.read_bytes()
        text_dec    = raw_bytes.lstrip(b"\xef\xbb\xbf").decode("utf-8")
        data = json.loads(text_dec)
        if not isinstance(data, list):
            data = data.get("chapters", [])

        # tqdm for big bundles (threshold 50 chapters)
        chap_iter = (
            tqdm(data, desc=chapter_tag, unit="chap", leave=False)
            if len(data) > 50 else data
        )

        _PREFERRED = ["content", "body", "text", "chapter"]  # already defined earlier

        def clean_html(raw: str) -> str:
            return strip_html(raw)  # uses your existing strip_html + ftfy

        def extract(ch: dict) -> str | None:
            # 1) preferred keys
            for k, v in ((k.lower(), v) for k, v in ch.items()):
                if k in _PREFERRED and isinstance(v, str) and v.strip():
                    return clean_html(v)
            # 2) fallback first long string
            for v in ch.values():
                if isinstance(v, str) and len(v.strip()) > 20:
                    return clean_html(v)
            return None

        pieces: list[str] = [
            txt for ch in chap_iter if isinstance(ch, dict)
            for txt in [extract(ch)] if txt
        ]
        raw_text = normalise("\n\n".join(pieces))

    # ─── Case B: plain .txt (or already-clean JSON handled by load_text) ───
    else:
        raw_text = normalise(load_text(path))

    # ─── Split & write out segments ────────────────────────────────────────
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

    csv_file: TextIO | None = None
    csv_writer: csv.writer | None = None
    try:
        if args.csv:
            args.csv.parent.mkdir(parents=True, exist_ok=True)
            csv_file = args.csv.open("w", encoding="utf-8", newline="")
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(["seg_id", "text"])

        files = list(iter_files(args.inp, args.recursive))   # materialise once

        # Only show tqdm when there's more than one file
        iterable = tqdm(files, desc="Segmenting", unit="file") if len(files) > 1 else files

        for file in iterable:
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
