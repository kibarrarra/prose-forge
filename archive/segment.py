#!/usr/bin/env python
"""
segment.py – slice novels into chapters, then paragraphs or sentences.

Quick examples
--------------

# 1) Segment a per-chapter JSON into paragraphs
python scripts/segment.py --in data/raw/chapters/lotm_0001.json --out data/segments

# 2) Split a mega-JSON into chapters *and* paragraphs
python scripts/segment.py --in data/raw/lotm/lotm_full.json \
        --split-per-chapter --chapters-out data/raw/chapters --out data/segments

# 3) Only create per-chapter JSON (no segments yet)
python scripts/segment.py --in data/raw/lotm/lotm_full.json \
        --split-per-chapter --no-segments
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

# ─── optional deps ────────────────────────────────────────────────────────────
try:
    from tqdm import tqdm  # progress bar
except ImportError:  # noqa: D401 – dummy fallback keeps code simple
    tqdm = lambda x, **kw: x  # type: ignore

from ftfy import fix_text
from dotenv import load_dotenv

load_dotenv()  # for scripts that also use OPENAI_API_KEY down-stream

# ─── type helpers ─────────────────────────────────────────────────────────────
SPLIT_MODE = Literal["para", "sent"]

# ─── constants & regexes ──────────────────────────────────────────────────────
_PREFERRED = ["content", "body", "text", "chapter"]  # canonical field names
_SENTENCE_END = (
    r"(?<!\b[A-Z]\.)(?<!\b[eE][gG]\.)(?<!\b[iI][eE]\.)"  # ignore initials / i.e.
    r"(?<=[.!?！？])\s+"                                  # real sentence end
)
_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_P   = re.compile(r"<\s*(p|br)[^>]*>", re.I)
_CREDIT   = re.compile(r"(translator|editor)\s*:", re.I)


# ──────────────────────────────────────────────────────────────────────────────
# HTML + Unicode cleaning helpers
# ──────────────────────────────────────────────────────────────────────────────
def strip_html(raw: str) -> str:
    """Unescape entities, preserve paragraph breaks, drop credits, fix mojibake."""
    import html

    s = html.unescape(raw)
    s = _HTML_P.sub("\n\n", s)          # keep structure for para split
    s = _HTML_TAG.sub("", s)
    s = "\n".join(l for l in s.splitlines() if not _CREDIT.search(l))
    return fix_text(s)


def normalise(text: str) -> str:
    """CRLF→LF, nbsp→space, NFKC."""
    return unicodedata.normalize("NFKC",
                                 text.replace("\r\n", "\n").replace("\u00A0", " "))


# ──────────────────────────────────────────────────────────────────────────────
# Loader (BOM-safe, JSON aware)
# ──────────────────────────────────────────────────────────────────────────────
def load_text(path: Path) -> str:
    """Return plain text from .txt or crawler .json."""
    raw_bytes = path.read_bytes().lstrip(b"\xef\xbb\xbf")  # strip UTF-8 BOM
    if path.suffix.lower() != ".json":
        return raw_bytes.decode("utf-8")

    data = json.loads(raw_bytes.decode("utf-8"))

    if not isinstance(data, list):
        data = data.get("chapters", [])

    blocks: List[str] = []
    for ch in data:
        if not isinstance(ch, dict):
            continue
        for k in _PREFERRED:
            if k in ch and isinstance(ch[k], str):
                blocks.append(ch[k])
                break
        else:
            # fallback first long string
            for v in ch.values():
                if isinstance(v, str) and len(v) > 20:
                    blocks.append(v)
                    break

    join = "\n\n".join(strip_html(b) for b in blocks)
    if not join.strip():
        raise ValueError(f"No prose found in {path.name}")
    return normalise(join)


# ──────────────────────────────────────────────────────────────────────────────
# Splitters
# ──────────────────────────────────────────────────────────────────────────────
def split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\r?\n\s*\r?\n", text) if p.strip()]


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(_SENTENCE_END, text) if s.strip()]


def filter_short(units: List[str], min_len: int = 4) -> List[str]:
    return [u for u in units if len(u) >= min_len]


# ──────────────────────────────────────────────────────────────────────────────
# Core segmenter for one file
# ──────────────────────────────────────────────────────────────────────────────
def segment_file(
    path: Path,
    dest: Path,
    mode: SPLIT_MODE,
    csv_writer: csv.writer | None = None,
) -> None:
    chapter_tag = path.stem  # lotm_0001 or lotm_full
    dest.mkdir(parents=True, exist_ok=True)

    raw_text = load_text(path)
    splitter = split_sentences if mode == "sent" else split_paragraphs
    units = filter_short(splitter(raw_text))

    for idx, chunk in enumerate(units, start=1):
        seg_id = f"{chapter_tag}_{mode[0]}{idx:03d}"
        (dest / f"{seg_id}.txt").write_text(chunk, encoding="utf-8")
        if csv_writer:
            csv_writer.writerow([seg_id, chunk])

    print(f"{path.name}: {len(units)} segments")


# ──────────────────────────────────────────────────────────────────────────────
# Chapter-split helper (mega-JSON → per-chapter JSON)
# ──────────────────────────────────────────────────────────────────────────────
def split_into_chapters(src: Path, dest_dir: Path) -> List[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes().lstrip(b"\xef\xbb\xbf")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Mega-JSON must be a list of chapter dicts")

    out_files: List[Path] = []
    for idx, ch in enumerate(data, start=1):
        out = dest_dir / f"lotm_{idx:04d}.json"
        out.write_text(json.dumps([ch], ensure_ascii=False), encoding="utf-8")
        out_files.append(out)
    print(f"✂ Split {src.name} → {len(out_files)} chapter files in {dest_dir}")
    return out_files


# ──────────────────────────────────────────────────────────────────────────────
# File iterator
# ──────────────────────────────────────────────────────────────────────────────
def iter_files(root: Path, recursive: bool) -> Iterable[Path]:
    if root.is_file():
        yield root
    else:
        pattern = "**/*" if recursive else "*"
        for p in root.glob(pattern):
            if p.suffix.lower() in {".txt", ".json"} and p.is_file():
                yield p


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Segment novels for ProseForge.")

    parser.add_argument("--in", dest="src", type=Path, required=True,
                        help="Source file or folder (.txt / .json).")
    parser.add_argument("--out", type=Path, required=True,
                        help="Destination folder for segment files.")
    parser.add_argument("--mode", choices=["para", "sent"], default="para",
                        help="Paragraph (default) or sentence splitting.")
    parser.add_argument("--csv", type=Path,
                        help="Optional CSV summary (seg_id,text).")
    parser.add_argument("--recursive", action="store_true",
                        help="Recurse into sub-directories when --in is a folder.")

    # new splitting flags
    parser.add_argument("--split-per-chapter", action="store_true",
                        help="If --in is a mega-JSON, slice into per-chapter JSON "
                             "files under --chapters-out.")
    parser.add_argument("--chapters-out", type=Path, default=Path("data/raw/chapters"),
                        help="Directory to write per-chapter JSON when splitting.")
    parser.add_argument("--no-segments", action="store_true",
                        help="With --split-per-chapter: only write JSON, skip segmenting.")

    args = parser.parse_args()

    # ─── handle mega-JSON split first ────────────────────────────────────────
    if args.split_per_chapter:
        chapter_files = split_into_chapters(args.src, args.chapters_out)
        if args.no_segments:
            print("✔ Split complete – skipping segmentation (--no-segments).")
            return
        files_to_process = chapter_files
    else:
        files_to_process = list(iter_files(args.src, args.recursive))

    # ─── CSV setup ───────────────────────────────────────────────────────────
    csv_file = None
    csv_writer = None
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        csv_file = args.csv.open("w", encoding="utf-8", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["seg_id", "text"])

    # ─── segment loop with progress bar ──────────────────────────────────────
    iterable = tqdm(files_to_process, desc="Segmenting", unit="file") \
               if len(files_to_process) > 1 else files_to_process

    try:
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
