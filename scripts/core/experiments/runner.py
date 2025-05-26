"""
runner.py - Experiment execution logic

This module contains the ExperimentRunner class that manages
the execution of individual experiments.
"""

import json
import os
import pathlib
import shutil
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import re

from rich.console import Console
from rich.progress import Progress

# Add project root to path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from scripts.utils.logging_helper import get_logger
from scripts.utils.paths import ROOT, SEG_DIR, RAW_DIR, CTX_DIR
from scripts.utils.subprocess_helpers import setup_subprocess_env, run_subprocess_safely
from scripts.utils.file_helpers import validate_paths, find_chapter_source, find_editor_feedback

log = get_logger()
console = Console()

# Define script paths
WRITER = ROOT / "scripts" / "bin" / "writer.py"
EDITOR_PANEL = ROOT / "scripts" / "bin" / "editor_panel.py"
SANITY_CHECKER = ROOT / "scripts" / "bin" / "sanity_checker.py"


class ExperimentRunner:
    """Encapsulates the logic for running a single experiment."""
    
    def __init__(self, experiment: Dict[str, Any], output_dir: pathlib.Path):
        self.experiment = experiment
        self.output_dir = output_dir
        self.exp_name = experiment["name"]
        self.start_time = time.time()
        self.exp_results = {
            "name": self.exp_name,
            "model": experiment.get("model", os.getenv("WRITER_MODEL", "claude-opus-4-20250514")),
            "chapters": experiment["chapters"],
            "rounds": experiment.get("rounds", 1),
            "status": "Running",
            "start_time": datetime.now().strftime("%H:%M:%S"),
            "duration": 0,
            "output_path": None
        }
        
    def validate_config(self) -> Tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
        """Validate experiment configuration and return paths.
        
        Returns:
            Tuple of (voice_spec_path, writer_spec_path, editor_spec_path)
            
        Raises:
            FileNotFoundError: If required files are missing
        """
        voice_spec_path = pathlib.Path(self.experiment["voice_spec"])
        writer_spec_path = pathlib.Path(self.experiment["writer_spec"])
        editor_spec_path = pathlib.Path(self.experiment["editor_spec"])
        
        # Verify all required files exist
        missing_files = validate_paths({
            "Voice spec": voice_spec_path,
            "Writer spec": writer_spec_path,
            "Editor spec": editor_spec_path
        })
        
        if missing_files:
            error_msg = f"Experiment '{self.exp_name}' references files that don't exist:\n" + "\n".join(missing_files)
            log.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        return voice_spec_path, writer_spec_path, editor_spec_path
    
    def validate_chapters(self, chapters: List[str]) -> None:
        """Validate that chapter sources exist."""
        for chapter in chapters:
            if not find_chapter_source(chapter):
                log.warning(f"Chapter '{chapter}' not found in any source directory")
    
    def setup_directories(self, rounds: int) -> Tuple[pathlib.Path, pathlib.Path]:
        """Set up audition directory structure.
        
        Args:
            rounds: Number of rounds to run
            
        Returns:
            Tuple of (audition_dir, final_dir)
        """
        # Sanitize experiment name for Windows directory compatibility
        sanitized_name = re.sub(r'[<>:"/\\|?*@]', '_', self.exp_name)
        if sanitized_name != self.exp_name:
            log.warning(f"Sanitized experiment name from '{self.exp_name}' to '{sanitized_name}' for directory compatibility")
        
        audition_dir = ROOT / "drafts" / "auditions" / sanitized_name
        log.info(f"Experiment name: '{self.exp_name}'")
        log.info(f"Sanitized name: '{sanitized_name}'")
        log.info(f"Full audition directory path: {audition_dir}")
        
        try:
            # Create round directories for feedback rounds
            feedback_rounds = max(0, rounds - 1)
            for rnd in range(1, feedback_rounds + 1):
                round_dir = audition_dir / f"round_{rnd}"
                log.info(f"Creating round directory: {round_dir}")
                round_dir.mkdir(parents=True, exist_ok=True)
            
            # Always create final directory
            final_dir = audition_dir / "final"
            log.info(f"Creating final directory: {final_dir}")
            final_dir.mkdir(parents=True, exist_ok=True)
            
            # Save experiment configuration
            config_path = audition_dir / "config.json"
            log.info(f"Saving experiment config to: {config_path}")
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.experiment, f, indent=2)
                
            return audition_dir, final_dir
            
        except Exception as e:
            log.error(f"Failed to create directories for experiment {self.exp_name}: {e}")
            log.error(f"Attempted to create: {audition_dir}")
            raise
    
    def run_single_pass_chapter(self, chapter: str, final_dir: pathlib.Path,
                               voice_spec_path: pathlib.Path, writer_spec: str, 
                               model: str, temperature: float) -> None:
        """Run a single-pass experiment (no feedback rounds)."""
        # Copy voice spec to final directory
        final_spec_path = final_dir / "voice_spec.md"
        log.info(f"Copying voice spec from {voice_spec_path} to {final_spec_path}")
        shutil.copy(voice_spec_path, final_spec_path)
        
        # Verify the copy was successful
        if not final_spec_path.exists():
            raise FileNotFoundError(f"Failed to copy voice spec to {final_spec_path}")
        
        log.info(f"Voice spec successfully copied, size: {final_spec_path.stat().st_size} bytes")
        
        # Run writer for the first and only draft
        self._run_writer_for_round(
            chapter=chapter,
            persona=self.exp_name,
            spec_path=final_spec_path,
            output_dir=final_dir,
            prev_round_dir=None,
            critic_feedback=None,
            writer_spec=writer_spec,
            model=model,
            temperature=temperature
        )
        
        log.info(f"Single-pass experiment {self.exp_name} completed for chapter {chapter}")
    
    def run_iterative_chapter(self, chapter: str, audition_dir: pathlib.Path,
                             final_dir: pathlib.Path, feedback_rounds: int,
                             voice_spec_path: pathlib.Path, writer_spec: str,
                             editor_spec_content: str, model: str, temperature: float) -> None:
        """Run iterative experiment with feedback rounds."""
        prev_round_dir = None
        
        # Process feedback rounds
        for rnd in range(1, feedback_rounds + 1):
            console.print(f"[cyan]Round {rnd} for chapter {chapter}[/]")
            
            current_round_dir = audition_dir / f"round_{rnd}"
            
            # Copy voice spec
            shutil.copy(voice_spec_path, current_round_dir / "voice_spec.md")
            
            # Find previous round's feedback
            critic_feedback_path = None
            if rnd > 1 and prev_round_dir:
                critic_feedback_path = find_editor_feedback(prev_round_dir, rnd - 1)
                if not critic_feedback_path:
                    log.warning(f"Expected critic feedback not found for round {rnd}")
            
            # Run writer
            self._run_writer_for_round(
                chapter=chapter,
                persona=self.exp_name,
                spec_path=current_round_dir / "voice_spec.md",
                output_dir=current_round_dir,
                prev_round_dir=prev_round_dir,
                critic_feedback=critic_feedback_path,
                writer_spec=writer_spec,
                model=model,
                temperature=temperature
            )
            
            # Run sanity checker if applicable
            if rnd > 1 and prev_round_dir and critic_feedback_path and critic_feedback_path.exists():
                self._run_sanity_checker(
                    draft_dir=current_round_dir,
                    chapter=chapter,
                    prev_draft_dir=prev_round_dir,
                    change_list_json=critic_feedback_path
                )
            
            # Run editor panel for feedback
            self._run_editor_panel(
                draft_dir=current_round_dir,
                rnd=rnd,
                output_path=current_round_dir / f"editor_round{rnd}.json",
                editor_spec_content=editor_spec_content,
                model=model
            )
            
            prev_round_dir = current_round_dir
        
        # Create final version
        self._create_final_version(
            persona=self.exp_name,
            chapters=[chapter],
            last_round_dir=prev_round_dir,
            final_dir=final_dir,
            writer_spec=writer_spec,
            model=model,
            temperature=temperature
        )
        
        # Run final sanity check
        final_feedback_path = final_dir / "critic_feedback.json"
        if prev_round_dir and final_feedback_path.exists():
            self._run_sanity_checker(
                draft_dir=final_dir,
                chapter=chapter,
                prev_draft_dir=prev_round_dir,
                change_list_json=final_feedback_path
            )
    
    def run(self, progress: Optional[Progress] = None) -> Dict[str, Any]:
        """Execute the experiment.
        
        Args:
            progress: Optional progress bar to update
            
        Returns:
            Experiment results dictionary
        """
        try:
            console.print(f"[bold green]Setting up experiment:[/] [cyan]{self.exp_name}[/]")
            
            # Validate configuration
            voice_spec_path, writer_spec_path, editor_spec_path = self.validate_config()
            
            # Extract parameters
            chapters = self.experiment["chapters"]
            rounds = self.experiment.get("rounds", 1)
            model = self.experiment.get("model", os.getenv("WRITER_MODEL", "claude-opus-4-20250514"))
            temperature = self.experiment.get("temperature", 0.7)  # Default to 0.7
            
            # Validate chapters
            self.validate_chapters(chapters)
            
            # Set up directories
            audition_dir, final_dir = self.setup_directories(rounds)
            self.exp_results["output_path"] = str(final_dir)
            
            # Load editor spec content (still needed for now)
            with open(editor_spec_path, 'r', encoding='utf-8') as f:
                editor_spec_content = f.read()
            
            console.print(f"[bold green]Running experiment:[/] [cyan]{self.exp_name}[/]")
            
            # Create progress task if available
            chapter_task = None
            if progress:
                chapter_task = progress.add_task(f"[cyan]Chapters for {self.exp_name}", total=len(chapters))
            
            # Process each chapter
            feedback_rounds = max(0, rounds - 1)
            
            for chapter in chapters:
                chapter_start_time = time.time()
                
                # Update progress
                if progress and chapter_task is not None:
                    progress.update(chapter_task, description=f"[cyan]{self.exp_name} - Chapter {chapter}")
                else:
                    console.print(f"[cyan]Processing chapter {chapter}[/]")
                
                # Run appropriate workflow
                if feedback_rounds == 0:
                    self.run_single_pass_chapter(chapter, final_dir, voice_spec_path, 
                                               str(writer_spec_path), model, temperature)
                else:
                    self.run_iterative_chapter(chapter, audition_dir, final_dir, 
                                             feedback_rounds, voice_spec_path,
                                             str(writer_spec_path), editor_spec_content, model, temperature)
                
                # Update progress
                if progress and chapter_task is not None:
                    progress.update(chapter_task, advance=1)
                
                chapter_duration = time.time() - chapter_start_time
                log.info(f"Chapter {chapter} completed in {chapter_duration:.1f}s")
            
            console.print(f"[bold green]Experiment {self.exp_name} completed successfully![/]")
            self.exp_results["status"] = "Completed"
            
        except Exception as e:
            self.exp_results["status"] = "Failed"
            self.exp_results["error"] = str(e)
            log.error(f"Experiment {self.exp_name} failed: {e}")
            raise
            
        finally:
            # Record duration
            duration = time.time() - self.start_time
            self.exp_results["duration"] = f"{duration:.1f}s"
        
        return self.exp_results
    
    def _run_writer_for_round(self,
                              chapter: str,
                              persona: str,
                              spec_path: pathlib.Path,
                              output_dir: pathlib.Path,
                              prev_round_dir: Optional[pathlib.Path] = None,
                              critic_feedback: Optional[pathlib.Path] = None,
                              writer_spec: Optional[str] = None,
                              model: Optional[str] = None,
                              temperature: float = 0.7) -> None:
        """Run the writer script for a specific round of an experiment."""
        # Build command
        cmd = [
            sys.executable, str(WRITER), chapter,
            "--persona", persona,
            "--spec", str(spec_path),
            "--audition-dir", str(output_dir)
        ]
        
        if model:
            cmd.extend(["--model", model])
        
        # Add temperature
        cmd.extend(["--temperature", str(temperature)])
        
        # Configure based on whether this is first draft or revision
        is_first_pass = (critic_feedback is None and prev_round_dir is None)
        
        if is_first_pass:
            cmd.extend(["--segmented-first-draft", "--chunk-size", "250"])
            log.info(f"Chapter {chapter}: First pass, using segmented first draft")
        else:
            log.info(f"Chapter {chapter}: Revision pass")
            
            # Add previous draft if available
            if prev_round_dir:
                prev_draft_path = prev_round_dir / f"{chapter}.txt"
                if prev_draft_path.exists():
                    cmd.extend(["--prev", str(prev_draft_path)])
                else:
                    log.warning(f"Previous draft not found at {prev_draft_path}")
            
            # Add critic feedback if available
            if critic_feedback and critic_feedback.exists():
                cmd.extend(["--critic-feedback", str(critic_feedback)])
        
        # Run with proper environment
        env = setup_subprocess_env(writer_spec=writer_spec, model=model)
        run_subprocess_safely(cmd, env, description=f"writer for {chapter}")
    
    def _run_editor_panel(self,
                          draft_dir: pathlib.Path, 
                          rnd: int, 
                          output_path: pathlib.Path, 
                          editor_spec_content: Optional[str] = None,
                          model: Optional[str] = None) -> None:
        """Run the editor panel script to get critic feedback."""
        cmd = [
            sys.executable, str(EDITOR_PANEL),
            "--draft-dir", str(draft_dir),
            "--round", str(rnd),
            "--output", str(output_path)
        ]
        
        env = setup_subprocess_env(editor_spec=editor_spec_content, model=model)
        run_subprocess_safely(cmd, env, description=f"editor panel round {rnd}")
    
    def _run_sanity_checker(self,
                            draft_dir: pathlib.Path,
                            chapter: str,
                            prev_draft_dir: Optional[pathlib.Path] = None,
                            change_list_json: Optional[pathlib.Path] = None) -> None:
        """Run the sanity checker script to verify draft quality."""
        draft_path = draft_dir / f"{chapter}.txt"
        if not draft_path.exists():
            log.warning(f"Draft not found for sanity check: {draft_path}")
            return
            
        # Sanity checker needs previous draft and change list to work
        if prev_draft_dir is None or change_list_json is None or not change_list_json.exists():
            log.info(f"Skipping sanity check for {draft_dir} - insufficient inputs")
            return
        
        # Define the previous draft path
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
        
        # Run with standard environment and error handling
        env = setup_subprocess_env()
        try:
            run_subprocess_safely(cmd, env, description=f"sanity check for {chapter}")
        except Exception as e:
            # Sanity check failures are non-fatal
            log.warning(f"Sanity check failed: {e}. This is non-fatal, continuing.")
    
    def _create_final_version(self,
                              persona: str, 
                              chapters: List[str],
                              last_round_dir: pathlib.Path, 
                              final_dir: pathlib.Path,
                              writer_spec: Optional[str] = None,
                              model: Optional[str] = None,
                              temperature: float = 0.7) -> None:
        """Generate the final version using the last round's feedback."""
        log.info(f"Creating final version for {persona}")
        
        # Copy voice spec from last round
        last_round_spec = last_round_dir / "voice_spec.md"
        if not last_round_spec.exists():
            raise FileNotFoundError(f"Voice spec not found in last round: {last_round_spec}")
        
        final_spec_path = final_dir / "voice_spec.md"
        shutil.copy(last_round_spec, final_spec_path)
        
        # Find and copy editor feedback to standard location
        final_feedback_path = None
        last_round_name = last_round_dir.name
        
        if last_round_name.startswith("round_"):
            try:
                last_round_num = int(last_round_name.split('_')[-1])
                feedback_source = find_editor_feedback(last_round_dir, last_round_num)
                
                if feedback_source:
                    final_feedback_path = final_dir / "critic_feedback.json"
                    shutil.copy(feedback_source, final_feedback_path)
                    log.info(f"Using editor feedback from {feedback_source}")
                else:
                    log.info("No editor feedback found, proceeding without feedback")
            except (ValueError, IndexError):
                log.warning(f"Could not parse round number from: {last_round_name}")
        
        # Run final revision for each chapter
        for chapter in chapters:
            last_draft_path = last_round_dir / f"{chapter}.txt"
            if not last_draft_path.exists():
                log.warning(f"Last draft not found for chapter {chapter}, skipping")
                continue
            
            self._run_writer_for_round(
                chapter=chapter,
                persona=persona,
                spec_path=final_spec_path,
                output_dir=final_dir,
                prev_round_dir=last_round_dir,
                critic_feedback=final_feedback_path,
                writer_spec=writer_spec,
                model=model,
                temperature=temperature
            ) 