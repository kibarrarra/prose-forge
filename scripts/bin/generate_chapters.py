#!/usr/bin/env python
"""
generate_chapters.py - Generate multiple chapters using a single voice spec.

This script generates multiple chapters using a consistent voice specification,
organizing outputs under drafts/[version_name]/ with the following structure:
- drafts/[version_name]/voice_spec.md
- drafts/[version_name]/chapters/[chapter_name].txt
- drafts/[version_name]/prompts/[chapter_name]_prompt.md

Usage:
    python scripts/bin/generate_chapters.py --version cosmic_clarity --chapters lotm_0001 lotm_0002 lotm_0003
    python scripts/bin/generate_chapters.py --version cosmic_clarity --range 1-5 --prefix lotm
    python scripts/bin/generate_chapters.py --version cosmic_clarity --count 10 --prefix lotm --start 1
    python scripts/bin/generate_chapters.py --config chapter_generation.yaml
"""

import argparse
import pathlib
import sys
import yaml
import time
import shutil
import re
from datetime import datetime
from typing import Dict, List, Any, Optional

# Rich imports for progress tracking
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich import box

# Add project root to path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from scripts.utils.logging_helper import get_logger
from scripts.utils.paths import ROOT, DRAFT_DIR
from scripts.utils.subprocess_helpers import setup_subprocess_env, run_subprocess_safely
from scripts.utils.file_helpers import validate_paths, find_chapter_source
from scripts.core.writing import DraftWriter, SourceLoader

# Create Rich console for pretty output
console = Console()
log = get_logger()

# Define script paths
WRITER = ROOT / "scripts" / "bin" / "writer.py"


def parse_chapter_range(range_str: str, prefix: str = "lotm") -> List[str]:
    """Parse a chapter range string like '1-5' into a list of chapter IDs.
    
    Args:
        range_str: Range string like '1-5', '10-20', etc.
        prefix: Chapter prefix (default: 'lotm')
        
    Returns:
        List of chapter IDs like ['lotm_0001', 'lotm_0002', ...]
    """
    try:
        start_str, end_str = range_str.split('-', 1)
        start = int(start_str)
        end = int(end_str)
        
        if start > end:
            raise ValueError(f"Start chapter {start} cannot be greater than end chapter {end}")
        
        chapters = []
        for i in range(start, end + 1):
            chapter_id = f"{prefix}_{i:04d}"
            chapters.append(chapter_id)
        
        return chapters
        
    except ValueError as e:
        if "invalid literal" in str(e):
            raise ValueError(f"Invalid range format '{range_str}'. Use format like '1-5'")
        raise


def generate_chapter_list(count: int, start: int = 1, prefix: str = "lotm") -> List[str]:
    """Generate a list of chapter IDs based on count and starting number.
    
    Args:
        count: Number of chapters to generate
        start: Starting chapter number (default: 1)
        prefix: Chapter prefix (default: 'lotm')
        
    Returns:
        List of chapter IDs like ['lotm_0001', 'lotm_0002', ...]
    """
    chapters = []
    for i in range(start, start + count):
        chapter_id = f"{prefix}_{i:04d}"
        chapters.append(chapter_id)
    
    return chapters


class ChapterGenerator:
    """Manages generation of multiple chapters with a single voice spec."""
    
    def __init__(self, version_name: str, voice_spec_path: pathlib.Path, 
                 writer_spec_path: pathlib.Path, model: str, temperature: float):
        self.version_name = version_name
        self.voice_spec_path = pathlib.Path(voice_spec_path)
        self.writer_spec_path = pathlib.Path(writer_spec_path)
        self.model = model
        self.temperature = temperature
        self.start_time = time.time()
        
        # Set up output directories
        self.version_dir = DRAFT_DIR / version_name
        self.chapters_dir = self.version_dir / "chapters"
        self.prompts_dir = self.version_dir / "prompts"
        
        # Track results
        self.results = []
        
    def setup_directories(self) -> None:
        """Create the directory structure for this version."""
        log.info(f"Setting up directories for version: {self.version_name}")
        
        # Create directories
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy voice spec to version directory
        dest_voice_spec = self.version_dir / "voice_spec.md"
        shutil.copy(self.voice_spec_path, dest_voice_spec)
        log.info(f"Copied voice spec to {dest_voice_spec}")
        
        # Save generation config
        config = {
            "version_name": self.version_name,
            "voice_spec": str(self.voice_spec_path),
            "writer_spec": str(self.writer_spec_path),
            "model": self.model,
            "temperature": self.temperature,
            "generated_at": datetime.now().isoformat()
        }
        
        config_path = self.version_dir / "generation_config.yaml"
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False)
        
    def generate_chapter(self, chapter: str, prev_chapter_path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
        """Generate a single chapter."""
        chapter_start = time.time()
        result = {
            "chapter": chapter,
            "status": "Running",
            "duration": 0,
            "output_path": None
        }
        
        try:
            # Validate chapter exists
            if not find_chapter_source(chapter):
                raise FileNotFoundError(f"Chapter '{chapter}' not found in source directories")
            
            # Output path
            output_path = self.chapters_dir / f"{chapter}.txt"
            result["output_path"] = str(output_path)
            
            # Build writer command
            cmd = [
                sys.executable, str(WRITER), chapter,
                "--persona", self.version_name,
                "--spec", str(self.version_dir / "voice_spec.md"),
                "--audition-dir", str(self.chapters_dir),
                "--model", self.model,
                "--temperature", str(self.temperature),
                "--segmented-first-draft",
                "--chunk-size", "250"
            ]
            
            # Add previous chapter for consistency if available
            if prev_chapter_path and prev_chapter_path.exists():
                cmd.extend(["--prev", str(prev_chapter_path)])
                log.info(f"Using previous chapter for consistency: {prev_chapter_path}")
            
            # Run writer
            env = setup_subprocess_env(writer_spec=str(self.writer_spec_path), model=self.model)
            run_subprocess_safely(cmd, env, description=f"writer for {chapter}")
            
            # Move prompt file if it exists
            prompt_source = self.chapters_dir / f"{chapter}_prompt.md"
            if prompt_source.exists():
                prompt_dest = self.prompts_dir / f"{chapter}_prompt.md"
                shutil.move(str(prompt_source), str(prompt_dest))
                log.info(f"Moved prompt to {prompt_dest}")
            
            result["status"] = "Completed"
            
        except Exception as e:
            result["status"] = "Failed"
            result["error"] = str(e)
            log.error(f"Failed to generate chapter {chapter}: {e}")
            raise
            
        finally:
            result["duration"] = time.time() - chapter_start
            
        return result
    
    def generate_all(self, chapters: List[str], progress: Optional[Progress] = None) -> List[Dict[str, Any]]:
        """Generate all chapters in sequence."""
        # Set up directories
        self.setup_directories()
        
        # Create progress task if available
        chapter_task = None
        if progress:
            chapter_task = progress.add_task(
                f"[cyan]Generating chapters for {self.version_name}", 
                total=len(chapters)
            )
        
        prev_chapter_path = None
        
        for i, chapter in enumerate(chapters):
            # Update progress
            if progress and chapter_task is not None:
                progress.update(
                    chapter_task, 
                    description=f"[cyan]{self.version_name} - Chapter {chapter} ({i+1}/{len(chapters)})"
                )
            else:
                console.print(f"[cyan]Generating chapter {chapter} ({i+1}/{len(chapters)})[/]")
            
            # Generate chapter
            result = self.generate_chapter(chapter, prev_chapter_path)
            self.results.append(result)
            
            # Update previous chapter path for next iteration
            if result["status"] == "Completed":
                prev_chapter_path = self.chapters_dir / f"{chapter}.txt"
            
            # Update progress
            if progress and chapter_task is not None:
                progress.update(chapter_task, advance=1)
            
            # Log result
            if result["status"] == "Completed":
                log.info(f"✓ Chapter {chapter} generated in {result['duration']:.1f}s")
            else:
                log.error(f"✗ Chapter {chapter} failed: {result.get('error', 'Unknown error')}")
        
        return self.results


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate multiple chapters using a single voice spec")
    
    # Option 1: Command line arguments
    ap.add_argument("--version", help="Version name for output organization")
    ap.add_argument("--voice-spec", type=pathlib.Path, help="Path to voice specification")
    ap.add_argument("--writer-spec", type=pathlib.Path, help="Path to writer specification")
    ap.add_argument("--model", default="claude-opus-4-20250514", help="Model to use")
    ap.add_argument("--temperature", type=float, default=0.7, help="Generation temperature")
    
    # Chapter specification options (mutually exclusive)
    chapter_group = ap.add_mutually_exclusive_group()
    chapter_group.add_argument("--chapters", nargs="+", help="List of chapter IDs to generate")
    chapter_group.add_argument("--range", help="Chapter range like '1-5' or '10-20'")
    chapter_group.add_argument("--count", type=int, help="Number of chapters to generate")
    
    # Additional options for range/count modes
    ap.add_argument("--prefix", default="lotm", help="Chapter prefix for range/count modes (default: lotm)")
    ap.add_argument("--start", type=int, default=1, help="Starting chapter number for count mode (default: 1)")
    
    # Option 2: Config file
    ap.add_argument("--config", help="Path to YAML configuration file")
    
    args = ap.parse_args()
    
    # Load configuration
    if args.config:
        config = load_config(args.config)
        version_name = config["version_name"]
        voice_spec_path = config["voice_spec"]
        writer_spec_path = config["writer_spec"]
        model = config.get("model", "claude-opus-4-20250514")
        temperature = config.get("temperature", 0.7)
        
        # Handle different chapter specification methods in config
        if "chapters" in config:
            chapters = config["chapters"]
        elif "range" in config:
            prefix = config.get("prefix", "lotm")
            chapters = parse_chapter_range(config["range"], prefix)
        elif "count" in config:
            prefix = config.get("prefix", "lotm")
            start = config.get("start", 1)
            chapters = generate_chapter_list(config["count"], start, prefix)
        else:
            ap.error("Config file must specify 'chapters', 'range', or 'count'")
            
    elif args.version and args.voice_spec and args.writer_spec:
        version_name = args.version
        voice_spec_path = args.voice_spec
        writer_spec_path = args.writer_spec
        model = args.model
        temperature = args.temperature
        
        # Handle chapter specification
        if args.chapters:
            chapters = args.chapters
        elif args.range:
            chapters = parse_chapter_range(args.range, args.prefix)
        elif args.count:
            chapters = generate_chapter_list(args.count, args.start, args.prefix)
        else:
            ap.error("Must specify --chapters, --range, or --count")
    else:
        ap.error("Either --config or (--version, --voice-spec, --writer-spec) required")
    
    # Validate paths
    missing_files = validate_paths({
        "Voice spec": pathlib.Path(voice_spec_path),
        "Writer spec": pathlib.Path(writer_spec_path)
    })
    
    if missing_files:
        log.error("Missing required files:\n" + "\n".join(missing_files))
        sys.exit(1)
    
    # Show startup banner
    console.print(Panel.fit(
        f"[bold cyan]Prose-Forge Chapter Generator[/]\n"
        f"[yellow]Version:[/] {version_name}\n"
        f"[yellow]Chapters:[/] {len(chapters)} chapters ({chapters[0]} to {chapters[-1]})\n"
        f"[yellow]Model:[/] {model}",
        border_style="green"
    ))
    
    # Create progress columns
    progress_columns = [
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn()
    ]
    
    # Run generation with progress tracking
    start_time = time.time()
    
    with Progress(*progress_columns, console=console) as progress:
        generator = ChapterGenerator(
            version_name=version_name,
            voice_spec_path=voice_spec_path,
            writer_spec_path=writer_spec_path,
            model=model,
            temperature=temperature
        )
        
        results = generator.generate_all(chapters, progress)
    
    # Calculate total time
    total_time = time.time() - start_time
    
    # Display results table
    table = Table(title=f"Generation Results (Total time: {total_time:.1f}s)", box=box.ROUNDED)
    table.add_column("Chapter", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Duration", style="green")
    table.add_column("Output Path", style="blue")
    
    successful = 0
    for result in results:
        status_style = "[green]" if result["status"] == "Completed" else "[red]"
        table.add_row(
            result["chapter"],
            f"{status_style}{result['status']}[/]",
            f"{result['duration']:.1f}s",
            result["output_path"] or "N/A"
        )
        if result["status"] == "Completed":
            successful += 1
    
    console.print(table)
    
    # Show completion summary
    console.print(Panel.fit(
        f"[bold green]Generation Complete![/]\n\n"
        f"[yellow]Summary:[/]\n"
        f"• Version: {version_name}\n"
        f"• Successful: {successful}/{len(chapters)}\n"
        f"• Total time: {total_time:.1f}s\n"
        f"• Output directory: {DRAFT_DIR / version_name}/",
        title="Complete",
        border_style="green"
    ))


if __name__ == "__main__":
    main() 