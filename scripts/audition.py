#!/usr/bin/env python
"""
audition.py – Generate specimen drafts for a list of personae
                 on the first three chapters (full length).

Outputs:
    drafts/<chap>/<persona>.txt, sample is *not* used.

Default personae are every *.md in config/voice_specs/.
"""

import argparse, itertools, pathlib, subprocess, sys

VOICE_DIR = pathlib.Path("config/voice_specs")
WRITER    = pathlib.Path("scripts/writer.py")
DEFAULT_CHAPS = [f"lotm_{i:04d}" for i in range(1, 4)]   # 0001–0003

def list_personae():
    return [p.stem for p in VOICE_DIR.glob("*.md")]

def call_writer(chapter: str, persona: str):
    cmd = [
        sys.executable, str(WRITER),
        chapter,
        "--persona", persona
    ]
    print("·", " ".join(cmd))
    subprocess.run(cmd, check=True)

def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--chapters", nargs="+", default=DEFAULT_CHAPS,
                    help="Chapter IDs (default: first three)")
    ap.add_argument("--persona", nargs="+", default=list_personae(),
                    help="One or more persona labels (spec filenames w/out .md)")
    
    args = ap.parse_args()

    for chap, persona in itertools.product(args.chapters, args.persona):
        call_writer(chap, persona)

if __name__ == "__main__":
    main()
