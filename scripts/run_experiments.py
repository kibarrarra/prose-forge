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
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# Rich imports for progress tracking and tables
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich import box

# Add project root to path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from utils.logging_helper import get_logger
from utils.paths import ROOT, VOICE_DIR, SEG_DIR, RAW_DIR, CTX_DIR, EXP_SUMM_DIR
from utils.io_helpers import read_utf8, write_utf8

# Create Rich console for pretty output
console = Console()
log = get_logger()

# Define script paths (similar to audition_iterative.py)
WRITER = ROOT / "scripts" / "writer.py"
EDITOR_PANEL = ROOT / "scripts" / "editor_panel.py"
SANITY_CHECKER = ROOT / "scripts" / "sanity_checker.py"

# Track experiment results for final summary table
experiment_results = []

def load_experiments(config_path: str) -> Dict[str, Any]:
    """Load experiments from a YAML configuration file."""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def filter_experiments(experiments: List[Dict[str, Any]], pattern: str) -> List[Dict[str, Any]]:
    """Filter experiments by name or components using regex pattern."""
    if not pattern:
        return experiments
    
    rx = re.compile(pattern, flags=re.I)  # Case-insensitive regex
    
    def match(exp: Dict[str, Any]) -> bool:
        """Check if experiment matches the regex pattern in any relevant field."""
        return any(
            rx.search(str(v))
            for k, v in exp.items()
            if k in ("name", "voice_spec", "writer_spec", "editor_spec")
        )
    
    filtered = [exp for exp in experiments if match(exp)]
    
    if not filtered:
        log.warning(f"No experiments matched pattern: {pattern}")
    
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

def run_experiment(experiment: Dict[str, Any], output_dir: pathlib.Path, progress: Optional[Progress] = None) -> Dict[str, Any]:
    """Run a single experiment with the given configuration."""
    exp_name = experiment["name"]
    start_time = time.time()
    exp_status = "Completed"
    error_details = None
    
    # Record experiment info for results table
    exp_results = {
        "name": exp_name,
        "model": experiment.get("model", os.getenv("WRITER_MODEL", "claude-3-opus-20240229")),
        "chapters": experiment["chapters"],
        "rounds": experiment.get("rounds", 1),
        "status": "Running",
        "start_time": datetime.now().strftime("%H:%M:%S"),
        "duration": 0,
        "output_path": None
    }
    experiment_results.append(exp_results)
    
    try:
        # Display setup status
        console.print(f"[bold green]Setting up experiment:[/] [cyan]{exp_name}[/]")
        
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
            exp_status = "Failed"
            error_details = f"Missing files: {', '.join(missing_files)}"
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
        exp_results["output_path"] = str(final_dir)
        
        # Save experiment configuration for reference
        with open(audition_dir / "config.json", 'w', encoding='utf-8') as f:
            json.dump(experiment, f, indent=2)
        
        # Load writer spec template
        writer_spec = load_text_spec(writer_spec_path)
        
        # Load editor spec
        with open(editor_spec_path, 'r', encoding='utf-8') as f:
            editor_spec_content = f.read()
        
        console.print(f"[bold green]Running experiment:[/] [cyan]{exp_name}[/]")
        
        # Create a task for this experiment's chapters if we have a progress bar
        chapter_task = None
        if progress:
            chapter_task = progress.add_task(f"[cyan]Chapters for {exp_name}", total=len(chapters))
        
        # Run audition process for each chapter
        for chapter in chapters:
            chapter_start_time = time.time()
            # Update progress if available
            if progress and chapter_task is not None:
                progress.update(chapter_task, description=f"[cyan]{exp_name} - Chapter {chapter}")
            else:
                console.print(f"[cyan]Processing chapter {chapter}[/]")
                
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
                
                # Update progress if available
                if progress and chapter_task is not None:
                    progress.update(chapter_task, advance=1)
                continue
            
            # Otherwise, perform the iterative rounds with feedback
            prev_round_dir = None
            
            # Process multiple rounds
            for rnd in range(1, feedback_rounds + 1):
                # Update progress if available
                if progress and chapter_task is not None:
                    progress.update(chapter_task, description=f"[cyan]{exp_name} - Chapter {chapter} (Round {rnd}/{feedback_rounds})")
                else:
                    console.print(f"[cyan]Round {rnd} for chapter {chapter}[/]")
                
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
                # Update progress if available
                if progress and chapter_task is not None:
                    progress.update(chapter_task, description=f"[cyan]{exp_name} - Chapter {chapter} (Final)")
                else:
                    console.print(f"[cyan]Final version for chapter {chapter}[/]")
                
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
            
            # Update progress if available
            if progress and chapter_task is not None:
                progress.update(chapter_task, advance=1)
            
            chapter_end_time = time.time()
            chapter_duration = chapter_end_time - chapter_start_time
            log.info(f"Chapter {chapter} completed in {chapter_duration:.1f}s")
        
        console.print(f"[bold green]Experiment {exp_name} completed successfully![/]")
    
    except Exception as e:
        exp_status = "Failed"
        error_details = str(e)
        log.error(f"Experiment {exp_name} failed: {e}")
        raise
    
    finally:
        # Update experiment results
        end_time = time.time()
        duration = end_time - start_time
        exp_results["duration"] = f"{duration:.1f}s"
        exp_results["status"] = exp_status
        if error_details:
            exp_results["error"] = error_details
    
    return exp_results

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
    
    # Set up environment with custom editor prompt if provided
    env = os.environ.copy()
    if editor_spec_content:
        env["EDITOR_PROMPT_TEMPLATE"] = editor_spec_content
    
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
                 dir1: Optional[str] = None, dir2: Optional[str] = None,
                 addl_drafts_dir: Optional[str] = None) -> None:
    """Compare the results of two experiments or specific directories."""
    # Create a progress status directly with a message (no context manager)
    console.print(f"[bold blue]Setting up comparison between experiments...[/]")
    
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
        console.print(f"[bold red]Error:[/] One or both directories do not exist: {exp1_dir}, {exp2_dir}")
        return
    
    # Update status with a progress message (no context manager)
    console.print(f"[bold blue]Comparing [cyan]{exp1_name}[/] vs [cyan]{exp2_name}...[/]")
    
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
        
        # Add additional drafts folder if provided
        if addl_drafts_dir and pathlib.Path(addl_drafts_dir).exists():
            cmd.extend(["--addl-dirs", str(addl_drafts_dir)])
            console.print(f"[blue]Including additional drafts from:[/] {addl_drafts_dir}")
        
        log.info(f"Running comparison: {' '.join(str(arg) for arg in cmd)}")
        
        # Show spinner during comparison
        with console.status("[bold yellow]Running comparison...[/]", spinner="dots") as status:
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
            console.print(f"[bold red]Comparison failed with exit code {completed_process.returncode}[/]")
            if completed_process.stderr:
                console.print(f"[red]Error output:[/] {completed_process.stderr}")
            return
        
        # Extract useful metrics from the stdout if available
        metrics = {}
        for line in completed_process.stdout.splitlines():
            if ":" in line and ("similarity" in line.lower() or "difference" in line.lower() or "score" in line.lower()):
                try:
                    key, value = line.split(":", 1)
                    metrics[key.strip()] = value.strip()
                except ValueError:
                    pass
        
        # Show a nice summary panel
        summary_lines = [
            f"[bold green]Comparison completed: {exp1_name} vs {exp2_name}[/]",
            f"[cyan]Output:[/] {output_file}"
        ]
        
        # Add metrics if we found any
        if metrics:
            summary_lines.append("\n[yellow]Metrics:[/]")
            for key, value in metrics.items():
                summary_lines.append(f"  [cyan]{key}:[/] {value}")
        
        # Suggest opening the file
        summary_lines.append("\n[bold]Next steps:[/]")
        summary_lines.append(f"  Open the HTML file in your browser to view the detailed comparison")
        
        console.print(Panel.fit(
            "\n".join(summary_lines),
            title="Comparison Summary",
            border_style="green",
            padding=(1, 2)
        ))
    else:
        console.print(f"[bold red]Error:[/] Comparison script not found: {compare_script}")

def generate_html_report(results: List[Dict[str, Any]], output_dir: pathlib.Path) -> str:
    """Generate an HTML report summarizing experiment results.
    
    Args:
        results: List of experiment result dictionaries
        output_dir: Output directory for the report
        
    Returns:
        Path to the generated HTML file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = output_dir / f"experiment_report_{timestamp}.html"
    
    # HTML template for the report
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Prose-Forge Experiment Report</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.5;
                margin: 0;
                padding: 20px;
                color: #333;
                max-width: 1200px;
                margin: 0 auto;
            }
            h1, h2, h3 {
                color: #2c3e50;
                margin-top: 30px;
            }
            table {
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
            }
            th, td {
                text-align: left;
                padding: 12px 15px;
                border-bottom: 1px solid #ddd;
            }
            th {
                background-color: #f0f8ff;
                color: #2c3e50;
                font-weight: bold;
                border-bottom: 2px solid #ccc;
                position: sticky;
                top: 0;
            }
            tr:hover {
                background-color: #f5f5f5;
            }
            .status-completed {
                color: green;
                font-weight: bold;
            }
            .status-failed {
                color: red;
                font-weight: bold;
            }
            .summary-card {
                background-color: #f8f9fa;
                border-radius: 5px;
                padding: 15px;
                margin: 20px 0;
                border-left: 5px solid #4682B4;
            }
            .chart-container {
                margin: 30px 0;
                display: flex;
                flex-direction: row;
                flex-wrap: wrap;
                justify-content: space-between;
            }
            .chart {
                background: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 15px;
                margin-bottom: 20px;
                width: 48%;
            }
            .timestamp {
                color: #666;
                font-size: 0.8em;
            }
            .compare-section {
                margin: 30px 0;
            }
            .compare-button {
                background-color: #4682B4;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                margin: 5px;
                text-decoration: none;
                display: inline-block;
            }
            .compare-button:hover {
                background-color: #36648B;
            }
        </style>
    </head>
    <body>
        <h1>Prose-Forge Experiment Report</h1>
        <div class="timestamp">Generated on: {{timestamp}}</div>
        
        <div class="summary-card">
            <h2>Run Summary</h2>
            <div>Total Experiments: {{total_experiments}}</div>
            <div>Completed: {{completed_count}}</div>
            <div>Failed: {{failed_count}}</div>
            <div>Total Runtime: {{total_runtime}}</div>
        </div>

        <h2>Experiment Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Experiment</th>
                    <th>Model</th>
                    <th>Chapters</th>
                    <th>Rounds</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Output Path</th>
                </tr>
            </thead>
            <tbody>
                {{result_rows}}
            </tbody>
        </table>

        <h2>Comparison Suggestions</h2>
        <div class="compare-section">
            {{comparison_links}}
        </div>

    </body>
    </html>
    """
    
    # Start with some summary statistics
    total_experiments = len(results)
    completed_count = sum(1 for r in results if r["status"] == "Completed")
    failed_count = total_experiments - completed_count
    total_runtime = sum(float(r["duration"].strip("s")) for r in results if "duration" in r)
    
    # Generate table rows
    result_rows = []
    for r in results:
        # Format chapters list
        chapters_str = ", ".join(r["chapters"]) if len(r["chapters"]) <= 3 else f"{len(r['chapters'])} chapters"
        
        # Set status style based on completion
        status_class = "status-completed" if r["status"] == "Completed" else "status-failed"
        
        # Create table row
        row = f"""
        <tr>
            <td>{r["name"]}</td>
            <td>{r["model"]}</td>
            <td>{chapters_str}</td>
            <td>{r["rounds"]}</td>
            <td class="{status_class}">{r["status"]}</td>
            <td>{r["duration"]}</td>
            <td>{r["output_path"] or 'N/A'}</td>
        </tr>
        """
        result_rows.append(row)
    
    # Create comparison links
    comparison_links = []
    experiment_names = [r["name"] for r in results if r["status"] == "Completed"]
    if len(experiment_names) >= 2:
        for i, exp1 in enumerate(experiment_names[:-1]):
            for exp2 in experiment_names[i+1:]:
                cmd = f'python scripts/run_experiments.py --compare {exp1} {exp2}'
                comparison_links.append(
                    f'<a href="#" class="compare-button" onclick="navigator.clipboard.writeText(\'{cmd}\'); '
                    f'alert(\'Command copied to clipboard: {cmd}\');">'
                    f'Compare {exp1} vs {exp2}</a>'
                )
    
    if not comparison_links:
        comparison_links.append("<p>Run multiple successful experiments to see comparison suggestions.</p>")
    
    # Fill template
    html_content = html_template.replace("{{timestamp}}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    html_content = html_content.replace("{{total_experiments}}", str(total_experiments))
    html_content = html_content.replace("{{completed_count}}", str(completed_count))
    html_content = html_content.replace("{{failed_count}}", str(failed_count))
    html_content = html_content.replace("{{total_runtime}}", f"{total_runtime:.1f}s")
    html_content = html_content.replace("{{result_rows}}", "\n".join(result_rows))
    html_content = html_content.replace("{{comparison_links}}", "\n".join(comparison_links))
    
    # Write HTML file
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return str(report_file)

def main() -> None:
    ap = argparse.ArgumentParser(description="Run experiments from a YAML configuration file")
    ap.add_argument("--config", help="Path to YAML configuration file")
    ap.add_argument("--filter", help="Filter experiments by name or components")
    ap.add_argument("--compare", nargs=2, metavar=("EXP1", "EXP2"), 
                    help="Compare results of two experiments (uses final directories)")
    ap.add_argument("--compare-dirs", nargs=2, metavar=("DIR1", "DIR2"),
                    help="Compare results between two specific directories")
    ap.add_argument("--addl-drafts", metavar="DIR",
                    help="Directory containing additional drafts for comparison (structure: addl_drafts/draft_type/chapter.txt)")
    ap.add_argument("--output-dir", default=EXP_SUMM_DIR,
                    help="Directory for experiment outputs")
    ap.add_argument("--no-auto-compare", action="store_true",
                    help="Disable automatic comparison of all experiments after they complete")
    ap.add_argument("--generate-combined-report", nargs=2, metavar=("EXP_REPORT", "COMP_REPORT"),
                    help="Generate combined report from existing experiment report and comparison report")
    
    args = ap.parse_args()
    
    # Create output directory
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Handle generate combined report operation
    if args.generate_combined_report:
        exp_report, comp_report = args.generate_combined_report
        if not os.path.exists(exp_report) or not os.path.exists(comp_report):
            ap.error(f"Both report files must exist. Check paths: {exp_report}, {comp_report}")
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        combined_report_path = output_dir / f"combined_report_{timestamp}.html"
        
        try:
            merge_html_reports(exp_report, [comp_report], combined_report_path)
            console.print(f"[bold green]Combined HTML report generated:[/] [blue]{combined_report_path}[/]")
        except Exception as e:
            console.print(f"[bold red]Error generating combined report:[/] {e}")
        return
        
    # Handle comparison operations
    if args.compare:
        # Compare experiment final outputs
        compare_experiments(args.compare[0], args.compare[1], output_dir, addl_drafts_dir=args.addl_drafts)
        return
        
    if args.compare_dirs:
        # Compare specific directories
        compare_experiments("dir1", "dir2", output_dir, args.compare_dirs[0], args.compare_dirs[1], addl_drafts_dir=args.addl_drafts)
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
    
    # Show startup banner
    console.print(Panel.fit(
        f"[bold cyan]Prose-Forge Experiment Runner[/]\n"
        f"[yellow]Running {len(experiments)} experiment(s)[/]",
        border_style="green"
    ))
    
    # Record start time for the whole run
    start_time = time.time()
    
    # Run each experiment and collect results
    results = []
    
    # Create progress columns for the overall experiment progress
    progress_columns = [
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn()
    ]
    
    # Use a progress bar to track overall experiment progress
    with Progress(*progress_columns, console=console) as exp_progress:
        exp_task = exp_progress.add_task(f"[magenta]Overall progress", total=len(experiments))
        
        for i, experiment in enumerate(experiments):
            try:
                # Update progress description to show current experiment
                exp_name = experiment["name"]
                exp_progress.update(exp_task, description=f"[magenta]Experiment {i+1}/{len(experiments)}: {exp_name}")
                
                # Run the experiment
                result = run_experiment(experiment, output_dir, exp_progress)
                results.append(result)
                
                # Advance the overall progress
                exp_progress.update(exp_task, advance=1)
                
            except Exception as e:
                log.error(f"Experiment failed: {e}")
                # Continue with the next experiment

    # Calculate total run time
    end_time = time.time()
    total_runtime = end_time - start_time
    
    # Display summary table
    table = Table(title=f"Experiment Results Summary (Total Runtime: {total_runtime:.1f}s)", box=box.ROUNDED)
    
    # Add columns
    table.add_column("Experiment", style="cyan")
    table.add_column("Model", style="yellow")
    table.add_column("Chapters", style="magenta")
    table.add_column("Rounds")
    table.add_column("Status", style="bold")
    table.add_column("Duration", style="green")
    table.add_column("Output Path", style="blue")
    
    # Add rows
    completed_experiments = []
    for result in experiment_results:
        # Format chapters list
        chapters_str = ", ".join(result["chapters"]) if len(result["chapters"]) <= 3 else f"{len(result['chapters'])} chapters"
        
        # Set status style based on completion
        status_style = "[green]" if result["status"] == "Completed" else "[red]"
        
        # Track completed experiments for comparison
        if result["status"] == "Completed":
            completed_experiments.append(result["name"])
        
        # Add the row
        table.add_row(
            result["name"],
            result["model"],
            chapters_str,
            str(result["rounds"]),
            f"{status_style}{result['status']}[/]",
            result["duration"],
            result["output_path"] or "N/A"
        )
    
    # Print the table
    console.print(table)
    
    # Generate HTML report for experiment results
    html_report_path = None
    if experiment_results:
        report_file = generate_html_report(experiment_results, output_dir)
        html_report_path = report_file
        console.print(f"[bold green]Experiment HTML report generated:[/] [blue]{report_file}[/]")
    
    # Automatically compare all experiments if we have multiple completed ones and auto-compare isn't disabled
    comparison_html_paths = []
    if len(completed_experiments) >= 2 and not args.no_auto_compare:
        console.print(f"[bold cyan]Automatically comparing all {len(completed_experiments)} completed experiments...[/]")
        
        # Run all-finals comparison using compare_versions.py
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        compare_output_path = output_dir / f"all_finals_comparison_{timestamp}.html"
        
        try:
            # Use the all-finals option from compare_versions.py
            all_finals_cmd = [
                sys.executable, str(ROOT / "scripts" / "compare_versions.py"),
                "--all-finals",
                "--output", str(compare_output_path)
            ]
            
            # Add additional drafts folder if provided
            if args.addl_drafts and pathlib.Path(args.addl_drafts).exists():
                all_finals_cmd.extend(["--addl-dirs", str(args.addl_drafts)])
                console.print(f"[blue]Including additional drafts in all-finals comparison from:[/] {args.addl_drafts}")
            
            with console.status("[bold yellow]Running full comparison of all experiment versions...[/]", spinner="dots") as status:
                subprocess.run(all_finals_cmd, check=True, capture_output=True)
            
            console.print(f"[bold green]All-experiments comparison generated:[/] [blue]{compare_output_path}[/]")
            comparison_html_paths.append(str(compare_output_path))
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]Error generating all-experiments comparison:[/] {e}")
        
        # Create a combined HTML report
        if html_report_path and comparison_html_paths:
            combined_report_path = output_dir / f"combined_report_{timestamp}.html"
            try:
                merge_html_reports(html_report_path, comparison_html_paths, combined_report_path)
                console.print(f"[bold green]Combined HTML report generated:[/] [blue]{combined_report_path}[/]")
            except Exception as e:
                console.print(f"[bold red]Error generating combined report:[/] {e}")

def merge_html_reports(experiment_report: str, comparison_reports: List[str], output_path: str) -> None:
    """
    Merge experiment results HTML with comparison HTML reports.
    
    Args:
        experiment_report: Path to the experiment results HTML report
        comparison_reports: List of paths to comparison HTML reports (typically just the all-finals comparison)
        output_path: Output path for the combined report
    """
    # Read the experiment report HTML
    with open(experiment_report, 'r', encoding='utf-8') as f:
        exp_html = f.read()
    
    # Extract the body content (remove html, head, and body tags)
    exp_body = exp_html.split('<body>')[1].split('</body>')[0].strip()
    
    # Extract any CSS from the experiment report
    exp_css = ""
    if '<style>' in exp_html and '</style>' in exp_html:
        exp_css = exp_html.split('<style>')[1].split('</style>')[0].strip()
    
    # Read the all-finals comparison report
    all_finals_body = ""
    all_finals_css = ""
    if comparison_reports:
        try:
            with open(comparison_reports[0], 'r', encoding='utf-8') as f:
                comp_html = f.read()
            
            # Extract the body content
            all_finals_body = comp_html.split('<body>')[1].split('</body>')[0].strip()
            
            # Extract CSS
            if '<style>' in comp_html and '</style>' in comp_html:
                all_finals_css = comp_html.split('<style>')[1].split('</style>')[0].strip()
        except Exception as e:
            log.error(f"Error reading comparison report {comparison_reports[0]}: {e}")
    
    # Combine all HTML reports with improved styling
    combined_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ProseForge Combined Report</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { 
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        .section-divider {
            margin: 50px 0;
            border-top: 2px solid #eee;
            position: relative;
        }
        .section-divider::before {
            content: attr(data-title);
            position: absolute;
            top: -15px;
            left: 50%;
            transform: translateX(-50%);
            background-color: white;
            padding: 0 20px;
            font-size: 1.5rem;
            font-weight: bold;
            color: #555;
        }
        .timestamp {
            color: #666;
            font-size: 0.8em;
            margin-bottom: 20px;
        }
        h1 { margin-bottom: 30px; }
        #toc {
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
        }
        #toc ul {
            list-style-type: none;
            padding-left: 10px;
        }
        #toc ul li {
            margin-bottom: 10px;
        }
        #toc a {
            text-decoration: none;
        }
        .section-container {
            padding: 20px;
        }
        
        /* Preserve table styling */
        .table {
            width: 100%;
            margin-bottom: 1rem;
            color: #212529;
            border-collapse: collapse;
        }
        .table th,
        .table td {
            padding: 0.75rem;
            vertical-align: top;
            border-top: 1px solid #dee2e6;
        }
        .table thead th {
            vertical-align: bottom;
            border-bottom: 2px solid #dee2e6;
        }
        
        /* Fix tab navigation */
        .nav-tabs {
            border-bottom: 1px solid #dee2e6;
            margin-bottom: 1rem;
        }
        .nav-tabs .nav-link {
            margin-bottom: -1px;
            border: 1px solid transparent;
            border-top-left-radius: 0.25rem;
            border-top-right-radius: 0.25rem;
        }
        .nav-tabs .nav-link.active {
            color: #495057;
            background-color: #fff;
            border-color: #dee2e6 #dee2e6 #fff;
        }
        
        /* Include original CSS from both reports */
        """ + exp_css + """
        
        """ + all_finals_css + """
    </style>
</head>
<body>
    <div class="container">
        <h1>ProseForge Combined Report</h1>
        <div class="timestamp">Generated on: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</div>
        
        <div id="toc">
            <h3>Table of Contents</h3>
            <ul>
                <li><a href="#experiment-results">1. Experiment Results</a></li>
                <li><a href="#all-versions">2. All Versions Ranking</a></li>
            </ul>
        </div>
        
        <div id="experiment-results">
            <div class="section-divider" data-title="Experiment Results"></div>
            <div class="section-container">
                """ + exp_body + """
            </div>
        </div>
"""

    # Add the all-versions ranking if available
    if all_finals_body:
        combined_html += """
        <div id="all-versions">
            <div class="section-divider" data-title="All Versions Ranking"></div>
            <div class="section-container">
                """ + all_finals_body + """
            </div>
        </div>
"""

    # Close the HTML and add Bootstrap JS for tab functionality
    combined_html += """
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Fix tab functionality
        document.addEventListener('DOMContentLoaded', function() {
            // Find all tab buttons
            const tabButtons = document.querySelectorAll('[data-bs-toggle="tab"]');
            
            // Add click event listeners
            tabButtons.forEach(function(button) {
                button.addEventListener('click', function(event) {
                    event.preventDefault();
                    
                    // Get the target tab pane
                    const target = document.querySelector(button.dataset.bsTarget);
                    if (!target) return;
                    
                    // Find all siblings and deactivate them
                    const tabPane = target.parentElement;
                    if (!tabPane) return;
                    
                    const siblings = tabPane.querySelectorAll('.tab-pane');
                    siblings.forEach(function(pane) {
                        pane.classList.remove('show', 'active');
                    });
                    
                    // Find all nav links and deactivate them
                    const tabLinks = button.closest('.nav-tabs');
                    if (tabLinks) {
                        const links = tabLinks.querySelectorAll('.nav-link');
                        links.forEach(function(link) {
                            link.classList.remove('active');
                        });
                    }
                    
                    // Activate the clicked button and target pane
                    button.classList.add('active');
                    target.classList.add('show', 'active');
                });
            });
        });
    </script>
</body>
</html>
"""

    # Write the combined HTML to the output file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(combined_html)

if __name__ == "__main__":
    main() 
