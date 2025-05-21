#!/usr/bin/env python
"""
run_experiments.py - Run experiments defined in a YAML configuration file.

This script reads experiment configurations from a YAML file and runs each
experiment, following the workflow established in audition_iterative.py but
with configurable prompts, voice specs, and models.

Usage:
    python scripts/run_experiments.py --config experiments.yaml
    python scripts/run_experiments.py --config experiments.yaml --filter cosmic
    python scripts/run_experiments.py --config experiments.yaml --compare exp1 exp2
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import yaml
import time
from typing import Dict, List, Any, Optional

# Add project root to path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from utils.logging_helper import get_logger
from utils.paths import ROOT, VOICE_DIR, SEG_DIR, RAW_DIR, CTX_DIR
from utils.io_helpers import read_utf8, write_utf8

log = get_logger()

# Define script paths (similar to audition_iterative.py)
WRITER = ROOT / "scripts" / "writer.py"
EDITOR_PANEL = ROOT / "scripts" / "editor_panel.py"
SANITY_CHECKER = ROOT / "scripts" / "sanity_checker.py"

def load_experiments(config_path: str) -> Dict[str, Any]:
    """Load experiments from a YAML configuration file."""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def filter_experiments(experiments: List[Dict[str, Any]], filter_term: str) -> List[Dict[str, Any]]:
    """Filter experiments by name or components."""
    if not filter_term:
        return experiments
    
    filtered = []
    for exp in experiments:
        # Check if filter matches the name or any component path
        if filter_term.lower() in exp["name"].lower():
            filtered.append(exp)
            continue
        
        # Check voice_spec path
        if "voice_spec" in exp and filter_term.lower() in exp["voice_spec"].lower():
            filtered.append(exp)
            continue
            
        # Check writer/editor spec paths
        if "writer_spec" in exp and filter_term.lower() in exp["writer_spec"].lower():
            filtered.append(exp)
            continue
        
        if "editor_spec" in exp and filter_term.lower() in exp["editor_spec"].lower():
            filtered.append(exp)
            
    return filtered

def load_text_spec(file_path: str) -> str:
    """Load a plain text writer spec template."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def run_sanity_checker(
    draft_dir: pathlib.Path,
    chapter: str,
    prev_draft_dir: Optional[pathlib.Path] = None,
    change_list_json: Optional[pathlib.Path] = None
) -> None:
    """Run the sanity checker script to verify draft quality.
    
    The sanity checker requires a previous draft, new draft, and change list JSON.
    If these aren't available, we skip the sanity check.
    """
    draft_path = draft_dir / f"{chapter}.txt"
    if not draft_path.exists():
        log.warning(f"Draft not found for sanity check: {draft_path}")
        return
        
    # Sanity checker needs previous draft and change list to work
    if prev_draft_dir is None or change_list_json is None or not change_list_json.exists():
        log.info(f"Skipping sanity check for {draft_dir} - insufficient inputs")
        return
    
    prev_draft_path = prev_draft_dir / f"{chapter}.txt"
    if not prev_draft_path.exists():
        log.warning(f"Previous draft not found for sanity check: {prev_draft_path}")
        return
    
    log.info(f"Checking revision: {prev_draft_path.name} vs {draft_path.name}")
    
    cmd = [
        sys.executable, str(SANITY_CHECKER),
        "--prev-draft", str(prev_draft_path),
        "--new-draft", str(draft_path),
        "--change-list-json", str(change_list_json)
    ]
    
    # Check for raw context file
    raw_context_path = CTX_DIR / f"{chapter}.txt"
    if raw_context_path.exists():
        cmd.extend(["--raw-context", str(raw_context_path)])
    
    log.info(f"Running sanity check: {' '.join(str(arg) for arg in cmd)}")
    try:
        # Set up environment with UTF-8 encoding
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        # Run the subprocess with explicit UTF-8 encoding
        result = subprocess.run(
            cmd, 
            check=True, 
            cwd=ROOT, 
            capture_output=True,
            text=True, 
            encoding='utf-8', 
            errors='replace',
            env=env
        )
        
        # Log the stdout output so it's visible in the console
        if result.stdout:
            for line in result.stdout.splitlines():
                log.info(f"Sanity Check: {line}")
    except subprocess.CalledProcessError as e:
        log.warning(f"Sanity check failed with exit code {e.returncode}: {e.stderr}. This is non-fatal, continuing.")

def run_experiment(experiment: Dict[str, Any], output_dir: pathlib.Path) -> None:
    """Run a single experiment with the given configuration."""
    exp_name = experiment["name"]
    log.info(f"Running experiment: {exp_name}")
    
    # Extract experiment parameters
    voice_spec_path = pathlib.Path(experiment["voice_spec"])
    writer_spec_path = pathlib.Path(experiment["writer_spec"])
    editor_spec_path = pathlib.Path(experiment["editor_spec"])
    chapters = experiment["chapters"]
    rounds = experiment.get("rounds", 1)
    model = experiment.get("model", os.getenv("WRITER_MODEL", "claude-3-opus-20240229"))
    
    # Verify that all required configuration files exist
    missing_files = []
    for path, desc in [
        (voice_spec_path, "Voice spec"),
        (writer_spec_path, "Writer spec"),
        (editor_spec_path, "Editor spec")
    ]:
        if not path.exists():
            missing_files.append(f"{desc}: {path}")
    
    if missing_files:
        error_msg = f"Experiment '{exp_name}' references files that don't exist:\n" + "\n".join(missing_files)
        log.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    # Verify that chapters exist as well
    for chapter in chapters:
        chapter_exists = False
        # Check in raw directory first (preferred source)
        if (RAW_DIR / f"{chapter}.json").exists() or (RAW_DIR / f"{chapter}.txt").exists():
            chapter_exists = True
        # Check in segments directory as fallback
        elif any(SEG_DIR.glob(f"{chapter}_p*.txt")):
            chapter_exists = True
        # Check in context directory as last resort
        elif (CTX_DIR / f"{chapter}.txt").exists():
            chapter_exists = True
            
        if not chapter_exists:
            log.warning(f"Chapter '{chapter}' not found in raw, segments, or context directories. It may not be processed correctly.")
    
    # Create audition directory structure (following audition_iterative.py's pattern)
    audition_dir = ROOT / "drafts" / "auditions" / exp_name
    
    # If rounds = 1, we only do a first draft with no rounds/feedback
    # If rounds > 1, we do (rounds-1) feedback rounds plus final
    feedback_rounds = max(0, rounds - 1)
    
    # Create directories for each feedback round 
    for rnd in range(1, feedback_rounds + 1):
        round_dir = audition_dir / f"round_{rnd}"
        round_dir.mkdir(parents=True, exist_ok=True)
    
    # Always create final directory
    final_dir = audition_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    
    # Save experiment configuration for reference
    with open(audition_dir / "config.json", 'w', encoding='utf-8') as f:
        json.dump(experiment, f, indent=2)
    
    # Load writer spec template
    writer_spec = load_text_spec(writer_spec_path)
    
    # Load editor spec
    with open(editor_spec_path, 'r', encoding='utf-8') as f:
        editor_spec_content = f.read()
    
    # Run audition process for each chapter
    for chapter in chapters:
        # Set up audition process
        log.info(f"Running audition process for chapter {chapter}")
        
        # If we're doing a single-pass experiment (rounds=1)
        if feedback_rounds == 0:
            # Just do the first draft directly to final directory
            current_dir = final_dir
            
            # Copy the voice spec into the directory
            shutil.copy(voice_spec_path, current_dir / "voice_spec.md")
            
            # Run writer for the first and only draft
            run_writer_for_round(
                chapter=chapter,
                persona=exp_name,
                spec_path=current_dir / "voice_spec.md",
                output_dir=current_dir,
                prev_round_dir=None,
                critic_feedback=None,
                writer_spec=writer_spec,
                model=model
            )
            
            # First draft has no previous version or change list, so we skip sanity check
            log.info(f"Skipping sanity check for first draft of {chapter}")
            
            log.info(f"Single-pass experiment {exp_name} completed successfully for chapter {chapter}!")
            continue
        
        # Otherwise, perform the iterative rounds with feedback
        prev_round_dir = None
        for rnd in range(1, feedback_rounds + 1):
            current_round_dir = audition_dir / f"round_{rnd}"
            
            # Copy the voice spec into the round directory (as required by writer.py)
            shutil.copy(voice_spec_path, current_round_dir / "voice_spec.md")
            
            # For rounds after the first, check for critic feedback from the previous round
            critic_feedback_path = None
            if rnd > 1 and prev_round_dir:
                critic_feedback_path = prev_round_dir / f"editor_round{rnd-1}.json"
                if not critic_feedback_path.exists():
                    log.warning(f"Expected critic feedback not found at {critic_feedback_path}")
                    # Since the standard filename pattern didn't work, we'll look for 
                    # any editor feedback files in the previous round directory
                    editor_files = list(prev_round_dir.glob("editor_*.json"))
                    if editor_files:
                        # Use the first editor feedback file found
                        critic_feedback_path = editor_files[0]
                        log.info(f"Using alternate critic feedback at {critic_feedback_path}")
            
            # Run writer.py for this round
            run_writer_for_round(
                chapter=chapter,
                persona=exp_name,
                spec_path=current_round_dir / "voice_spec.md",
                output_dir=current_round_dir,
                prev_round_dir=prev_round_dir,
                critic_feedback=critic_feedback_path,
                writer_spec=writer_spec,
                model=model
            )
            
            # Run sanity checker for rounds after the first if we have previous draft and feedback
            if rnd > 1 and prev_round_dir and critic_feedback_path and critic_feedback_path.exists():
                run_sanity_checker(
                    draft_dir=current_round_dir,
                    chapter=chapter,
                    prev_draft_dir=prev_round_dir,
                    change_list_json=critic_feedback_path
                )
            else:
                log.info(f"Skipping sanity check for round {rnd} - insufficient inputs")
            
            # Run editor panel for all rounds where we need feedback for the next round
            # This includes all rounds up to and including the feedback_rounds
            if rnd <= feedback_rounds:
                run_editor_panel(
                    draft_dir=current_round_dir,
                    rnd=rnd,
                    output_path=current_round_dir / f"editor_round{rnd}.json",
                    editor_spec_content=editor_spec_content,
                    model=model
                )
            
            prev_round_dir = current_round_dir
        
        # Create final version using the latest round (only if we had feedback rounds)
        if feedback_rounds > 0:
            create_final_version(
                persona=exp_name,
                chapters=[chapter],
                last_round_dir=prev_round_dir,
                final_dir=final_dir,
                writer_spec=writer_spec,
                model=model
            )
            
            # Run sanity checker on the final output if we have the necessary inputs
            final_feedback_path = final_dir / "critic_feedback.json"
            if prev_round_dir and final_feedback_path.exists():
                run_sanity_checker(
                    draft_dir=final_dir,
                    chapter=chapter,
                    prev_draft_dir=prev_round_dir,
                    change_list_json=final_feedback_path
                )
            else:
                log.info(f"Skipping final sanity check - insufficient inputs")
    
    log.info(f"Experiment {exp_name} completed successfully!")

def run_writer_for_round(
    chapter: str,
    persona: str,
    spec_path: pathlib.Path,
    output_dir: pathlib.Path,
    prev_round_dir: Optional[pathlib.Path] = None,
    critic_feedback: Optional[pathlib.Path] = None,
    writer_spec: Optional[str] = None,
    model: Optional[str] = None
) -> None:
    """Run the writer script for a specific round of an experiment."""
    # Base command parts, common to all calls
    cmd = [
        sys.executable, str(WRITER), chapter,
        "--persona", persona,
        "--spec", str(spec_path),
        "--audition-dir", str(output_dir)
    ]
    
    # Add model if specified
    if model:
        cmd.extend(["--model", model])
    
    # Determine if this is the first draft pass in the iterative process
    is_first_pass = (critic_feedback is None and prev_round_dir is None)
    
    if is_first_pass:
        # Use the same chunking configuration as audition_iterative.py
        cmd.extend(["--segmented-first-draft", "--chunk-size", "250"])
        log.info(f"Chapter {chapter}: First pass, using segmented first draft with chunk size 250")
    else:
        # This is a revision pass
        log.info(f"Chapter {chapter}: Revision pass")
        if prev_round_dir is not None:
            prev_draft_path = prev_round_dir / f"{chapter}.txt"
            if prev_draft_path.exists():
                cmd.extend(["--prev", str(prev_draft_path)])
            else:
                log.warning(f"Chapter {chapter}: Previous draft not found at {prev_draft_path}")
        
        if critic_feedback and critic_feedback.exists():
            cmd.extend(["--critic-feedback", str(critic_feedback)])
        else:
            # Only warn if it's a revision pass and feedback is unexpectedly missing
            if not is_first_pass and critic_feedback:
                log.warning(f"Chapter {chapter}: Critic feedback not found at {critic_feedback}")
                # Try looking in the previous round directory if provided
                if prev_round_dir and critic_feedback:
                    round_num = int(str(critic_feedback).split('editor_round')[-1].split('.')[0])
                    alternate_path = prev_round_dir / f"editor_round{round_num}.json"
                    if alternate_path.exists():
                        log.info(f"Chapter {chapter}: Found alternate feedback at {alternate_path}")
                        cmd.extend(["--critic-feedback", str(alternate_path)])
    
    log.info(f"Running writer: {' '.join(str(arg) for arg in cmd)}")
    
    # Set up environment with PYTHONPATH and custom prompts if provided
    env = os.environ.copy()
    
    # Ensure the project root is on PYTHONPATH
    python_path = env.get("PYTHONPATH", "")
    project_root_str = str(ROOT.resolve())
    if project_root_str not in python_path.split(os.pathsep):
        env["PYTHONPATH"] = f"{project_root_str}{os.pathsep}{python_path}"
    
    # Add writer prompt template for writer.py if provided
    if writer_spec:
        env["WRITER_PROMPT_TEMPLATE"] = writer_spec
    
    # Log environment variables and command for debugging
    log_dir = pathlib.Path("logs/run_experiments")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"writer_call_{timestamp}_{persona}_{chapter}.txt"
    
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"COMMAND: {' '.join(str(arg) for arg in cmd)}\n\n")
        f.write("ENVIRONMENT VARIABLES:\n")
        # Log the relevant environment variables
        for key, value in env.items():
            if key.startswith("WRITER_") or key == "PYTHONPATH":
                f.write(f"{key}={value}\n")
        
        # Log the writer spec details if available
        if writer_spec:
            f.write("\nWRITER SPEC:\n")
            f.write(writer_spec)
            f.write("\n")
    
    log.info(f"Writer call details saved to {log_file}")
    
    subprocess.run(cmd, check=True, cwd=ROOT, env=env)

def run_editor_panel(
    draft_dir: pathlib.Path, 
    rnd: int, 
    output_path: pathlib.Path, 
    editor_spec_content: Optional[str] = None,
    model: Optional[str] = None
) -> None:
    """Run the editor panel script to get critic feedback."""
    cmd = [
        sys.executable, str(EDITOR_PANEL),
        "--draft-dir", str(draft_dir),
        "--round", str(rnd),
        "--output", str(output_path)
    ]
    
    log.info(f"Running editor panel: {' '.join(str(arg) for arg in cmd)}")
    
    # Set up environment with custom critic prompt if provided
    env = os.environ.copy()
    if editor_spec_content:
        env["CRITIC_PROMPT_OVERRIDE"] = editor_spec_content
    
    # Set model override if provided
    if model:
        env["EDITOR_MODEL"] = model
    
    subprocess.run(cmd, check=True, cwd=ROOT, env=env)

def create_final_version(
    persona: str, 
    chapters: List[str],
    last_round_dir: pathlib.Path, 
    final_dir: pathlib.Path,
    writer_spec: Optional[str] = None,
    model: Optional[str] = None
) -> None:
    """Generate the final version using the last round's feedback."""
    log.info(f"Creating final version for {persona}")
    
    # 1) Copy the canonical voice spec from the last round
    last_round_spec = last_round_dir / "voice_spec.md"
    if not last_round_spec.exists():
        raise FileNotFoundError(f"Voice spec not found in last round: {last_round_spec}")
    
    # Copy to final directory
    final_spec_path = final_dir / "voice_spec.md"
    shutil.copy(last_round_spec, final_spec_path)
    
    # 2) Check for editor feedback
    final_feedback_path = None
    
    # Try to find editor feedback using multiple approaches
    # First, try the standard naming pattern
    last_round_name = last_round_dir.name
    if last_round_name.startswith("round_"):
        try:
            last_round_num = int(last_round_name.split('_')[-1])
            last_editor_json = last_round_dir / f"editor_round{last_round_num}.json"
            
            if last_editor_json.exists():
                # Found feedback with standard naming
                final_feedback_path = final_dir / "critic_feedback.json"
                shutil.copy(last_editor_json, final_feedback_path)
                log.info(f"Using editor feedback from {last_editor_json}")
            else:
                # Look for any editor feedback files in the last round directory
                editor_files = list(last_round_dir.glob("editor_*.json"))
                if editor_files:
                    # Use the first editor feedback file found
                    final_feedback_path = final_dir / "critic_feedback.json"
                    shutil.copy(editor_files[0], final_feedback_path)
                    log.info(f"Using alternative editor feedback from {editor_files[0]}")
                else:
                    log.info(f"No editor feedback found in {last_round_dir}, proceeding without feedback")
        except (ValueError, IndexError):
            log.warning(f"Could not parse round number from directory name: {last_round_name}")
            log.info("Proceeding without editor feedback")
    
    # 3) For each chapter, run the final revision
    for chapter in chapters:
        # Get path to the last draft but DO NOT copy it yet
        last_draft_path = last_round_dir / f"{chapter}.txt"
        if not last_draft_path.exists():
            log.warning(f"Last draft not found for chapter {chapter}, skipping.")
            continue
        
        # Run writer for final revision - NOTE: --prev points to the last_round_dir, not final_dir
        cmd = [
            sys.executable, str(WRITER), chapter,
            "--persona", persona,
            "--spec", str(final_spec_path),
            "--prev", str(last_draft_path),
            "--audition-dir", str(final_dir)
        ]
        
        # Add feedback if available
        if final_feedback_path:
            cmd.extend(["--critic-feedback", str(final_feedback_path)])
        
        # Add model if specified
        if model:
            cmd.extend(["--model", model])
        
        log.info(f"Running final revision: {' '.join(str(arg) for arg in cmd)}")
        
        # Set up environment
        env = os.environ.copy()
        python_path = env.get("PYTHONPATH", "")
        project_root_str = str(ROOT.resolve())
        if project_root_str not in python_path.split(os.pathsep):
            env["PYTHONPATH"] = f"{project_root_str}{os.pathsep}{python_path}"
        

        
        subprocess.run(cmd, check=True, cwd=ROOT, env=env)

def compare_experiments(exp1: str, exp2: str, output_dir: pathlib.Path, 
                 dir1: Optional[str] = None, dir2: Optional[str] = None) -> None:
    """Compare the results of two experiments or specific directories."""
    # If specific directories are provided, use those
    if dir1 and dir2:
        exp1_dir = pathlib.Path(dir1)
        exp2_dir = pathlib.Path(dir2)
        
        # Extract meaningful names from paths for better file naming
        # Instead of just using the last directory name, use parent/round format
        dir1_parts = exp1_dir.parts
        dir2_parts = exp2_dir.parts
        
        # Look for 'auditions' in the path to extract experiment name and round
        if 'auditions' in dir1_parts:
            # Find index of 'auditions' in the path
            idx = dir1_parts.index('auditions')
            if idx + 1 < len(dir1_parts):  # Make sure there's an experiment name after 'auditions'
                exp1_name = f"{dir1_parts[idx+1]}_{exp1_dir.name}"
            else:
                exp1_name = exp1_dir.name
        else:
            exp1_name = exp1_dir.name
            
        if 'auditions' in dir2_parts:
            idx = dir2_parts.index('auditions')
            if idx + 1 < len(dir2_parts):  # Make sure there's an experiment name after 'auditions'
                exp2_name = f"{dir2_parts[idx+1]}_{exp2_dir.name}"
            else:
                exp2_name = exp2_dir.name
        else:
            exp2_name = exp2_dir.name
    else:
        # Otherwise use the default "final" directories under the experiment names
        exp1_dir = ROOT / "drafts" / "auditions" / exp1 / "final"
        exp2_dir = ROOT / "drafts" / "auditions" / exp2 / "final" 
        exp1_name = f"{exp1}_final"
        exp2_name = f"{exp2}_final"
    
    if not exp1_dir.exists() or not exp2_dir.exists():
        log.error(f"One or both directories do not exist: {exp1_dir}, {exp2_dir}")
        return
    
    # Use existing compare_versions.py script
    compare_script = ROOT / "scripts" / "compare_versions.py"
    if compare_script.exists():
        # Create comparison output directory
        comparison_dir = output_dir / "comparisons"
        comparison_dir.mkdir(exist_ok=True)
        
        output_file = comparison_dir / f"{exp1_name}_vs_{exp2_name}.html"
        cmd = [
            sys.executable, str(compare_script),
            "--dir1", str(exp1_dir),
            "--dir2", str(exp2_dir),
            "--output", str(output_file),
            "--format", "html"  # Explicitly request HTML format
        ]
        
        log.info(f"Running comparison: {' '.join(str(arg) for arg in cmd)}")
        
        # Run the process but only log specific lines from stdout that we want to see
        completed_process = subprocess.run(
            cmd, 
            check=False,  # Don't raise exception on non-zero exit
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # Check for errors manually
        if completed_process.returncode != 0:
            log.error(f"Comparison failed with exit code {completed_process.returncode}")
            if completed_process.stderr:
                log.error(f"Error output: {completed_process.stderr}")
            return
        
        # Log only relevant output - suppress the "Comparison saved" line
        for line in completed_process.stdout.splitlines():
            if "Comparing directories:" in line:
                log.info(line)
            # Skip the "Comparison saved" line since we'll log our own version
            elif "Comparison saved" not in line and line.strip():
                log.info(line)
        
        log.info(f"Comparison saved to: {output_file}")
    else:
        log.error(f"Comparison script not found: {compare_script}")

def main() -> None:
    ap = argparse.ArgumentParser(description="Run experiments from a YAML configuration file")
    ap.add_argument("--config", help="Path to YAML configuration file")
    ap.add_argument("--filter", help="Filter experiments by name or components")
    ap.add_argument("--compare", nargs=2, metavar=("EXP1", "EXP2"), 
                    help="Compare results of two experiments (uses final directories)")
    ap.add_argument("--compare-dirs", nargs=2, metavar=("DIR1", "DIR2"),
                    help="Compare results between two specific directories")
    ap.add_argument("--output-dir", default=pathlib.Path("outputs"),
                    help="Directory for experiment outputs")
    
    args = ap.parse_args()
    
    # Create output directory
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # Handle comparison operations first
    if args.compare:
        # Compare experiment final outputs
        compare_experiments(args.compare[0], args.compare[1], output_dir)
        return
        
    if args.compare_dirs:
        # Compare specific directories
        compare_experiments("dir1", "dir2", output_dir, args.compare_dirs[0], args.compare_dirs[1])
        return
    
    # For all other operations, require config file
    if not args.config:
        ap.error("the --config argument is required unless using --compare or --compare-dirs")
    
    # Load experiments
    config = load_experiments(args.config)
    experiments = config.get("experiments", [])
    
    # Filter experiments if requested
    if args.filter:
        experiments = filter_experiments(experiments, args.filter)
        if not experiments:
            log.warning(f"No experiments matched filter: {args.filter}")
            return
    
    # Run each experiment
    for experiment in experiments:
        run_experiment(experiment, output_dir)

if __name__ == "__main__":
    main() 
