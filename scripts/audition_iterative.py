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
from utils.paths import ROOT, VOICE_DIR, CTX_DIR
from utils.io_helpers import read_utf8, ensure_utf8_windows

# ── logging & constants ────────────────────────────────────────────────────
log = get_logger()
WRITER = ROOT / "scripts" / "writer.py"
EDITOR_PANEL = ROOT / "scripts" / "editor_panel.py"
SANITY_CHECKER = ROOT / "scripts" / "sanity_checker.py"
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
        # Base command parts, common to all calls
        base_cmd_parts = [
            sys.executable, str(WRITER), ch,
            "--persona", persona,
            "--spec", str(spec_path),
            "--audition-dir", str(out_dir)
        ]
        
        cmd = list(base_cmd_parts) # Initialize cmd with base parts

        # Determine if this is the first draft pass in the iterative process
        is_first_iterative_pass = (critic_feedback is None and prev_round_dir is None)

        if is_first_iterative_pass:
            cmd.extend(["--segmented-first-draft", "--chunk-size", "250"])
            log.info(f"Chapter {ch}: First iterative pass, using segmented first draft with chunk size 250.")
        else:
            # This is a revision pass
            log.info(f"Chapter {ch}: Revision pass.")
            if prev_round_dir is not None:
                prev_draft_path = prev_round_dir / f"{ch}.txt"
                if prev_draft_path.exists():
                    cmd.extend(["--prev", str(prev_draft_path)])
                else:
                    log.warning(f"Chapter {ch}: Revision mode, but previous draft not found at {prev_draft_path}. This might affect revision quality.")
            
            if critic_feedback and critic_feedback.exists():
                cmd.extend(["--critic-feedback", str(critic_feedback)])
            else:
                # Only warn if it's a revision pass (not first) and feedback is unexpectedly missing
                if not is_first_iterative_pass:
                     log.warning(f"Chapter {ch}: Revision mode, but critic feedback JSON not provided or found. Check if {critic_feedback} is expected.")

        log.info("RUN: %s", " ".join(map(str, cmd))) # Use map(str, ...) for safety

        # Ensure the project root is on PYTHONPATH for the subprocess
        env = os.environ.copy()
        python_path = env.get("PYTHONPATH", "")
        project_root_str = str(ROOT.resolve())
        if project_root_str not in python_path.split(os.pathsep):
            env["PYTHONPATH"] = f"{project_root_str}{os.pathsep}{python_path}"

        subprocess.run(cmd, check=True, cwd=ROOT, env=env)


def run_editor(draft_dir: pathlib.Path, rnd: int) -> pathlib.Path:
    """Run the editor panel for *draft_dir* and return the JSON manifest path."""
    out_path = draft_dir / f"editor_round{rnd}.json"
    cmd = [sys.executable, str(EDITOR_PANEL),
           "--draft-dir", str(draft_dir),
           "--round", str(rnd),
           "--output", str(out_path)]
    log.info("RUN: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)
    return out_path


def run_sanity_check(prev_draft_dir: pathlib.Path, current_draft_dir: pathlib.Path,
                     change_list_json: pathlib.Path, chapter: str) -> bool:
    """Run sanity checker for a specific chapter and return True if OK."""
    prev_draft_path = prev_draft_dir / f"{chapter}.txt"
    new_draft_path = current_draft_dir / f"{chapter}.txt"
    raw_context_path = CTX_DIR / f"{chapter}.txt"
    status_path = current_draft_dir / f"{chapter}_sanity_status.txt"

    if not prev_draft_path.exists():
        log.warning(f"Sanity check skipped: Previous draft missing {prev_draft_path}")
        return True # Cannot check, assume OK for workflow
    if not new_draft_path.exists():
        log.warning(f"Sanity check skipped: New draft missing {new_draft_path}")
        return False # Revision failed
    if not change_list_json.exists():
        log.warning(f"Sanity check skipped: Change list missing {change_list_json}")
        return False # Cannot check without changes

    cmd = [sys.executable, str(SANITY_CHECKER),
           "--prev-draft", str(prev_draft_path),
           "--new-draft", str(new_draft_path),
           "--change-list-json", str(change_list_json),
           "--output-status", str(status_path)]

    if raw_context_path.exists():
        cmd += ["--raw-context", str(raw_context_path)]
    else:
        log.warning(f"Raw context not found for sanity check: {raw_context_path}")

    log.info("RUN Sanity Check: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True, text=True)
        # Read the verdict
        if status_path.exists():
            verdict = read_utf8(status_path).strip()
            log.info(f"Sanity check verdict for {chapter}: {verdict}")
            return verdict == "OK"
        else:
            log.warning(f"Sanity check status file missing: {status_path}")
            return False
    except subprocess.CalledProcessError as e:
        log.error(f"Sanity check failed for {chapter}:\n{e.stderr}")
        return False


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
    last_editor_json = last_round_dir / f"editor_round{last_round_num}.json"
    if not last_editor_json.exists():
        raise FileNotFoundError(last_editor_json)
    shutil.copy(last_editor_json, final_dir / "critic_feedback.json")

    # 3) copy last-round drafts into final_dir as the starting point so that
    #    writer.py (in revision mode) can perform an in-place update.
    for ch in chapters:
        src_draft = last_round_dir / f"{ch}.txt"
        if not src_draft.exists():
            raise FileNotFoundError(src_draft)
        shutil.copy(src_draft, final_dir / f"{ch}.txt")

    # 4) run writer with the feedback to perform the final revision in-place
    for ch in chapters:
        prev_draft_path = final_dir / f"{ch}.txt" # The draft copied in step 3
        cmd = [sys.executable, str(WRITER), ch,
               "--persona", persona,
               "--spec", str(final_dir / "voice_spec.md"),
               "--audition-dir", str(final_dir),
               "--critic-feedback", str(final_dir / "critic_feedback.json"),
               "--prev", str(prev_draft_path)] # Add the mandatory --prev arg
        log.info("RUN Final Writer: %s", " ".join(cmd))
        subprocess.run(cmd, check=True, cwd=ROOT)

        # Run sanity check on the final revised draft
        run_sanity_check(
            prev_draft_dir=last_round_dir, # Drafts were copied from here
            current_draft_dir=final_dir,
            change_list_json=final_dir / "critic_feedback.json",
            chapter=ch
        )

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

    previous_editor_json: pathlib.Path | None = None
    last_round_dir: pathlib.Path | None = None

    for rnd in range(1, rounds + 1):
        spec_dir = ROOT / "drafts" / "auditions" / persona / f"round_{rnd}"
        spec_dir.mkdir(parents=True, exist_ok=True)

        # copy the fixed voice spec into this round's directory as voice_spec.md
        spec_path = copy_fixed_spec(persona, spec_dir)

        # run writer with previous round drafts and any critic feedback
        call_writer(spec_dir, persona, chapters, spec_path,
                    previous_editor_json, last_round_dir)

        # run editor panel for the drafts just created
        editor_json = run_editor(spec_dir, rnd)
        log.info("Editor feedback saved → %s", editor_json)

        # Run sanity check for each chapter revised in this round
        if last_round_dir and previous_editor_json:
            log.info(f"Running sanity checks for round {rnd}...")
            all_ok = True
            for ch in chapters:
                if not run_sanity_check(last_round_dir, spec_dir, previous_editor_json, ch):
                    all_ok = False
            if not all_ok:
                log.warning(f"Sanity check issues found in round {rnd}.")

        # store for next iteration
        previous_editor_json = editor_json
        last_round_dir = spec_dir

    # after the iterative rounds, create the final refined drafts
    if last_round_dir is not None:
        create_final_version(persona, chapters, last_round_dir)


if __name__ == "__main__":
    main() 