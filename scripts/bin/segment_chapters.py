#!/usr/bin/env python
"""
segment_chapters.py  –  Split big novel files into per-chapter files
                        (TXT or JSON) with a progress bar.

Examples
────────
# 1) Mega-JSON  ➜  per-chapter JSON
python scripts/segment_chapters.py data/raw/lotm_full.json --slug lotm

# 2) Plain text ➜  per-chapter TXT
python scripts/segment_chapters.py data/raw/lotm_full.txt  --slug lotm

# 3) Folder of sources (progress bar shown)
python scripts/segment_chapters.py data/raw/novels --recursive
"""

from __future__ import annotations
import argparse, html, json, re, unicodedata, sys
from pathlib import Path
from typing import List, Iterable

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from ftfy import fix_text
from scripts.utils.io_helpers import write_utf8

# progress bar (fallback to plain iterator if tqdm missing)
try:
    from tqdm import tqdm
except ImportError:                               # noqa: D401
    tqdm = lambda x, **kw: x                      # type: ignore

# ─── HTML + Unicode helpers ────────────────────────────────────────────────
_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_P   = re.compile(r"<\s*(p|br)[^>]*>", re.I)
_CREDIT   = re.compile(r"(translator|editor)\s*:", re.I)

def strip_html(raw: str) -> str:
    s = html.unescape(raw)
    s = _HTML_P.sub("\n\n", s)
    s = _HTML_TAG.sub("", s)
    s = "\n".join(l for l in s.splitlines() if not _CREDIT.search(l))
    return fix_text(s)

def normalise(text: str) -> str:
    return unicodedata.normalize("NFKC",
                                 text.replace("\r\n", "\n").replace("\u00A0", " "))

# ─── load any .txt / crawler .json ─────────────────────────────────────────
_PREFERRED = ["content", "body", "text", "chapter"]

def load_text(path: Path) -> str:
    raw = path.read_bytes().lstrip(b"\xef\xbb\xbf")          # strip BOM
    if path.suffix.lower() != ".json":
        return normalise(raw.decode("utf-8"))

    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list):
        data = data.get("chapters", [])
    blocks: List[str] = []
    for ch in data:
        if not isinstance(ch, dict):
            continue
        for k in _PREFERRED:
            if k in ch and isinstance(ch[k], str):
                blocks.append(ch[k]); break
        else:
            for v in ch.values():
                if isinstance(v, str) and len(v) > 20:
                    blocks.append(v); break
    joined = "\n\n".join(strip_html(b) for b in blocks)
    if not joined.strip():
        raise ValueError(f"No prose found in {path.name}")
    return normalise(joined)

# ─── regex split for plain-text files ──────────────────────────────────────
_CHAP_RE = re.compile(r"^\s*(?:Chapter|CHAPTER)\s+(\d+)\b", re.I | re.M)

def split_txt_into_chapters(text: str) -> list[tuple[int, str]]:
    m = list(_CHAP_RE.finditer(text))
    if not m:
        raise ValueError("No chapter headings found – adjust _CHAP_RE.")
    out: list[tuple[int, str]] = []
    for i, hit in enumerate(m):
        start = hit.end()
        end   = m[i+1].start() if i+1 < len(m) else len(text)
        out.append((int(hit.group(1)), text[start:end].lstrip("\n")))
    return out

# ─── writer ────────────────────────────────────────────────────────────────
def write_chapters(src: Path, dest_dir: Path, slug: str | None = None) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    tag = slug or src.stem

    if src.suffix.lower() == ".json":
        raw = src.read_bytes().lstrip(b"\xef\xbb\xbf")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, list):
            raise ValueError("Mega-JSON must be a list of chapter dicts")
        for idx, ch in enumerate(data, start=1):
            out = dest_dir / f"{tag}_{idx:04d}.json"
            out.write_text(json.dumps([ch], ensure_ascii=False), encoding="utf-8")
        print(f"✂  {src.name} → {idx} chapter JSON files")
        return

    body = load_text(src)
    chapters = split_txt_into_chapters(body)
    for num, content in chapters:
        out = dest_dir / f"{tag}_{num:04d}.txt"
        write_utf8(out, content.strip() + "\n")
    print(f"✂  {src.name} → {len(chapters)} chapter TXT files")

# ─── helpers to gather input files ─────────────────────────────────────────
def iter_sources(root: Path, recursive: bool) -> Iterable[Path]:
    if root.is_file():
        yield root
    else:
        pattern = "**/*" if recursive else "*"
        for p in root.glob(pattern):
            if p.suffix.lower() in {".txt", ".json"} and p.is_file():
                yield p

# ─── CLI ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Split novel files into per-chapter files with progress bar."
    )
    ap.add_argument("source", type=Path,
                    help="File OR directory containing .txt / .json novels.")
    ap.add_argument("--dest", type=Path, default=Path("raw/chapters"),
                    help="Output directory (default: raw/chapters)")
    ap.add_argument("--slug", type=str,
                    help="Filename prefix (ignored when processing a directory "
                         "unless you pass --force-slug).")
    ap.add_argument("--recursive", action="store_true",
                    help="Recurse into sub-folders when source is a directory.")
    ap.add_argument("--force-slug", action="store_true",
                    help="Apply --slug to every file even in dir mode.")
    args = ap.parse_args()

    sources = list(iter_sources(args.source, args.recursive))
    if not sources:
        raise SystemExit("No .txt or .json files found.")

    iterable = tqdm(sources, desc="Chapter-splitting", unit="file") \
               if len(sources) > 1 else sources

    for src in iterable:
        tag = args.slug if (args.slug and (args.force_slug or src == args.source)) else None
        write_chapters(src, args.dest, tag)

    print("✔ All done")

if __name__ == "__main__":
    main()
