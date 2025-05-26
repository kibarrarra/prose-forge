#!/usr/bin/env python
"""
compare_versions_refactored.py – Refactored version comparison tool

A cleaner, modular version of the original compare_versions.py script.
This version uses separate modules for different functionality areas.

Usage:
    python scripts/compare_versions_refactored.py lotm_0001 lotm_0002 --versions cosmic_clarity_1 cosmic_clarity_3 lovecraft_2
    python scripts/compare_versions_refactored.py lotm_0001 --final-versions cosmic_clarity lovecraft
    python scripts/compare_versions_refactored.py --dir1 drafts/auditions/cosmic_clarity/round_1 --dir2 drafts/auditions/lovecraft/round_1 --output comparison.json
    python scripts/compare_versions_refactored.py --all-finals --addl-dirs drafts/addl_drafts
"""

import argparse
import json
import pathlib
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional

# Rich imports for progress tracking and console output
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.panel import Panel

# Add project root to path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Import modular components
from scripts.core.file_loaders import gather_final_versions, load_original_text
from scripts.core.comparison import compare_versions, compare_directories
from scripts.core.html_generation import generate_html_output, generate_ranking_html
from scripts.core.elo_ranking import smart_rank_chapter_versions, pairwise_rank_chapter_versions, rank_chapter_versions

# Import utilities
from scripts.utils.paths import ROOT
from scripts.utils.logging_helper import get_logger
from scripts.utils.io_helpers import read_utf8

# Create console and logger
console = Console()
log = get_logger()

def rank_all_chapters(
    output_path: pathlib.Path, 
    addl_dirs: Optional[pathlib.Path] = None, 
    max_versions: int = 0,
    ranking_method: str = "smart",
    initial_runs: int = 3,
    top_candidates: int = 4,
    temperature: float = 0.8,
    save_intermediate: bool = True,
    load_from_json: Optional[pathlib.Path] = None,
) -> None:
    """
    Rank all available chapter versions and generate an HTML report.
    
    Args:
        output_path: Path to save the HTML report
        addl_dirs: Directory containing additional drafts for comparison
        max_versions: Maximum number of versions to compare per chapter (0 = no limit)
        ranking_method: Method to use for ranking ('smart', 'full_pairwise', 'simple', or 'quick')
        initial_runs: Number of initial ranking runs (smart method only)
        top_candidates: Number of top candidates for pairwise comparison (smart method only)
        temperature: Temperature for initial ranking runs (smart method only)
        save_intermediate: Whether to save intermediate JSON results
        load_from_json: Load existing ranking results from JSON file instead of running new rankings
    """
    
    def validate_ranking_result(ranking_result: Dict[str, Any], chapter_id: str, num_versions: int) -> bool:
        """Validate that a ranking result is complete and valid."""
        if ranking_result is None:
            log.warning(f"Ranking result for {chapter_id} is None")
            return False
            
        if "error" in ranking_result:
            log.warning(f"Ranking result for {chapter_id} contains error: {ranking_result['error']}")
            return False
            
        # Check for required fields
        required_fields = ["chapter_id", "versions", "table"]
        for field in required_fields:
            if field not in ranking_result:
                log.warning(f"Ranking result for {chapter_id} missing required field: {field}")
                return False
        
        # Validate table structure
        table = ranking_result.get("table", [])
        if not isinstance(table, list) or len(table) == 0:
            log.warning(f"Ranking result for {chapter_id} has empty or invalid table")
            return False
            
        # Relaxed discussion validation - just check if it exists and has some content
        discussion = ranking_result.get("discussion", "")
        if not discussion or len(discussion.strip()) < 50:
            log.warning(f"Ranking result for {chapter_id} has very short or missing discussion")
            # Don't fail validation for this - just warn
            
        # Check if we have reasonable rankings (at least top ranked item)
        top_entry = table[0] if table else None
        if not top_entry or "rank" not in top_entry:
            log.warning(f"Ranking result for {chapter_id} has malformed top ranking entry")
            return False
            
        # Check that we have at least some reasonable number of ranked items
        if len(table) < min(2, num_versions):
            log.warning(f"Ranking result for {chapter_id} has too few ranked items: {len(table)} < {min(2, num_versions)}")
            return False
            
        return True
    
    def save_intermediate_results(rankings: List[Dict[str, Any]], intermediate_file: pathlib.Path, operation: str = ""):
        """Safely save intermediate results with validation and backup."""
        try:
            # Filter out invalid rankings before saving
            valid_rankings = []
            invalid_count = 0
            
            for ranking in rankings:
                if ranking is None:
                    invalid_count += 1
                    continue
                    
                # Basic validation
                if isinstance(ranking, dict) and "chapter_id" in ranking:
                    valid_rankings.append(ranking)
                else:
                    invalid_count += 1
                    log.warning(f"Skipping invalid ranking result: {ranking}")
            
            # Create backup of existing file if it exists
            if intermediate_file.exists():
                backup_file = intermediate_file.with_suffix(f".backup_{datetime.now().strftime('%H%M%S')}.json")
                try:
                    import shutil
                    shutil.copy2(intermediate_file, backup_file)
                    console.print(f"[dim]Created backup: {backup_file}[/]")
                except Exception as backup_err:
                    log.warning(f"Failed to create backup: {backup_err}")
            
            # Save the valid rankings
            with open(intermediate_file, 'w', encoding='utf-8') as f:
                json.dump(valid_rankings, f, indent=2, ensure_ascii=False)
            
            status_msg = f"Saved {len(valid_rankings)} valid rankings"
            if invalid_count > 0:
                status_msg += f" (skipped {invalid_count} invalid)"
            if operation:
                status_msg += f" - {operation}"
                
            console.print(f"[dim]{status_msg}[/]")
            
        except Exception as save_err:
            log.error(f"Failed to save intermediate results: {save_err}")
            console.print(f"[bold red]✗ Failed to save intermediate results: {save_err}[/]")

    # If loading from existing JSON, skip ranking and go straight to HTML generation
    if load_from_json and load_from_json.exists():
        console.print(f"[cyan]Loading existing rankings from {load_from_json}[/]")
        try:
            with open(load_from_json, 'r', encoding='utf-8') as f:
                rankings = json.load(f)
        except Exception as load_err:
            console.print(f"[bold red]Error loading JSON file: {load_err}[/]")
            sys.exit(1)
        
        console.print(f"[green]Loaded {len(rankings)} existing rankings[/]")
        
        # Generate HTML report
        console.print("[cyan]Generating HTML report from saved results...[/]")
        valid_rankings = [r for r in rankings if r is not None]
        if len(valid_rankings) != len(rankings):
            console.print(f"[yellow]Warning: {len(rankings) - len(valid_rankings)} ranking(s) were None[/]")
        
        html_content = generate_ranking_html(valid_rankings)
        
        # Save HTML report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        console.print(f"[bold green]✓ HTML report generated from saved results: {output_path}[/]")
        return
    
    console.print(f"[bold cyan]Gathering all final chapter versions...[/]")
    chapters_map = gather_final_versions()
    
    # Add additional drafts if provided
    if addl_dirs and addl_dirs.exists():
        console.print(f"[cyan]Looking for additional drafts in {addl_dirs}[/]")
        for draft_type_dir in addl_dirs.iterdir():
            if not draft_type_dir.is_dir():
                continue
                
            # Skip the comparisons folder
            if draft_type_dir.name == "comparisons":
                continue
                
            draft_type = draft_type_dir.name
            console.print(f"[blue]Processing additional draft type: {draft_type}[/]")
            
            # Look for chapter files in this draft directory
            for chapter_file in draft_type_dir.glob("*.txt"):
                chapter_id = chapter_file.stem
                
                # Skip files that aren't likely chapters (sanity reports, logs, etc.)
                if any(non_chapter in chapter_id.lower() for non_chapter in ["sanity", "status", "log", "report", "editor"]):
                    log.info(f"Skipping non-chapter file: {chapter_file}")
                    continue
                    
                if chapter_id not in chapters_map:
                    chapters_map[chapter_id] = []
                    
                chapter_text = read_utf8(chapter_file)
                # Use an empty voice spec for additional drafts
                voice_spec = ""
                
                # Add this as a version for the chapter
                chapters_map[chapter_id].append((f"addl_{draft_type}", chapter_text, voice_spec))
                log.info(f"Added additional draft '{draft_type}' for chapter {chapter_id}")
    
    if not chapters_map:
        console.print("[bold red]No chapters found with multiple versions[/]")
        return
    
    # Show startup summary
    method_description = ranking_method
    if ranking_method == "quick":
        method_description = "quick (simple ranking only, no pairwise comparisons)"
    
    console.print(Panel.fit(
        f"[bold green]Chapter Ranking Process[/]\n\n"
        f"[yellow]Method:[/] {method_description}\n"
        f"[yellow]Chapters to rank:[/] {len(chapters_map)}\n"
        f"[yellow]Output:[/] {output_path}",
        title="Setup Complete",
        border_style="green"
    ))
    
    # Prepare intermediate results file
    intermediate_file = None
    if save_intermediate:
        intermediate_dir = output_path.parent / "intermediate_results"
        intermediate_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        intermediate_file = intermediate_dir / f"rankings_{timestamp}.json"
        console.print(f"[dim]Intermediate results will be saved to: {intermediate_file}[/]")
    
    # Create progress columns for overall chapter progress
    progress_columns = [
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ]
    
    # Process each chapter
    rankings = []
    with Progress(*progress_columns, console=console) as progress:
        chapter_task = progress.add_task("[green]Processing chapters", total=len(chapters_map))
        
        for chapter_id, versions in chapters_map.items():
            if len(versions) < 2:
                console.print(f"[yellow]Chapter {chapter_id} has only {len(versions)} version(s), skipping[/]")
                progress.update(chapter_task, advance=1)
                continue
                
            # Limit the number of versions to compare (if too many)
            if max_versions > 0 and len(versions) > max_versions:
                console.print(f"[yellow]Chapter {chapter_id} has {len(versions)} versions, limiting to {max_versions}[/]")
                versions = versions[:max_versions]
            
            progress.update(chapter_task, description=f"[green]Ranking {chapter_id} ({len(versions)} versions)")
            
            try:
                ranking = None
                if ranking_method == "smart":
                    console.print(f"[cyan]Starting smart ranking for {chapter_id} with {len(versions)} versions[/]")
                    ranking = smart_rank_chapter_versions(
                        chapter_id, 
                        versions,
                        initial_runs=initial_runs,
                        top_candidates=min(top_candidates, len(versions)),  # Don't exceed available versions
                        temperature=temperature,
                        progress=progress,  # Pass the progress instance
                        parent_task_id=chapter_task  # Pass the parent task ID
                    )
                    console.print(f"[cyan]Smart ranking completed for {chapter_id}[/]")
                elif ranking_method == "full_pairwise":
                    console.print(f"[cyan]Running full pairwise comparison for {chapter_id}[/]")
                    ranking = pairwise_rank_chapter_versions(chapter_id, versions)
                elif ranking_method == "quick":
                    console.print(f"[cyan]Running quick ranking for {chapter_id} (no pairwise comparisons)[/]")
                    original = load_original_text(chapter_id)
                    ranking = rank_chapter_versions(chapter_id, versions, original_text=original, output_console=None)
                else:  # simple
                    console.print(f"[cyan]Running simple ranking for {chapter_id}[/]")
                    original = load_original_text(chapter_id)
                    ranking = rank_chapter_versions(chapter_id, versions, original_text=original, output_console=None)
                
                # Debug: Show what we got back
                if ranking is None:
                    console.print(f"[red]Ranking function returned None for {chapter_id}[/]")
                else:
                    console.print(f"[green]Ranking function returned result for {chapter_id}[/]")
                    console.print(f"[dim]Result keys: {list(ranking.keys()) if isinstance(ranking, dict) else 'Not a dict'}[/]")
                    if isinstance(ranking, dict):
                        table = ranking.get("table", [])
                        console.print(f"[dim]Table entries: {len(table)}[/]")
                        if table:
                            console.print(f"[dim]First entry: {table[0]}[/]")
                
                # Validate the ranking result before adding it
                if ranking is not None and validate_ranking_result(ranking, chapter_id, len(versions)):
                    rankings.append(ranking)
                    console.print(f"[bold green]✓ Completed ranking for {chapter_id}[/]")
                    
                    # Save intermediate results after each successful ranking
                    if save_intermediate and intermediate_file:
                        save_intermediate_results(rankings, intermediate_file, f"after {chapter_id}")
                        
                else:
                    error_msg = "Ranking validation failed" if ranking is not None else "Ranking function returned None"
                    console.print(f"[bold red]✗ {error_msg} for {chapter_id}[/]")
                    
                    # Show more details about validation failure
                    if ranking is not None:
                        console.print(f"[yellow]Debug info for failed validation:[/]")
                        console.print(f"[yellow]  Has table: {bool(ranking.get('table'))}[/]")
                        console.print(f"[yellow]  Table length: {len(ranking.get('table', []))}[/]")
                        console.print(f"[yellow]  Has discussion: {bool(ranking.get('discussion'))}[/]")
                        console.print(f"[yellow]  Discussion length: {len(ranking.get('discussion', ''))}[/]")
                        console.print(f"[yellow]  Has chapter_id: {bool(ranking.get('chapter_id'))}[/]")
                        console.print(f"[yellow]  Has versions: {bool(ranking.get('versions'))}[/]")
                    
                    # Add error entry but don't save to intermediate results yet
                    error_entry = {
                        "chapter_id": chapter_id,
                        "versions": [v[0] for v in versions],
                        "error": error_msg,
                        "timestamp": datetime.now().isoformat(),
                        "debug_info": {
                            "ranking_returned": ranking is not None,
                            "ranking_keys": list(ranking.keys()) if isinstance(ranking, dict) else None,
                            "table_length": len(ranking.get("table", [])) if isinstance(ranking, dict) else None
                        }
                    }
                    rankings.append(error_entry)
                
            except Exception as e:
                console.print(f"[bold red]✗ Failed to rank chapter {chapter_id}: {e}[/]")
                # Add detailed error info with traceback
                import traceback
                log.error(f"Traceback: {traceback.format_exc()}")
                
                error_entry = {
                    "chapter_id": chapter_id,
                    "versions": [v[0] for v in versions],
                    "error": f"Ranking failed: {e}",
                    "timestamp": datetime.now().isoformat()
                }
                rankings.append(error_entry)
                
                # Save intermediate results even with errors, but mark them clearly
                if save_intermediate and intermediate_file:
                    save_intermediate_results(rankings, intermediate_file, f"after error in {chapter_id}")
            
            progress.update(chapter_task, advance=1)
    
    # Final save of intermediate results
    if save_intermediate and intermediate_file:
        save_intermediate_results(rankings, intermediate_file, "final save")
        console.print(f"[bold cyan]Final results saved to: {intermediate_file}[/]")
    
    # Generate HTML report
    console.print("[cyan]Generating HTML report...[/]")
    
    # Filter out any None values and error entries for HTML generation
    valid_rankings = [r for r in rankings if r is not None and "error" not in r]
    error_rankings = [r for r in rankings if r is not None and "error" in r]
    
    if len(valid_rankings) != len(rankings):
        console.print(f"[yellow]Warning: {len(rankings) - len(valid_rankings)} ranking(s) had errors and will be excluded from HTML[/]")
        if error_rankings:
            console.print("[yellow]Failed chapters:[/]")
            for err_ranking in error_rankings:
                chapter_id = err_ranking.get("chapter_id", "unknown")
                error_msg = err_ranking.get("error", "unknown error")
                console.print(f"  [red]• {chapter_id}:[/] {error_msg}")
    
    if not valid_rankings:
        console.print("[bold red]No valid rankings to generate HTML from[/]")
        return
    
    try:
        html_content = generate_ranking_html(valid_rankings)
        
        # Save HTML report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        console.print(f"[bold green]✓ HTML report saved to: {output_path}[/]")
            
    except Exception as e:
        console.print(f"[bold red]✗ HTML generation failed: {e}[/]")
        console.print(f"[yellow]Rankings are still available in: {intermediate_file}[/]")
        console.print(f"[yellow]You can retry HTML generation with:[/]")
        console.print(f"[cyan]  python scripts/compare_versions_refactored.py --generate-html-from {intermediate_file} --output {output_path}[/]")
        raise e
    
    # Show completion summary
    successful_rankings = [r for r in rankings if "error" not in r]
    failed_rankings = [r for r in rankings if "error" in r]
    
    console.print(Panel.fit(
        f"[bold green]Ranking Complete![/]\n\n"
        f"[green]✓ Successfully ranked:[/] {len(successful_rankings)} chapters\n"
        f"[red]✗ Failed:[/] {len(failed_rankings)} chapters\n\n"
        f"[cyan]Report saved to:[/] {output_path}\n"
        f"[cyan]Intermediate results:[/] {intermediate_file}\n\n"
        f"[yellow]Next steps:[/]\n"
        f"• Open {output_path} in your browser\n"
        f"• Review the rankings and analysis",
        title="Results Summary",
        border_style="green"
    ))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters", nargs="*", help="Chapter IDs to compare (e.g. lotm_0001)")
    ap.add_argument("--versions", nargs="+", help="Specific versions to compare (e.g. cosmic_clarity_1 cosmic_clarity_3)")
    ap.add_argument("--final-versions", nargs="+", help="Compare final versions of these personae")
    ap.add_argument("--dir1", help="First directory to compare")
    ap.add_argument("--dir2", help="Second directory to compare")
    ap.add_argument("--output", help="Output file path (HTML format)")
    ap.add_argument("--format", choices=["html", "json"], default="html", 
                    help="Output format: html (default) or json")
    ap.add_argument("--all-finals", action="store_true", 
                    help="Rank all final versions of all chapters")
    ap.add_argument("--addl-dirs", nargs="+", help="Directory containing additional drafts for comparison (structure: addl_dirs/draft_type/chapter.txt)")
    ap.add_argument("--max-versions", type=int, default=0,
                    help="Maximum number of versions to compare per chapter (0 = no limit)")
    
    # Smart ranking parameters
    ap.add_argument("--ranking-method", choices=["smart", "full_pairwise", "simple", "quick"], default="smart",
                    help="Ranking method: smart (default), full_pairwise, simple, or quick (no pairwise comparisons)")
    ap.add_argument("--initial-runs", type=int, default=3,
                    help="Number of initial randomized ranking runs (smart method only)")
    ap.add_argument("--top-candidates", type=int, default=3,
                    help="Number of top candidates for pairwise comparison (smart method only)")
    ap.add_argument("--temperature", type=float, default=0.8,
                    help="Temperature for initial ranking runs (smart method only)")
    
    # Results management
    ap.add_argument("--generate-html-from", help="Generate HTML report from existing JSON results file")
    ap.add_argument("--no-save-intermediate", action="store_true",
                    help="Don't save intermediate JSON results during ranking")
    
    args = ap.parse_args()
    
    # Handle HTML generation from existing JSON
    if args.generate_html_from:
        json_file = pathlib.Path(args.generate_html_from)
        if not json_file.exists():
            console.print(f"[bold red]Error: JSON file not found: {json_file}[/]")
            sys.exit(1)
        
        # Determine output path
        if args.output:
            out_path = pathlib.Path(args.output)
            if not out_path.suffix:
                out_path = pathlib.Path(str(out_path) + ".html")
        else:
            out_path = json_file.with_suffix('.html')
        
        console.print(Panel.fit(
            f"[bold cyan]ProseForge HTML Generation[/]\n\n"
            f"[yellow]Source:[/] {json_file}\n"
            f"[yellow]Output:[/] {out_path}",
            title="Generating HTML from Saved Results",
            border_style="blue"
        ))
        
        try:
            rank_all_chapters(out_path, load_from_json=json_file)
        except Exception as e:
            console.print(f"[bold red]Error generating HTML: {e}[/]")
            sys.exit(1)
        return
    
    # Show startup banner
    if args.all_finals:
        operation = f"Ranking all final versions using {args.ranking_method} method"
    elif args.dir1 and args.dir2:
        operation = "Comparing two directories"
    elif args.chapters:
        operation = f"Comparing {len(args.versions or args.final_versions or [])} versions across {len(args.chapters)} chapters"
    else:
        operation = "Version comparison"
    
    console.print(Panel.fit(
        f"[bold cyan]ProseForge Version Comparison (Refactored)[/]\n\n"
        f"[yellow]Operation:[/] {operation}",
        title="Starting Analysis",
        border_style="blue"
    ))
    
    # Handle the all-finals mode
    if args.all_finals:
        # Determine output path
        if args.output:
            out_path = pathlib.Path(args.output)
            # Add .html extension if not specified
            if not out_path.suffix:
                out_path = pathlib.Path(str(out_path) + ".html")
        else:
            # Create default output file
            out_dir = ROOT / "drafts" / "auditions" / "comparisons"
            out_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            method_suffix = f"_{args.ranking_method}" if args.ranking_method != "smart" else ""
            out_path = out_dir / f"ranking_all_finals_{timestamp}{method_suffix}.html"
        
        # Run the ranking process
        try:
            # Pass additional directories if specified
            addl_dirs = pathlib.Path(args.addl_dirs[0]) if args.addl_dirs else None
            max_versions = args.max_versions
            save_intermediate = not args.no_save_intermediate
            rank_all_chapters(
                out_path, 
                addl_dirs, 
                max_versions, 
                args.ranking_method, 
                args.initial_runs, 
                args.top_candidates, 
                args.temperature,
                save_intermediate=save_intermediate,
            )
        except Exception as e:
            log.error(f"Error ranking chapters: {e}")
            sys.exit(1)
        return
    
    # Check if we're doing a directory-based comparison
    if args.dir1 and args.dir2:
        log.info(f"Comparing directories: {args.dir1} vs {args.dir2}")
        
        # Determine output path and format
        output_format = args.format
        output_ext = ".html" if output_format == "html" else ".json"
        
        if args.output:
            out_path = pathlib.Path(args.output)
            # Override extension based on format if the user didn't specify one
            if not out_path.suffix:
                out_path = pathlib.Path(str(out_path) + output_ext)
        else:
            # Create default output directory and file
            out_dir = ROOT / "drafts" / "auditions" / "comparisons"
            out_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract meaningful names from directories for better filenames
            dir1_path = pathlib.Path(args.dir1)
            dir2_path = pathlib.Path(args.dir2)
            
            # Look for 'auditions' in path to get experiment name
            dir1_parts = dir1_path.parts
            dir2_parts = dir2_path.parts
            
            dir1_name = ""
            dir2_name = ""
            
            # Try to construct name like "experiment_round" from path
            if 'auditions' in dir1_parts:
                idx = dir1_parts.index('auditions')
                if idx + 1 < len(dir1_parts):  # Make sure there's an experiment name after 'auditions'
                    dir1_name = f"{dir1_parts[idx+1]}_{dir1_path.name}"
                else:
                    dir1_name = dir1_path.name
            else:
                dir1_name = dir1_path.name
                
            if 'auditions' in dir2_parts:
                idx = dir2_parts.index('auditions')
                if idx + 1 < len(dir2_parts):  # Make sure there's an experiment name after 'auditions'
                    dir2_name = f"{dir2_parts[idx+1]}_{dir2_path.name}"
                else:
                    dir2_name = dir2_path.name
            else:
                dir2_name = dir2_path.name
            
            out_path = out_dir / f"compare_{dir1_name}_vs_{dir2_name}{output_ext}"
        
        # Generate comparison
        try:
            result = compare_directories(pathlib.Path(args.dir1), pathlib.Path(args.dir2))
            
            # Save results
            out_path.parent.mkdir(parents=True, exist_ok=True)
            
            if output_format == "html":
                html_content = generate_html_output(result)
                out_path.write_text(html_content, encoding="utf-8")
            else:
                out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
                
            log.info("Comparison saved → %s", out_path)
        except Exception as e:
            log.error(f"Error comparing directories: {e}")
            sys.exit(1)
    else:
        # Traditional version-based comparison
        if not args.chapters:
            print("Error: Chapter IDs are required for version-based comparison")
            sys.exit(1)
        
        if not args.versions and not args.final_versions:
            print("Error: Must specify either --versions or --final-versions")
            sys.exit(1)
        
        versions = args.versions or []
        
        # Handle final versions by converting them to the right format
        if args.final_versions:
            for persona in args.final_versions:
                # No need to add suffix for final versions as load_version_text will handle it
                versions.append(persona)
        
        # Create output directory
        out_dir = ROOT / "drafts" / "auditions" / "comparisons"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate comparison
        result = compare_versions(args.chapters, versions)
        
        # Determine output format
        output_format = args.format
        output_ext = ".html" if output_format == "html" else ".json"
        
        # Save results
        version_str = "_".join(versions)
        chapter_str = "_".join(args.chapters)
        
        if args.output:
            out_path = pathlib.Path(args.output)
            # Override extension based on format if the user didn't specify one
            if not out_path.suffix:
                out_path = pathlib.Path(str(out_path) + output_ext)
        else:
            out_path = out_dir / f"compare_{version_str}_{chapter_str}{output_ext}"
        
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        if output_format == "html":
            html_content = generate_html_output(result)
            out_path.write_text(html_content, encoding="utf-8")
        else:
            out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            
        log.info("Comparison saved → %s", out_path)

if __name__ == "__main__":
    main() 