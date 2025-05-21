#!/usr/bin/env python
"""
editor_panel.py – Editors provide inline comments on drafts compared to RAW.

This differs from critic_panel.py (reviewer) in that the output is intended to
be fed back into the writer for iterative improvement.  Therefore the editors
MUST embed *inline* comments inside each REWRITE section, ideally using the
format  [[COMMENT: …]]  immediately after the text they address.

STDOUT / output file is a JSON object identical in structure to critic_panel so
that downstream scripts remain compatible:
{
  "critic_A_summary": "… annotated rewrite …",
  "critic_B_summary": "… annotated rewrite …",
  "discussion_transcript": "…",
  "accepted": true
}
The summaries contain the fully annotated draft for each critic so the writer
LLM can reference concrete, line-level feedback.
"""

import argparse, json, pathlib, textwrap, os, re
from utils.io_helpers import read_utf8
from utils.paths import CTX_DIR
from utils.logging_helper import get_logger
from utils.llm_client import get_llm_client

TEST_MODE = bool(os.getenv("PF_TEST_MODE"))

client = get_llm_client(test_mode=TEST_MODE)

import tiktoken

log = get_logger()
# Allow override via environment variable so we can test different models
# without touching the source code. Falls back to the previous default.
MODEL = os.getenv("EDITOR_MODEL", "gpt-4o-mini")   # cheap for discussion / annotation

def count_tokens(text: str) -> int:
    """Count tokens in text using GPT-4's tokenizer."""
    enc = tiktoken.encoding_for_model("gpt-4")
    return len(enc.encode(text))

def load_bundle(dir: pathlib.Path) -> tuple[str, str, int]:
    """Return (combined RAW+REWRITE bundle, voice_spec, total_tokens).
    RAW text is included so the editor can verify continuity but **should not**
    annotate the RAW section – only the REWRITE.
    """

    combined_sections: list[str] = []
    total_tokens = 0

    # ── voice spec ───────────────────────────────────────────────────────
    spec_path = dir / "voice_spec.md"
    if not spec_path.exists():
        legacy = dir / "voice_spec_used.md"
        if legacy.exists():
            spec_path = legacy
            log.warning("Using legacy spec name: %s", legacy.name)

    spec = read_utf8(spec_path)
    total_tokens += count_tokens(spec)

    # ── per-chapter RAW + REWRITE bundle ────────────────────────────────
    model_context_limit = 28000

    for draft_path in sorted(dir.glob("lotm_[0-9][0-9][0-9][0-9].txt")):
        chap_id = draft_path.stem  # e.g. lotm_0001

        rewrite_text = read_utf8(draft_path)
        rewrite_tokens = count_tokens(rewrite_text)

        raw_path = CTX_DIR / f"{chap_id}.txt"
        if raw_path.exists():
            raw_text = read_utf8(raw_path)
            raw_tokens = count_tokens(raw_text)
        else:
            raw_text = "[RAW SOURCE NOT FOUND]"
            raw_tokens = 0
            log.warning("Raw context missing for %s", chap_id)

        if total_tokens + rewrite_tokens + raw_tokens > model_context_limit:
            log.warning("Token limit reached, stopping at %s", chap_id)
            break

        section = textwrap.dedent(f"""
            # {chap_id}

            ## RAW SOURCE (reference only – **do NOT annotate**)
            {raw_text}

            ## REWRITE (add inline comments with [[COMMENT: …]])
            {rewrite_text}
            """)
        combined_sections.append(section.strip())
        total_tokens += rewrite_tokens + raw_tokens

    return "\n\n".join(combined_sections), spec, total_tokens

def chat(system: str, user: str) -> str:

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

    model_context_limit = 28000
    truncated = token_count > model_context_limit
    if truncated:
        log.warning("Context tokens (%d) exceed model limit %d; analysis was truncated", token_count, model_context_limit)

    rubric = textwrap.dedent("""
        You are an EDITOR reviewing a REWRITE section against its RAW SOURCE.

        Your **primary goal** is to identify areas for improvement and formulate a
        clear, actionable list of edits for the author.

        Focus your review on: clarity, pacing, atmosphere, continuity with RAW,
        and adherence to the VOICE SPEC.

        **Optional:** You MAY add brief inline notes like [[COMMENT: ...]] right after
        a specific phrase *if* it helps clarify an issue for your later summary or
        for the other critic during discussion. These notes are for context only.

        **Required Output:** After reviewing the REWRITE text (and adding any optional
        inline notes), you MUST output **ONLY** two bullet sections (no full
        rewrite text!):

           MUST:
             - one bullet per mandatory change (max 5)
           
           NICE:
             - optional improvements worth considering later.
           
           Keep bullets concise (≤100 words each) and clearly actionable.
           Reference specific parts of the text if needed for clarity.

        Return ONLY the MUST and NICE bullet lists. Add NO other prose, no
        rewritten text.
    """)

    summary_A = chat(
        """You are Critic A, a meticulous copy-editor focused on 
        sentence-level clarity and concision.""",
        f"{rubric}\n\nVOICE SPEC:\n{spec}\n\nTEXT BUNDLE (RAW + REWRITE):\n{drafts}"
    )

    summary_B = chat(
        """You are Critic B, an atmospheric editor spotlighting mood, 
        imagery, and emotional cadence.""",
        f"{rubric}\n\nVOICE SPEC:\n{spec}\n\nTEXT BUNDLE (RAW + REWRITE):\n{drafts}"
    )

    discussion = chat(
        """You are Critic A and Critic B in turn. Hold up to three short
        back-and-forths to agree on the *highest-impact* edits.

        Conclude with two bullet lists:
          1) MUST – the five edits that must be applied (max 5)
          2) NICE – optional improvements worth considering.

        Keep bullets concise (≤100 words each) and clearly actionable.
        Reference specific parts of the text if needed for clarity.
        """,
        textwrap.dedent(
            f"""
            VOICE SPEC:
            ----------
            {spec}

            TEXT BUNDLE (RAW + REWRITE):
            ----------------------------------------
            {drafts}

            PREVIOUS BULLET LISTS FROM EACH CRITIC:
            ----------------------------------------
            CRITIC A:
            {summary_A}

            CRITIC B:
            {summary_B}
            """
        )
    )

    # ── extract bullet list from discussion ─────────────────────────────
    # Regex to match lines starting with markdown bullets OR numbers+dot
    bullet_re = re.compile(r"^(?:[\-*•]|\d+\.)\s+(.*)")
    must_edits: list[str] = []
    nice_edits: list[str] = []
    in_nice_section = False
    for line in (l.strip() for l in discussion.splitlines()):
        if not line:
            continue
        # Heuristic: if the bullet list starts with "(nice)" or we reach a heading
        # like "NICE:" or "### NICE"
        nice_markers = ["nice-to-have", "nice:", "### nice"]
        if any(line.lower().startswith(marker) for marker in nice_markers):
            in_nice_section = True
            continue
        m = bullet_re.match(line)
        if m:
            (nice_edits if in_nice_section else must_edits).append(m.group(1).strip())

    change_list = {"must": must_edits, "nice": nice_edits}

    # ── acceptance heuristic ────────────────────────────────────────────
    # 1. Reject if we had to truncate the input bundle.
    # 2. Reject if the critics failed to enumerate any mandatory edits
    #    (we expect a bullet list like "- edit" or "• edit" at the end).
    has_bullets = any(mark in discussion for mark in ("- ", "•", "* "))
    accepted = (not truncated) and has_bullets

    out = {
        "critic_A_summary": summary_A,
        "critic_B_summary": summary_B,
        "discussion_transcript": discussion,
        "change_list": change_list,
        "accepted": accepted
    }

    log.info("Marked draft as %s", "ACCEPTED" if accepted else "REJECTED")

    output_path = pathlib.Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main() 