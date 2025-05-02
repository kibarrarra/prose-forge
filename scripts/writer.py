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
import argparse, json, math, pathlib, re, sys, textwrap
from utils.paths import RAW_DIR, SEG_DIR, CTX_DIR, DRAFT_DIR, CONFIG_DIR
from typing import Optional, TypedDict
from utils.io_helpers import read_utf8, write_utf8
from utils.openai_client import get_openai_client
from ftfy import fix_text


# ── logging setup ────────────────────────────────────────────
from utils.logging_helper import get_logger
log = get_logger()

# ── project paths ────────────────────────────────────────────────────────────
DIR = pathlib.Path
RAW  = RAW_DIR
SEG  = SEG_DIR
CTX  = CTX_DIR
OUT  = DRAFT_DIR
CFG  = CONFIG_DIR

# ── OpenAI client ────────────────────────────────────────────────────────────
client = get_openai_client()

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
                        prev_final: Optional[str], persona: Optional[str],
                        critic_feedback: Optional[dict] = None,
                        include_raw: bool = True,
                        raw_ending: str | None = None) -> list[dict]:
    """Compose prompt for the LLM.

    Args:
        include_raw: If False, omit the RAW SOURCE block. Useful for iterative
        review rounds where we want the model to focus on the previous draft
        plus feedback to minimise drift.
    """

    persona_note = f" as {persona}" if persona else ""
    system = textwrap.dedent(f"""\
        You are 'Chapter-Author'{persona_note}. Follow the voice spec. {length_hint}
        ---
        VOICE SPEC
        ----------
        {voice_spec}
        """)

    user_parts: list[str] = []
    if include_raw:
        user_parts.append(f"RAW SOURCE:\n{source}")
    if prev_final:
        user_parts.append(f"PREVIOUS FINAL CHAPTER:\n{prev_final}")
    if critic_feedback:
        user_parts.append(textwrap.dedent(f"""\
            CRITIC FEEDBACK:
            ---------------
            Critic A: {critic_feedback.get('critic_A_summary', '')}
            Critic B: {critic_feedback.get('critic_B_summary', '')}

            Discussion: {critic_feedback.get('discussion_transcript', '')}

            Please incorporate the key insights from this feedback into your writing.
            """))

    # Always provide raw ending discipline snippet so model mirrors exact beat
    if raw_ending:
        user_parts.append(textwrap.dedent(f"""\
            RAW ENDING (last ≈60 words):
            ---------------------------
            {raw_ending}

            Your final sentence must conclude on the *same narrative beat*.
            Absolutely forbid introduction of foreshadowing or closure that is
            absent in the RAW ENDING.
            """))

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)}
    ]

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
def draft_name(persona: str, sample: bool, version: int) -> str:
    tag = "_sample" if sample else ""
    return f"{persona}{tag}_v{version}.txt"

def latest_version(folder: DIR, persona: str, sample: bool) -> int:
    tag = "_sample" if sample else ""
    drafts = sorted(folder.glob(f"{persona}{tag}_v*.txt"))
    if not drafts:
        return 0
    return int(re.search(r"_v(\d+)", drafts[-1].stem)[1])

# ── main actions ────────────────────────────────────────────────────────────
def make_first_draft(text: str, chap_id: str, args, voice_spec: str,
                     prev_final: Optional[str], critic_feedback: Optional[dict] = None) -> pathlib.Path:
    # sample truncation
    if args.sample:
        text = " ".join(text.split()[: args.sample])
    # Determine reference length: use previous draft if available to preserve
    # pacing; otherwise base it on RAW text.
    reference_text = prev_final if prev_final else text
    src_words = len(reference_text.split())
    target_words = args.target_words or int(src_words * args.target_ratio)
    length_hint = f"Match the source length within ±10 % (≈{target_words} words)."
    max_toks = estimate_max_tokens(target_words)

    include_raw = prev_final is None

    # extract raw ending ~60 words
    raw_ending = " ".join(text.split()[-60:]) if include_raw else None

    prompt = build_author_prompt(text, voice_spec, length_hint,
                                 prev_final, args.persona, critic_feedback,
                                 include_raw=include_raw,
                                 raw_ending=raw_ending)
    draft = call_llm(prompt, temp=0.7, max_tokens=max_toks)

    # For auditions, write to the audition directory
    if args.audition_dir:
        folder = args.audition_dir
        # Use chapter ID as filename for audition drafts
        path = folder / f"{chap_id}.txt"
    else:
        # Regular mode uses the chapter directory
        folder = OUT / chap_id
        folder.mkdir(parents=True, exist_ok=True)
        fname = draft_name(args.persona, bool(args.sample), 1)
        path = folder / fname
    
    write_utf8(path, draft)
    return path

def make_revision(chap_id: str, args, voice_spec: str) -> pathlib.Path:
    notes = json.loads(read_utf8(args.revise))
    if not any(k in notes for k in ("rewrite", "cut", "keep")):
        die("Revision notes must have at least 'rewrite', 'cut' or 'keep'.")

    folder = OUT / chap_id
    v_now  = latest_version(folder, args.persona, bool(args.sample))
    if v_now == 0:
        die("No existing draft to revise.")

    current = read_utf8(folder / draft_name(args.persona, bool(args.sample), v_now))
    max_toks = estimate_max_tokens(len(current.split()))
    prompt = build_revision_prompt(current, notes, voice_spec)
    new_draft = call_llm(prompt, temp=0.4, max_tokens=max_toks)

    fname = draft_name(args.persona, bool(args.sample), v_now + 1)
    path  = folder / fname
    write_utf8(path, new_draft)
    return path

# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("chapter", help="Chapter id (lotm_0006) or path to JSON/TXT")
    p.add_argument("--spec", type=DIR, required=True,
                   help="Voice spec markdown file")
    p.add_argument("--persona", help="Persona label for auditions")
    p.add_argument("--sample", type=int,
                   help="Use only first N words of RAW SOURCE")
    p.add_argument("--target-words", type=int)
    p.add_argument("--target-ratio", type=float, default=1.0)
    p.add_argument("--prev", type=DIR, help="Previous locked chapter")
    p.add_argument("--revise", type=DIR,
                   help="JSON notes file from critic/auditor")
    p.add_argument("--audition-dir", type=DIR,
                   help="Directory for audition drafts (e.g. drafts/auditions/persona_1)")
    p.add_argument("--critic-feedback", type=DIR,
                   help="JSON file containing critic feedback for final version")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    chap_path = resolve_chapter(args.chapter)
    raw_text, chap_id = load_raw_text(chap_path)

    # ── voice spec resolution ─────────────────────────────────────────────
    spec_path = args.spec
    if not spec_path.exists():
        die(f"Voice spec not found: {spec_path}")
    voice_spec = read_utf8(spec_path)

    prev_final = read_utf8(args.prev) if args.prev and args.prev.exists() else None
    
    # Load critic feedback if provided
    critic_feedback = None
    if args.critic_feedback and args.critic_feedback.exists():
        critic_feedback = json.loads(read_utf8(args.critic_feedback))

    if args.revise:
        out = make_revision(chap_id, args, voice_spec)
        log.info("✔ revision → %s", out)
    else:
        out = make_first_draft(raw_text, chap_id, args, voice_spec, prev_final, critic_feedback)
        log.info("✔ draft → %s", out)

if __name__ == "__main__":
    main()
