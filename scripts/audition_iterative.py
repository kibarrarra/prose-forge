#!/usr/bin/env python
"""
audition_iterative.py – Voice-spec audition loop that keeps the spec fixed

This script is similar to `audition_and_review.py` but *does not* let the critics
modify the voice specification. Instead, successive rounds pass the critic
feedback JSON back to the writer so that the drafts improve iteratively while
remaining anchored to the original `voice_spec.md`.

Typical usage:
    python scripts/audition_iterative.py cosmic_clarity 2 --rounds 2

That command will:
  • create two audition rounds (`drafts/auditions/cosmic_clarity_1` and `_2`)
  • in round 1 write the first drafts with the original spec
  • collect critic feedback for round 1
  • in round 2 call *writer* again with the *same* spec **plus** the critic
    feedback JSON from round 1
  • after the configured number of rounds, generate a *final* version in
    `drafts/final/cosmic_clarity` using the last critic feedback

You can then use `compare_versions.py` across different personae / specs.
"""

from __future__ import annotations

import argparse, json, os, pathlib, shutil, subprocess, sys
from utils.logging_helper import get_logger
from utils.paths import ROOT, VOICE_DIR
from utils.io_helpers import read_utf8, ensure_utf8_windows

# ── logging & constants ────────────────────────────────────────────────────
log = get_logger()
WRITER = ROOT / "scripts" / "writer.py"
CRITIC = ROOT / "scripts" / "critic_panel.py"
DEFAULT_ROUNDS = 2  # feedback iterations before the final pass

# ── helpers ────────────────────────────────────────────────────────────────

def copy_fixed_spec(persona: str, spec_dir: pathlib.Path) -> pathlib.Path:
    """Copy the canonical voice spec into *spec_dir* as `voice_spec.md`.

    Returns the path to the copied spec file.
    """
    src = VOICE_DIR / f"{persona}.md"
    if not src.exists():
        raise FileNotFoundError(f"Voice spec for persona '{persona}' not found: {src}")

    dst_spec = spec_dir / "voice_spec.md"
    shutil.copy(src, dst_spec)
    # No longer need to copy to _used.md or _std.md
    return dst_spec


def call_writer(out_dir: pathlib.Path, persona: str, chapters: list[str],
                spec_path: pathlib.Path, critic_feedback: pathlib.Path | None,
                prev_round_dir: pathlib.Path | None) -> None:
    """Invoke *writer.py* once per chapter.

    If *prev_round_dir* is provided, pass the previous draft file via --prev so
    the LLM can improve on the exact prior version rather than rewriting from
    scratch."""

    for ch in chapters:
        cmd = [sys.executable, str(WRITER), ch,
               "--persona", persona,
               "--spec", str(spec_path),
               "--audition-dir", str(out_dir)]

        if prev_round_dir is not None:
            prev_draft = prev_round_dir / f"{ch}.txt"
            if prev_draft.exists():
                cmd += ["--prev", str(prev_draft)]

        if critic_feedback and critic_feedback.exists():
            cmd += ["--critic-feedback", str(critic_feedback)]

        log.info("RUN: %s", " ".join(cmd))
        subprocess.run(cmd, check=True, cwd=ROOT)


def run_critic(draft_dir: pathlib.Path, rnd: int) -> pathlib.Path:
    """Run the critic panel for *draft_dir* and return the JSON manifest path."""
    out_path = draft_dir / f"critic_round{rnd}.json"
    cmd = [sys.executable, str(CRITIC),
           "--draft-dir", str(draft_dir),
           "--round", str(rnd),
           "--output", str(out_path)]
    log.info("RUN: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)
    return out_path


def create_final_version(persona: str, chapters: list[str],
                         last_round_dir: pathlib.Path) -> None:
    """Generate the final drafts using the *original* spec and the most recent
    critic feedback."""
    final_dir = ROOT / "drafts" / "auditions" / persona / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    # 1) copy the canonical spec
    canonical_spec = VOICE_DIR / f"{persona}.md"
    shutil.copy(canonical_spec, final_dir / "voice_spec.md")

    # 2) copy critic feedback for traceability
    # Find the last round number from last_round_dir
    last_round_name = last_round_dir.name  # should be 'round_N'
    last_round_num = last_round_name.split('_')[-1]
    last_critic_json = last_round_dir / f"critic_round{last_round_num}.json"
    if not last_critic_json.exists():
        raise FileNotFoundError(last_critic_json)
    shutil.copy(last_critic_json, final_dir / "critic_feedback.json")

    # 3) run writer with the feedback
    for ch in chapters:
        cmd = [sys.executable, str(WRITER), ch,
               "--persona", persona,
               "--spec", str(final_dir / "voice_spec.md"),
               "--audition-dir", str(final_dir),
               "--critic-feedback", str(final_dir / "critic_feedback.json")]
        log.info("RUN: %s", " ".join(cmd))
        subprocess.run(cmd, check=True, cwd=ROOT)

    log.info("Final drafts created in %s", final_dir)

# ── main loop ──────────────────────────────────────────────────────────────

def main() -> None:
    ensure_utf8_windows()

    ap = argparse.ArgumentParser()
    ap.add_argument("persona", help="Persona label (e.g. cosmic_clarity)")
    ap.add_argument("chapters", type=int, help="Number of chapters to write")
    ap.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS,
                    help="Feedback rounds before the final pass [default: 2]")
    args = ap.parse_args()

    persona = args.persona
    num_chaps = args.chapters
    chapters = [f"lotm_{i:04d}" for i in range(1, num_chaps + 1)]
    rounds = max(1, args.rounds)

    previous_critic_json: pathlib.Path | None = None
    last_round_dir: pathlib.Path | None = None

    for rnd in range(1, rounds + 1):
        spec_dir = ROOT / "drafts" / "auditions" / persona / f"round_{rnd}"
        spec_dir.mkdir(parents=True, exist_ok=True)

        # copy the fixed voice spec into this round's directory as voice_spec.md
        spec_path = copy_fixed_spec(persona, spec_dir)

        # run writer with previous round drafts and any critic feedback
        call_writer(spec_dir, persona, chapters, spec_path,
                    previous_critic_json, last_round_dir)

        # run critic panel for the drafts just created
        critic_json = run_critic(spec_dir, rnd)
        log.info("Critic feedback saved → %s", critic_json)

        # store for next iteration
        previous_critic_json = critic_json
        last_round_dir = spec_dir

    # after the iterative rounds, create the final refined drafts
    if last_round_dir is not None:
        create_final_version(persona, chapters, last_round_dir)


if __name__ == "__main__":
    main() 