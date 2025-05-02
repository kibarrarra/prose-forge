#!/usr/bin/env python
"""
writer.py - Create or revise a chapter draft according to voice_spec.md.

Core modes
──────────
1. First draft            $ writer.py lotm_0006
2. Audition (first 2k w)  $ writer.py lotm_0001 --sample 2000 --persona lovecraft
3. Revision pass          $ writer.py lotm_0006 --revise notes/lotm_0006.json
"""

from __future__ import annotations
import argparse, json, math, pathlib, re, sys, textwrap, logging
from typing import Optional, TypedDict
from utils.io_helpers import read_utf8, write_utf8

import httpx
from openai import OpenAI
from dotenv import load_dotenv ; load_dotenv()
from ftfy import fix_text


logging.basicConfig(
    filename="logs/writer.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [writer] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("writer")

# ── project paths ────────────────────────────────────────────────────────────
DIR = pathlib.Path
RAW  = DIR("data/raw/chapters")
SEG  = DIR("data/segments")
CTX  = DIR("data/context")
OUT  = DIR("drafts")
CFG  = DIR("config")
SPEC_DEFAULT = CFG / "voice_spec.md"

# ── OpenAI client ────────────────────────────────────────────────────────────
timeout = httpx.Timeout(
    connect=30.0,
    read=600.0,
    write=600.0,
    pool=60.0
)

client = OpenAI(timeout=timeout)

# ── utilities ────────────────────────────────────────────────────────────────
def die(msg: str) -> None:
    log.error(msg)
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)

def strip_html(text: str) -> str:               # very light fallback
    import re, html
    return re.sub(r"<[^>]+>", "", html.unescape(text))

def normalise(text: str) -> str:
    import unicodedata as ud
    return ud.normalize("NFKC", text.replace("\r\n", "\n"))

def estimate_max_tokens(words: int, factor: float = 1.4) -> int:
    """1 token ≈ 0.75 words → pad by factor."""
    return max(1024, min(int(words / 0.75 * factor), 8192))

# ── load raw source text ─────────────────────────────────────────────────────
def resolve_chapter(arg: str) -> pathlib.Path:
    p = pathlib.Path(arg)
    if p.exists():
        return p
    # treat as chapter id
    if (CTX / f"{arg}.txt").exists() or any(SEG.glob(f"{arg}_p*.txt")):
        return pathlib.Path(f"{arg}.stub")
    if (RAW / f"{arg}.json").exists():
        return RAW / f"{arg}.json"
    die(f"Cannot locate chapter '{arg}'.")

def load_raw_text(path: pathlib.Path) -> tuple[str, str]:
    """
    Return (clean_plaintext, chapter_id). Handles .json, plain text, or
    segment/context fallbacks. Always decodes as UTF-8 and strips BOM.
    """
    chap_id = path.stem

    # ---------- JSON ----------
    if path.suffix.lower() == ".json":
        blocks = json.loads(read_utf8(path))
        if not isinstance(blocks, list):
            blocks = [blocks]
        parts = [
            strip_html(fix_text(p))
            for b in blocks
            for k in ("content", "body", "text")
            if isinstance((p := b.get(k, "")), str)
        ]
        return normalise("\n\n".join(parts)), chap_id

    # ---------- segment or context ----------
    segs = sorted(SEG.glob(f"{chap_id}_p*.txt"))
    if segs:
        txt = "\n\n".join(read_utf8(p) for p in segs)
    else:
        ctx = CTX / f"{chap_id}.txt"
        if not ctx.exists():
            die(f"No plaintext found for {chap_id}.")
        txt = read_utf8(ctx)

    return normalise(txt), chap_id


# ── prompt builders ─────────────────────────────────────────────────────────
def build_author_prompt(source: str, voice_spec: str, length_hint: str,
                        prev_final: Optional[str], persona: Optional[str]) -> list[dict]:
    persona_note = f" as {persona}" if persona else ""
    system = textwrap.dedent(f"""\
        You are 'Chapter-Author'{persona_note}. Follow the voice spec. {length_hint}
        ---
        VOICE SPEC
        ----------
        {voice_spec}
        """)
    user_parts = [f"RAW SOURCE:\n{source}"]
    if prev_final:
        user_parts.append(f"PREVIOUS FINAL CHAPTER:\n{prev_final}")
    return [{"role": "system", "content": system},
            {"role": "user",   "content": "\n\n".join(user_parts)}]

def build_revision_prompt(current: str, notes: dict,
                          voice_spec: str) -> list[dict]:
    system = textwrap.dedent(f"""\
        You are the same 'Chapter-Author'. Apply ONLY the changes requested.
        ---
        VOICE SPEC
        ----------
        {voice_spec}
        """)
    user = textwrap.dedent(f"""\
        CURRENT DRAFT:
        {current}

        CHANGE LIST (JSON):
        {json.dumps(notes, indent=2, ensure_ascii=False)}
        """)
    return [{"role": "system", "content": system},
            {"role": "user",   "content": user}]

def call_llm(msgs: list[dict], temp: float, max_tokens: int) -> str:
    res = client.chat.completions.create(
        model="gpt-4o",
        temperature=temp,
        messages=msgs,
        max_tokens=max_tokens
    )
    return res.choices[0].message.content.strip()

# ── filename helpers ────────────────────────────────────────────────────────
def draft_name(sample: bool, version: int) -> str:
    tag = "_sample" if sample else ""
    return f"author{tag}_v{version}.txt"

def latest_version(folder: DIR, sample: bool) -> int:
    tag = "_sample" if sample else ""
    drafts = sorted(folder.glob(f"author{tag}_v*.txt"))
    if not drafts:
        return 0
    return int(re.search(r"_v(\d+)", drafts[-1].stem)[1])

# ── main actions ────────────────────────────────────────────────────────────
def make_first_draft(text: str, chap_id: str, args, voice_spec: str,
                     prev_final: Optional[str]) -> pathlib.Path:
    # sample truncation
    if args.sample:
        text = " ".join(text.split()[: args.sample])
    src_words = len(text.split())
    target_words = args.target_words or int(src_words * args.target_ratio)
    length_hint = f"Match the source length within ±10 % (≈{target_words} words)."
    max_toks = estimate_max_tokens(target_words)

    prompt = build_author_prompt(text, voice_spec, length_hint,
                                 prev_final, args.persona)
    draft = call_llm(prompt, temp=0.7, max_tokens=max_toks)

    folder = OUT / chap_id
    folder.mkdir(parents=True, exist_ok=True)
    fname  = draft_name(bool(args.sample), 1)
    path   = folder / fname
    write_utf8(path, draft)
    return path

def make_revision(chap_id: str, args, voice_spec: str) -> pathlib.Path:
    notes = json.loads(args.revise.read_text())
    if not any(k in notes for k in ("rewrite", "cut", "keep")):
        die("Revision notes must have at least 'rewrite', 'cut' or 'keep'.")

    folder = OUT / chap_id
    v_now  = latest_version(folder, bool(args.sample))
    if v_now == 0:
        die("No existing draft to revise.")

    current = (folder / draft_name(bool(args.sample), v_now)).read_text()
    max_toks = estimate_max_tokens(len(current.split()))
    prompt = build_revision_prompt(current, notes, voice_spec)
    new_draft = call_llm(prompt, temp=0.4, max_tokens=max_toks)

    fname = draft_name(bool(args.sample), v_now + 1)
    path  = folder / fname
    path.write_text(new_draft, encoding="utf-8")
    return path

# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("chapter", help="Chapter id (lotm_0006) or path to JSON/TXT")
    p.add_argument("--spec", type=DIR,
                   help="Voice spec file (default: config/voice_spec.md)")
    p.add_argument("--persona", help="Persona label for auditions")
    p.add_argument("--sample", type=int,
                   help="Use only first N words of RAW SOURCE")
    p.add_argument("--target-words", type=int)
    p.add_argument("--target-ratio", type=float, default=1.0)
    p.add_argument("--prev", type=DIR, help="Previous locked chapter")
    p.add_argument("--revise", type=DIR,
                   help="JSON notes file from critic/auditor")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    chap_path = resolve_chapter(args.chapter)
    raw_text, chap_id = load_raw_text(chap_path)

    # ── voice spec resolution ─────────────────────────────────────────────
    if args.spec:
        spec_path = args.spec
    elif args.persona:
        spec_path = pathlib.Path(f"config/voice_specs/{args.persona}.md")
    else:
        spec_path = SPEC_DEFAULT

    if not spec_path.exists():
        die(f"Voice spec not found: {spec_path}")
    voice_spec = read_utf8(spec_path)

    prev_final = args.prev.read_text() if args.prev and args.prev.exists() else None

    if args.revise:
        out = make_revision(chap_id, args, voice_spec)
        log.info("✔ revision → %s", out)
    else:
        out = make_first_draft(raw_text, chap_id, args, voice_spec, prev_final)
        log.info("✔ draft → %s", out)

if __name__ == "__main__":
    main()
