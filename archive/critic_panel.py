#!/usr/bin/env python
"""
critic_panel.py – two critics discuss, converge, and output new voice_spec.md
STDOUT is a JSON object:
{
  "critic_A_summary": "...",
  "critic_B_summary": "...",
  "discussion_transcript": "...",
  "accepted": true|false
}
"""

import argparse, json, pathlib, textwrap, os
from utils.io_helpers import read_utf8
from utils.paths import CTX_DIR
from utils.logging_helper import get_logger
from utils.llm_client import get_llm_client

import tiktoken

log = get_logger()
MODEL = "gpt-4.1-mini"   # cheap for discussion

client = get_llm_client()

def count_tokens(text: str) -> int:
    """Count tokens in text using GPT-4's tokenizer."""
    enc = tiktoken.encoding_for_model("gpt-4")
    return len(enc.encode(text))

def load_bundle(dir: pathlib.Path) -> tuple[str, str, int]:
    """Return a combined string containing RAW + REWRITE for each chapter, the
    voice spec markdown, and the total token count used.  Incorporates RAW
    source from CTX_DIR so critics can evaluate continuity and naming
    consistency against the original text."""

    combined_sections: list[str] = []
    total_tokens = 0

    # ── voice spec ───────────────────────────────────────────────────────
    spec_path = dir / "voice_spec.md"  # canonical name within audition round
    if not spec_path.exists():
        legacy = dir / "voice_spec_used.md"
        if legacy.exists():
            spec_path = legacy
            log.warning("Using legacy spec name: %s", legacy.name)

    spec = read_utf8(spec_path)
    total_tokens += count_tokens(spec)

    # ── per-chapter RAW + REWRITE bundles ────────────────────────────────
    model_context_limit = 28000  # ≈32k window minus safety margin for replies

    for draft_path in sorted(dir.glob("lotm_*.txt")):
        chap_id = draft_path.stem  # e.g. lotm_0001

        # Load rewritten draft
        rewrite_text = read_utf8(draft_path)
        rewrite_tokens = count_tokens(rewrite_text)

        # Load corresponding RAW source (best-effort)
        raw_path = CTX_DIR / f"{chap_id}.txt"
        if raw_path.exists():
            raw_text = read_utf8(raw_path)
            raw_tokens = count_tokens(raw_text)
        else:
            raw_text = "[RAW SOURCE NOT FOUND]"
            raw_tokens = 0
            log.warning("Raw context missing for %s", chap_id)

        # Abort if adding this chapter would exceed model context window
        if total_tokens + rewrite_tokens + raw_tokens > model_context_limit:
            log.warning("Token limit reached, stopping at %s", chap_id)
            break

        section = textwrap.dedent(f"""
            # {chap_id}

            ## RAW SOURCE
            {raw_text}

            ## REWRITE
            {rewrite_text}
            """)
        combined_sections.append(section.strip())
        total_tokens += rewrite_tokens + raw_tokens

    return "\n\n".join(combined_sections), spec, total_tokens

def chat(system, user):
    res = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}]
    )
    return res.choices[0].message.content.strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft-dir", required=True)
    ap.add_argument("--round", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    drafts, spec, token_count = load_bundle(pathlib.Path(args.draft_dir))
    log.info("Total context tokens: %d", token_count)

    model_context_limit = 28000  # keep in sync with load_bundle
    if token_count > model_context_limit:
        log.warning("Context tokens (%d) exceed model limit %d; analysis will truncate", token_count, model_context_limit)

    rubric = textwrap.dedent("""
        Please review each REWRITE in comparison to its RAW SOURCE and provide
        detailed feedback in the following format:

        ### Scores (1-5)
        - **Clarity and Pacing**: Narrative flow and accessibility.
        - **Atmosphere / Dread Tone**: Effectiveness of horror or mood elements
        - **Verboseness**: Balance between detail and conciseness
        - **Redundancy**: Unnecessary repetition or filler
        - **Continuity & Consistency**: Fidelity to plot details, character names,
          and overall continuity with RAW SOURCE. Take special care to ensure that 
          the end of the chapter hits the same narrative tone as the RAW end. Do
          not allow closure or forewarning if there is none in the RAW.

        ### Detailed Analysis
        For each scoring category:
        1. Explain your rating
        2. Quote specific examples from REWRITE (and RAW if relevant)
        3. Provide concrete, actionable improvement suggestions

        ### Top Issues To Address
        Conclude with a bullet list of the five most important revisions the
        author should make next.
    """)

    summary_A = chat(
        "You are Critic A, focused on technical writing quality and clarity. "
        "Your analysis should be precise, with concrete examples and specific improvement suggestions. "
        "Focus on sentence structure, readability, and maintaining narrative flow while enhancing clarity.",
        f"{rubric}\n\nVOICE SPEC:\n{spec}\n\nTEXT BUNDLE (RAW + REWRITE):\n{drafts}"
    )
    
    summary_B = chat(
        "You are Critic B, focused on creative writing and atmosphere. "
        "Your analysis should emphasize the emotional impact, atmospheric elements, and psychological depth. "
        "Focus on enhancing existing elements while maintaining narrative coherence.",
        f"{rubric}\n\nVOICE SPEC:\n{spec}\n\nTEXT BUNDLE (RAW + REWRITE):\n{drafts}"
    )

    discussion = chat(
        "You are Critic A and Critic B in turn. Hold up to three back-and-forths. "
        "Your goal is to converge on a prioritized list of improvements that will "
        "enhance clarity, atmosphere, conciseness, and especially continuity with "
        "the RAW SOURCE while respecting the VOICE SPEC. Conclude with a bullet list "
        "of concrete next-step revisions (max 5 bullets).",
        f"CRITIC A:\n{summary_A}\n\nCRITIC B:\n{summary_B}"
    )

    out = {
        "critic_A_summary": summary_A,
        "critic_B_summary": summary_B,
        "discussion_transcript": discussion,
        "accepted": True
    }
    
    output_path = pathlib.Path(args.output)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
