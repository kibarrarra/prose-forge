#!/usr/bin/env python
"""
audition_and_review.py – 3-iteration voice-spec refinement loop

Usage:
    python scripts/audition_and_review.py cosmic_clarity 2  # persona name, chapters to write
"""

import subprocess, shutil, json, pathlib, sys
from utils.logging_helper import get_logger
from utils.paths import CTX_DIR, VOICE_DIR, ROOT

log = get_logger()
WRITER   = ROOT / "scripts" / "writer.py"
CRITIC   = ROOT / "scripts" / "critic_panel.py"   # two-critic dialog
MAX_ROUNDS = 3

def call_writer(out_dir: pathlib.Path, persona: str, chapters: list[str]):
    for ch in chapters:
        cmd = [sys.executable, str(WRITER), ch, "--persona", persona,
               "--spec", str(out_dir / "voice_spec.md"),
               "--audition-dir", str(out_dir)]
        log.info("RUN: %s", " ".join(cmd))
        subprocess.run(cmd, check=True, cwd=ROOT)

def copy_spec(persona: str, dst: pathlib.Path):
    src = VOICE_DIR / f"{persona}.md"
    shutil.copy(src, dst / "voice_spec.md")

def main():
    persona   = sys.argv[1]         # e.g. cosmic_clarity
    num_chaps = int(sys.argv[2])    # 2
    chapters  = [f"lotm_{i:04d}" for i in range(1, num_chaps+1)]

    for rnd in range(1, MAX_ROUNDS+1):
        out_dir = ROOT / "drafts" / "auditions" / f"{persona}_{rnd}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1) copy current spec snapshot
        copy_spec(persona, out_dir)

        # 2) writer generates drafts
        call_writer(out_dir, persona, chapters)

        # 3) critics read drafts + spec + context
        panel_notes = subprocess.check_output(
            [sys.executable, str(CRITIC),
            "--draft-dir", str(out_dir),
            "--round", str(rnd)]
        ).decode()

        manifest = out_dir / f"critic_round{rnd}.json"
        manifest.write_text(panel_notes, encoding="utf-8")
        log.info("critic notes saved → %s", manifest)

        # 4) extract new spec from panel output
        new_spec = json.loads(panel_notes)["updated_spec_md"]
        (VOICE_DIR / f"{persona}.md").write_text(new_spec, encoding="utf-8")
        log.info("voice spec updated for next round")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: run_loop.py persona chapters_to_write")
        sys.exit(1)
    main()
