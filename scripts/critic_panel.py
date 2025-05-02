#!/usr/bin/env python
"""
critic_panel.py – two critics discuss, converge, and output new voice_spec.md
STDOUT is a JSON object:
{
  "critic_A_summary": "...",
  "critic_B_summary": "...",
  "discussion_transcript": "...",
  "updated_spec_md": "### 1 Bedrock clarity ...",
  "accepted": true|false
}
"""

import argparse, json, pathlib, textwrap, os
from utils.io_helpers import read_utf8, write_utf8
from utils.paths import CTX_DIR

import httpx
from openai import OpenAI
from dotenv import load_dotenv ; load_dotenv()

MODEL = "gpt-4o-mini"   # cheap for discussion

# ── OpenAI client ────────────────────────────────────────────────────────────
timeout = httpx.Timeout(
    connect=30.0,
    read=600.0,
    write=600.0,
    pool=60.0
)

client = OpenAI(timeout=timeout)

def load_bundle(dir: pathlib.Path) -> str:
    texts = []
    for f in sorted(dir.glob("lotm_*.txt")):
        texts.append(f"# {f.stem}\n" + read_utf8(f))
    spec = read_utf8(dir / "voice_spec.md")
    return "\n\n".join(texts), spec

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
    args = ap.parse_args()

    drafts, spec = load_bundle(pathlib.Path(args.draft_dir))

    rubric = textwrap.dedent("""
        Score 1-5 on: clarity, dread tone, verboseness, redundancy.
        Suggest concrete spec edits in markdown bullet form.
        End your response with a markdown-formatted voice spec update.
    """)

    summary_A = chat("You are Critic A.", f"{rubric}\n\nSPEC:\n{spec}\n\nDRAFTS:\n{drafts}")
    summary_B = chat("You are Critic B.", f"{rubric}\n\nSPEC:\n{spec}\n\nDRAFTS:\n{drafts}")

    discussion = chat(
        "You are Critic A and Critic B in turn. Hold up to 3 back-and-forths. "
        "End with a markdown-formatted voice spec update when consensus is reached.",
        f"CRITIC A:\n{summary_A}\n\nCRITIC B:\n{summary_B}"
    )

    # Try to extract the new spec from the discussion
    # First try to find a markdown block
    if "```" in discussion:
        new_spec = discussion.split("```")[-2].strip()
    else:
        # If no markdown block, look for the last section that looks like a spec
        lines = discussion.split("\n")
        spec_start = None
        for i, line in enumerate(lines):
            if line.startswith("#") or line.startswith("##"):
                spec_start = i
        if spec_start is not None:
            new_spec = "\n".join(lines[spec_start:])
        else:
            # If we can't find a spec section, use the last paragraph
            new_spec = discussion.split("\n\n")[-1].strip()

    out = {
        "critic_A_summary": summary_A,
        "critic_B_summary": summary_B,
        "discussion_transcript": discussion,
        "updated_spec_md": new_spec,
        "accepted": True
    }
    
    # Ensure UTF-8 output
    import sys
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)

if __name__ == "__main__":
    main()
