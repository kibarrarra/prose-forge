#!/usr/bin/env python

# --- DEBUGGING BLOCK ---
# import sys
# import os
# print(f"--- DEBUG: writer.py starting ---", file=sys.stderr)
# print(f"CWD: {os.getcwd()}", file=sys.stderr)
# print(f"sys.path: {sys.path}", file=sys.stderr)
# print(f"-------------------------------", file=sys.stderr)
# --- END DEBUGGING BLOCK ---

from __future__ import annotations

"""
writer.py - Create or revise a chapter draft according to voice_spec.md.

Core modes
──────────
1. First draft            $ writer.py lotm_0006
2. Audition (first 2k w)  $ writer.py lotm_0001 --sample 2000 --persona lovecraft
3. Revision pass          $ writer.py lotm_0006 --revise notes/lotm_0006.json
"""

import argparse, json, math, pathlib, re, sys, textwrap
from utils.paths import RAW_DIR, SEG_DIR, CTX_DIR, DRAFT_DIR, CONFIG_DIR
from typing import Optional, TypedDict
from utils.io_helpers import read_utf8, write_utf8, normalize_text
from utils.llm_client import get_llm_client
from ftfy import fix_text
import os
import time


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
client = get_llm_client()

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

# ── raw ending extractor (≈60 words) ─────────────────────────────────────────

def extract_raw_ending(chap_id: str) -> str | None:
    """Return last ≈60 words from the canonical raw text for *chap_id*, or
    None if raw text not found.  This is used during revision passes to make
    sure the ending narrative beat remains aligned with the original source.
    """
    # Prefer JSON if available, then segments, then context plain text.
    json_path = RAW / f"{chap_id}.json"
    if json_path.exists():
        raw_text, _ = load_raw_text(json_path)
        return " ".join(raw_text.split()[-60:])

    # Segments or context
    segs = sorted(SEG.glob(f"{chap_id}_p*.txt"))
    if segs:
        raw_text = "\n\n".join(read_utf8(p) for p in segs)
    else:
        ctx_path = CTX / f"{chap_id}.txt"
        if not ctx_path.exists():
            return None
        raw_text = read_utf8(ctx_path)

    return " ".join(raw_text.split()[-60:])

def segment_text(text: str, chunk_words: int = 250) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i+chunk_words])
            for i in range(0, len(words), chunk_words)]

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

    # Always provide raw ending discipline snippet so model mirrors exact beat
    if raw_ending:
        user_parts.append(textwrap.dedent(f"""\
            RAW ENDING (last ≈60 words):
            ---------------------------
            {raw_ending}

            Do NOT add any interpretation, foreshadowing, or sense of closure
            that is absent in the RAW ENDING. Maintain its exact tone and
            level of uncertainty or suspense.
            """))

    # ────────────────────────────────────────────────────
    # SELF-CHECK to catch hallucinations / new elements
    # ────────────────────────────────────────────────────
    # Check if a custom self-check is provided via environment variable
    self_check = os.environ.get("WRITER_SELF_CHECK_OVERRIDE", textwrap.dedent("""\
        SELF-CHECK:
        List, in bullet form, any line that introduces a new object, event, or
        future plan that was not present in the RAW. Then rewrite the draft to
        remove them.  Return the revised draft only—no extra commentary or labels.
        **CRITICAL**: Start the output directly with the chapter text. Do not include preambles like "Here is the draft...".
        """))
    
    user_parts.append(self_check)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)}
    ]

def build_segment_author_prompt(raw_segments: list[str],
                                voice_spec: str,
                                length_hint: str,
                                persona: str | None,
                                raw_ending: str) -> list[dict]:
    persona_note = f" as {persona}" if persona else ""
    system = f"""You are 'Chapter-Author'{persona_note}.
Follow the voice spec. {length_hint}
You will rewrite the RAW text by applying the VOICE SPEC to each segment.
The primary goal is to transform the raw content into a polished narrative 
that fully embodies the VOICE SPEC, while preserving all core narrative events, 
character actions, and essential descriptive details from the RAW segments.

VOICE SPEC
----------
{voice_spec}
"""

    # assemble labelled segments
    labelled = []
    for idx, seg in enumerate(raw_segments, 1):
        labelled.append(f"[S{idx}]\n{seg}")

    user = f"""RAW SEGMENTS ({len(raw_segments)} total)
+---------------------------------------
+{'\n\n'.join(labelled)}

RAW ENDING (last ≈60 w)
+-----------------------
+{raw_ending}

INSTRUCTIONS
1. Work in order S1 → S{len(raw_segments)}.
   • For each segment, rewrite it to fully embody the VOICE SPEC. Preserve its core narrative events, character actions, and essential descriptive details.
   • While the word count of your rewritten segment should be *roughly comparable* to the original RAW segment, prioritize achieving the stylistic goals of the VOICE SPEC (e.g., fluidity, imagery, tone, pacing) over strict word-for-word or sentence-for-sentence matching for each individual segment.
   • Even if a segment's meaning is clear in the RAW text, ensure its prose is *fully transformed* to align with the VOICE SPEC. Verbatim sentences from the RAW text should be rare and only used if they already perfectly match the target voice and style.
   • Focus on making transitions between sentences and ideas *within* each rewritten segment smooth, natural, and stylistically consistent with the VOICE SPEC, rather than just rephrasing sentence by sentence.
2. Preserve every plot beat and all factual details from the RAW source across the entire chapter.
3. After processing all segments, perform a SELF-CHECK:
   – Ensure the overall chapter's total word count is within ±20% of the original RAW text's total word count ({length_hint.split('≈')[-1].split(' ')[0]} words). Expand or trim sentences/phrases across segments if needed to meet this target, but do so in a way that maintains stylistic integrity and narrative coherence.
   – Ensure the final sentence ends on **the identical narrative beat** shown in RAW ENDING (no extra closure or foreshadowing).
4. Output the full chapter with *no segment labels* and no commentary.
   **CRITICAL**: Start the output directly with the chapter text. Do not include preambles like "Here is the draft...".
"""

    return [{"role": "system", "content": system},
            {"role": "user",   "content": user}]

def build_revision_prompt(current: str, change_list: dict, voice_spec: str, raw_ending: str | None = None) -> list[dict]:
    system = textwrap.dedent(f"""\
You are the same 'Chapter-Author'.
You MUST apply every change listed under "must" exactly as specified—no omissions.
You MAY apply changes under "nice" if they genuinely improve clarity, mood, or pacing.
Do NOT introduce new plot points, foreshadowing, or factual inconsistencies outside the RAW ending beat.
You MUST keep the word count approximately the same as the previous draft. You should strive to make the fewest possible edits while accommodating editor demands.
---
VOICE SPEC
----------
{voice_spec}
----------
        """)

    user_parts = [textwrap.dedent(f"""\
PREVIOUS DRAFT:
{current}

CHANGE LIST (JSON):
{json.dumps(change_list, indent=2, ensure_ascii=False)}
        """)]

    if raw_ending:
        user_parts.append(textwrap.dedent(f"""\
RAW ENDING (last ≈60 words):
---------------------------
{raw_ending}
---------------------------
Do NOT add any interpretation, foreshadowing, or sense of closure
that is absent in the RAW ENDING. Maintain its exact tone and
level of uncertainty or suspense.
            """))

    # ────────────────────────────────────────────────────
    # SELF-CHECK to ensure MUST edits & no hallucinations
    # ────────────────────────────────────────────────────
    # Check if a custom self-check is provided via environment variable
    default_self_check = textwrap.dedent("""\
SELF-CHECK:
1. List, in bullet form, any MUST item that remains unimplemented.
2. List any new object, event, or future plan that was not present in the PREVIOUS DRAFT.
Then rewrite the draft to fix these issues.  Return FINAL only—no extra commentary or labels.
**CRITICAL**: Start the output directly with the chapter text. Do not include preambles like "Here is the draft...".
        """)
    
    self_check = os.environ.get("WRITER_SELF_CHECK_OVERRIDE", default_self_check)
    
    user_parts.append(self_check)

    user = "\n\n".join(user_parts)

    return [{"role": "system", "content": system},
            {"role": "user",   "content": user}]

def call_llm(msgs: list[dict], temp: float, max_tokens: int, model: str) -> str:
    MAX_RETRIES = 3
    INITIAL_DELAY_SECS = 1
    
    # Save the prompts to a log file for debugging
    log_dir = pathlib.Path("logs/prompts")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"prompt_{timestamp}_{model.replace('-', '_')}.txt"
    
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"MODEL: {model}\n")
        f.write(f"TEMP: {temp}\n")
        f.write(f"MAX_TOKENS: {max_tokens}\n\n")
        
        for msg in msgs:
            f.write(f"--- {msg['role'].upper()} ---\n\n")
            f.write(msg['content'])
            f.write("\n\n")
    
    log.info(f"Prompt saved to {log_file}")

    delay = INITIAL_DELAY_SECS
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            res = client.chat.completions.create(
                model=model,
                temperature=temp,
                messages=msgs,
                max_tokens=max_tokens
            )
            # If we get here, API call succeeded - try to parse response
            try:
                if not res.choices:
                    log.error(f"LLM call for model {model} returned no choices.")
                    raise ValueError("LLM response contained no choices.")

                choice = res.choices[0]
                
                completion_reason = None
                if hasattr(choice, 'finish_reason'): # OpenAI SDK standard
                    completion_reason = choice.finish_reason
                elif hasattr(choice, 'stop_reason'): # Anthropic SDK standard (if adapter places it here)
                    completion_reason = choice.stop_reason
                
                if completion_reason:
                    log.info(f"LLM call completion_reason: {completion_reason} for model {model}")
                    # Check for truncation reasons from either OpenAI or Anthropic
                    if completion_reason == "length" or completion_reason == "max_tokens": 
                        log.warning(f"LLM output was truncated due to token limit for model {model}.")
                else:
                    log.warning(f"Could not determine completion reason for model {model}. "
                                f"Choice object type: {type(choice)}, attributes: {dir(choice)}")

                if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                    content = choice.message.content.strip()
                    # Normalize special characters in the LLM response
                    return normalize_text(content)
                else:
                    log.error(f"LLM choice object for model {model} lacks expected 'message.content' structure. Choice: {choice}")
                    raise ValueError("LLM response choice lacks 'message.content'.")
                    
            except Exception as e:
                # Don't retry on response parsing errors
                log.error("Failed to parse LLM response: %s", e)
                raise
                
        except Exception as e:
            last_error = e
            if attempt == MAX_RETRIES - 1:
                log.error("Max retries reached for LLM call.")
                raise last_error
            
            # Log warning with attempt number and specific error
            log.warning("LLM call failed (attempt %d/%d), retrying in %d s: %s", 
                        attempt + 1, MAX_RETRIES, delay, e)
            time.sleep(delay)
            delay *= 2  # Exponential backoff

    # Should not be reached if MAX_RETRIES > 0, but satisfies type checker
    raise RuntimeError("LLM call failed after multiple retries")

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
                     prev_final: Optional[str]) -> pathlib.Path:
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

    # Determine prompt based on whether segmented drafting is enabled
    if args.segmented_first_draft:
        raw_segs = segment_text(text, args.chunk_size or 250)
        # Ensure raw_ending is extracted from the full original text
        raw_ending_full = " ".join(text.split()[-60:])
        prompt = build_segment_author_prompt(raw_segs,
                                             voice_spec,
                                             length_hint,
                                             args.persona,
                                             raw_ending_full)
    else:
        # Standard author prompt (uses raw_ending extracted earlier)
        prompt = build_author_prompt(text, voice_spec, length_hint,
                                     prev_final, args.persona,
                                     include_raw=include_raw,
                                     raw_ending=raw_ending)

    draft = call_llm(prompt, temp=0.5, max_tokens=max_toks, model=args.model)

    # Ensure text is properly normalized to handle special characters
    draft = normalize_text(draft)

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
    if not args.critic_feedback or not args.critic_feedback.exists():
        die("Revision mode requires --critic-feedback JSON file produced by editor_panel.")

    feedback = json.loads(read_utf8(args.critic_feedback))
    change_list = feedback.get("change_list", {})
    if not change_list.get("must") and not change_list.get("nice"):
        die("Change list missing or empty 'must' edits.")

    # Determine where the drafts are stored. If audition_dir is provided we
    # operate in-place inside that folder, otherwise use the standard
    # chapter directory under DRAFT_DIR.
    if args.audition_dir:
        folder = args.audition_dir
        # In audition mode, the 'current' text comes from the --prev argument's file.
        if not args.prev or not args.prev.exists():
            die(f"Revision in audition mode requires a valid --prev file. Not found: {args.prev}")
        current = read_utf8(args.prev)
        current_path = folder / f"{chap_id}.txt" # This is the *output* path
    else:
        folder = OUT / chap_id
        v_now  = latest_version(folder, args.persona, bool(args.sample))
        if v_now == 0:
            die("No existing draft to revise.")
        current_path = folder / draft_name(args.persona, bool(args.sample), v_now)
        current = read_utf8(current_path)

    raw_ending = extract_raw_ending(chap_id)
    max_toks = estimate_max_tokens(len(current.split()))
    prompt = build_revision_prompt(current, change_list, voice_spec, raw_ending)
    new_draft = call_llm(prompt, temp=0.2, max_tokens=max_toks, model=args.model)

    # Ensure text is properly normalized to handle special characters
    new_draft = normalize_text(new_draft)

    if args.audition_dir:
        # Overwrite the file directly for audition mode
        write_utf8(current_path, new_draft)
        return current_path
    else:
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
    p.add_argument("--audition-dir", type=DIR,
                   help="Directory for audition drafts (e.g. drafts/auditions/persona_1)")
    p.add_argument("--critic-feedback", type=DIR,
                   help="JSON file containing critic feedback for final version")
    p.add_argument("--model", type=str, default=os.getenv("WRITER_MODEL", "claude-3-opus-20240229"),
                   help="LLM model name to use (e.g. gpt-4o, claude-3-opus-20240229)")
    p.add_argument("--segmented-first-draft", action="store_true",
                   help="Enable segmented first draft mode")
    p.add_argument("--chunk-size", type=int,
                   help="Chunk size for segmented first draft mode")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    chap_path = resolve_chapter(args.chapter)
    raw_text, chap_id = load_raw_text(chap_path)

    # Debug output to help diagnose logging issues
    log.info("Writer args: critic_feedback=%s, prev=%s", 
             args.critic_feedback, args.prev)

    # ── voice spec resolution ─────────────────────────────────────────────
    spec_path = args.spec
    if not spec_path.exists():
        die(f"Voice spec not found: {spec_path}")
    voice_spec = read_utf8(spec_path)

    prev_final = read_utf8(args.prev) if args.prev and args.prev.exists() else None
    
    if args.critic_feedback and args.critic_feedback.exists():
        critic_feedback = json.loads(read_utf8(args.critic_feedback))
    else:
        critic_feedback = None

    if args.critic_feedback:
        out = make_revision(chap_id, args, voice_spec)
        log.info("✔ revision → %s", out)
    else:
        out = make_first_draft(raw_text, chap_id, args, voice_spec, prev_final)
        log.info("✔ draft → %s", out)

if __name__ == "__main__":
    main()
