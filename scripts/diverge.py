#!/usr/bin/env python
"""
diverge.py – generate N stylistically varied first-draft rewrites of one chapter.

The script searches for clean plaintext in this order:
    1. data/segments/<chap_id>_p*.txt         (paragraph files)
    2. data/context/<chap_id>.txt             (whole-chapter plaintext)
    3. data/raw/chapters/<chap_id>.json       (raw crawler JSON → cleaned)

Output:
    drafts/<chap_id>/<id>.txt  (five drafts per chapter)

Usage examples
--------------
# run by chapter id (preferred)
python scripts/diverge.py lotm_0001

# run by explicit file path
python scripts/diverge.py data/raw/chapters/lotm_0001.json
"""

from __future__ import annotations
import argparse, json, os, pathlib, sys, textwrap
from typing import List

# ─── third-party deps ─────────────────────────────────────────────────────────
from dotenv import load_dotenv; load_dotenv()          # loads .env
try:
    from tqdm import tqdm                              # optional, nice bar
except ImportError:                                    # noqa: D401
    tqdm = lambda x, **kw: x                           # type: ignore

import openai, yaml
from ftfy import fix_text

client = OpenAI(
    # keep OpenAI’s automatic 2 retries, just stretch the handshake window
    timeout=httpx.Timeout(
        connect=30.0,   # ⬅️ give DNS+TCP up to 30 s
        read=600.0,     # leave the 10-min read cap (or bump if you want)
    )
)
# ─── folder constants ─────────────────────────────────────────────────────────
RAW_DIR    = pathlib.Path("data/raw/chapters")
SEG_DIR    = pathlib.Path("data/segments")
CTX_DIR    = pathlib.Path("data/context")
DRAFT_ROOT = pathlib.Path("drafts")

# ─── import helpers from your segment script (HTML strip + unicode normalise) ─
try:
    from scripts.segment import strip_html, normalise  # type: ignore
except ImportError:
    # Fallback ultra-light cleaners (won’t be as robust but prevents crash)
    import html, re, unicodedata
    _TAG = re.compile(r"<[^>]+>")
    def strip_html(s: str) -> str:
        return _TAG.sub("", html.unescape(s))
    def normalise(s: str) -> str:
        return unicodedata.normalize("NFKC", s.replace("\r\n", "\n"))


# ─── stylistic diversity manifest (edit as you wish) ──────────────────────────
_MANIFEST_YAML = """
drafts:
  - id: vivid_T07
    temp: 0.7
    delta: "Lean into sensory detail and dramatic pacing."
  - id: concise_T06
    temp: 0.6
    delta: "Aim for economical sentences and crisp clarity."
  - id: lyrical_T08
    temp: 0.8
    delta: "Allow mild poetic phrasing and varied cadence."
  - id: noir_T07
    temp: 0.7
    delta: "Adopt a slightly sardonic, hard-boiled tone."
  - id: neutral_T05
    temp: 0.5
    delta: ""
"""
MANIFEST: List[dict] = yaml.safe_load(_MANIFEST_YAML)["drafts"]

SYSTEM_BASE = (
    "You are an accomplished novelist. Rewrite the chapter while preserving "
    "plot facts, character names, and chronology. {delta}"
)

# ─── util: obtain clean plaintext ─────────────────────────────────────────────
def load_from_segments(chap_id: str) -> str | None:
    segs = sorted(SEG_DIR.glob(f"{chap_id}_p*.txt"))
    if segs:
        return "\n\n".join(p.read_text() for p in segs)
    return None

def load_from_context(chap_id: str) -> str | None:
    f = CTX_DIR / f"{chap_id}.txt"
    return f.read_text() if f.exists() else None

def clean_raw_json(json_path: pathlib.Path) -> str:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):                     # crawler v1 shape
        data = [data]
    blocks = []
    for ch in data:
        val = next(
            (ch.get(k) for k in ("content", "body", "text", "chapter") if k in ch),
            None,
        )
        if val:
            blocks.append(fix_text(strip_html(val)))
    return normalise("\n\n".join(blocks))

def chapter_plaintext(src: pathlib.Path) -> tuple[str, str]:
    chap_id = src.stem
    txt = load_from_segments(chap_id) or load_from_context(chap_id)
    if txt:
        return txt, chap_id
    if src.suffix.lower() != ".json":
        sys.exit(f"❌ No clean text found and {src} is not JSON.")
    return clean_raw_json(src), chap_id

# ─── util: LLM call ───────────────────────────────────────────────────────────
def ask_llm(style_delta: str, temp: float, chapter_txt: str) -> str:
    msg = [
        {"role": "system", "content": SYSTEM_BASE.format(delta=style_delta)},
        {"role": "user",   "content": chapter_txt},
    ]
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=temp,
        messages=msg,
        max_tokens=4096,
    )
    return resp.choices[0].message.content.strip()

# ─── main workflow ────────────────────────────────────────────────────────────
def diverge(src_path: pathlib.Path) -> None:
    chapter_txt, chap_id = chapter_plaintext(src_path)
    out_dir = DRAFT_ROOT / chap_id
    out_dir.mkdir(parents=True, exist_ok=True)

    for cfg in tqdm(MANIFEST, desc=f"Diverging {chap_id}", unit="draft"):
        draft = ask_llm(cfg["delta"], cfg["temp"], chapter_txt)
        out_file = out_dir / f"{cfg['id']}.txt"
        out_file.write_text(draft, encoding="utf-8")
        tqdm.write(f"  ↳ wrote {out_file}")

# ─── CLI parsing ──────────────────────────────────────────────────────────────
def resolve_input(arg: str) -> pathlib.Path:
    """
    Accept:
      • explicit path to .json / .txt  OR
      • chapter id (lotm_0001) **if** we can find either:
          - any segment file data/segments/<id>_p*.txt
          - context/<id>.txt
          - raw/chapters/<id>.json  (fallback)
    """
    p = pathlib.Path(arg)
    if p.is_file():
        return p            # explicit path case

    chap_id = arg               # treat as id

    # 1) any segment files?
    if any(SEG_DIR.glob(f"{chap_id}_p*.txt")):
        return pathlib.Path(f"{chap_id}.stub")  # dummy path just to carry stem

    # 2) context file?
    if (CTX_DIR / f"{chap_id}.txt").exists():
        return pathlib.Path(f"{chap_id}.stub")

    # 3) raw json fallback
    cand = RAW_DIR / f"{chap_id}.json"
    if cand.exists():
        return cand

    sys.exit(f"❌ Could not resolve {arg} — "
             f"no segments, context, or JSON found.")


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="chapter id (lotm_0001) or path to JSON/TXT")
    diverge(resolve_input(parser.parse_args().input))
