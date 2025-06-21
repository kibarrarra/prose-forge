#!/usr/bin/env python
"""
polish.py  –  Writer-AI pass
Usage:  python scripts/polish.py lotm_0001  [--segdir data/segments]

• Reads the winning draft in  selected/<chap_id>.txt        (step-2 output)
• Reads paragraph source files in data/segments/<chap_id>_* (from segment.py)
• Rewrites each paragraph with chapter context.
• Writes polished draft to  rewrite/<chap_id>_v0.txt
"""

import argparse, pathlib, openai, textwrap, os, tqdm

client = openai.OpenAI()

PROMPT = textwrap.dedent("""\
    Full chapter context (do NOT rewrite):
    —
    {ctx}
    —

    Now rewrite the following paragraph to improve clarity and cadence
    while keeping names, facts, and word count ±10 %. 
    Output ONLY the rewritten paragraph.

    [[Paragraph]]
    {para}
""")

def polish_para(chapter_ctx: str, para_text: str) -> str:
    r = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[{"role": "user",
                   "content": PROMPT.format(ctx=chapter_ctx, para=para_text)}],
        max_tokens=800,
    )
    return r.choices[0].message.content.strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chap_id", help="e.g. lotm_0001")
    ap.add_argument("--segdir", default="data/segments",
                    help="Folder containing *_p###.txt paragraph files")
    args = ap.parse_args()

    chap_id  : str        = args.chap_id
    SEG_DIR  = pathlib.Path(args.segdir)
    ctx_path = pathlib.Path("selected") / f"{chap_id}.txt"
    out_dir  = pathlib.Path("rewrite")
    out_dir.mkdir(exist_ok=True)

    ctx_text = ctx_path.read_text(encoding="utf-8")

    # ---- collect paragraph files ------------------------------------------
    seg_files = sorted(SEG_DIR.glob(f"{chap_id}_p*.txt"))
    if not seg_files:
        raise SystemExit(f"No paragraph files found in {SEG_DIR} for {chap_id}")

    polished = []
    for seg in tqdm.tqdm(seg_files, desc=f"Polishing {chap_id}", unit="para"):
        polished.append(polish_para(ctx_text, seg.read_text()))

    out_path = out_dir / f"{chap_id}_v0.txt"
    out_path.write_text("\n\n".join(polished), encoding="utf-8")
    print("✔ polished draft →", out_path)

if __name__ == "__main__":
    openai.api_key = os.getenv("OPENAI_API_KEY")
    main()
