"""
comparison.py - Version and directory comparison logic

This module handles:
- Comparing multiple versions of chapters
- Directory-based comparisons
- Version text processing and metadata handling
"""

import pathlib
from typing import Dict, List, Any
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, SpinnerColumn

from .file_loaders import load_version_text, load_texts_from_dir, load_original_text
from .critics import get_comparison_feedback

console = Console()

def compare_versions(chapters: List[str], versions: List[str]) -> Dict[str, Any]:
    """Compare multiple versions of chapters and return critic feedback."""
    console.print(f"[bold blue]Comparing versions:[/] {', '.join(versions)} for chapters {', '.join(chapters)}")
    
    # Load all versions
    version_texts = {}
    original_texts = {}
    total_loads = len(versions) * len(chapters)
    
    progress_columns = [
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ]
    
    with Progress(*progress_columns, console=console) as progress:
        load_task = progress.add_task("[cyan]Loading version texts", total=total_loads)
        
        for version in versions:
            version_texts[version] = []
            for chapter in chapters:
                progress.update(load_task, description=f"[cyan]Loading {version} - {chapter}")
                try:
                    text, _ = load_version_text(version, chapter)  # Ignore the voice spec
                    version_texts[version].append((chapter, text))
                    
                    # Load original text for this chapter if we haven't already
                    if chapter not in original_texts:
                        original_texts[chapter] = load_original_text(chapter)
                        
                except Exception as e:
                    console.print(f"[red]Warning: Could not load {version} for {chapter}: {e}[/]")
                progress.update(load_task, advance=1)
    
    # Build comparison prompt
    comparison = []
    for version, texts in version_texts.items():
        version_comparison = [f"Version: {version}"]
        for chapter, text in texts:
            version_comparison.append(f"\nChapter: {chapter}")
            version_comparison.append(f"Text:\n{text}")
        comparison.append("\n".join(version_comparison))
    
    comparison_text = "\n\n---\n\n".join(comparison)
    
    console.print(f"[yellow]Running critic analysis...[/]")
    with console.status("[yellow]Critics discussing the versions...[/]"):
        result = get_comparison_feedback(comparison_text, versions, chapters, original_texts)
    
    console.print(f"[bold green]✓ Comparison complete[/]")
    return result

def compare_directories(dir1: pathlib.Path, dir2: pathlib.Path) -> Dict[str, Any]:
    """Compare texts from two directories and return critic feedback."""
    # Get directory names for version labels
    dir1_name = dir1.name
    dir2_name = dir2.name
    
    # Extract more descriptive names for the versions
    # Look for 'auditions' in the path to get experiment name
    dir1_parts = dir1.parts
    dir2_parts = dir2.parts
    
    dir1_full_name = ""
    dir2_full_name = ""
    
    # Try to construct a more descriptive name
    if 'auditions' in dir1_parts:
        idx = dir1_parts.index('auditions')
        if idx + 1 < len(dir1_parts):  # Make sure there's an experiment name after 'auditions'
            experiment_name = dir1_parts[idx+1]
            dir1_full_name = f"{experiment_name} ({dir1.name})"
        else:
            dir1_full_name = dir1.name
    else:
        dir1_full_name = dir1.name
        
    if 'auditions' in dir2_parts:
        idx = dir2_parts.index('auditions')
        if idx + 1 < len(dir2_parts):  # Make sure there's an experiment name after 'auditions'
            experiment_name = dir2_parts[idx+1]
            dir2_full_name = f"{experiment_name} ({dir2.name})"
        else:
            dir2_full_name = dir2.name
    else:
        dir2_full_name = dir2.name
    
    console.print(f"[bold blue]Comparing directories:[/] [cyan]{dir1_full_name}[/] vs [cyan]{dir2_full_name}[/]")
    
    # Load texts from both directories
    try:
        with console.status(f"[yellow]Loading texts from {dir1_full_name}...[/]"):
            dir1_texts = load_texts_from_dir(dir1)
        with console.status(f"[yellow]Loading texts from {dir2_full_name}...[/]"):
            dir2_texts = load_texts_from_dir(dir2)
    except Exception as e:
        console.print(f"[red]Error loading texts: {e}[/]")
        raise
    
    # Build comparison prompt
    dir1_comparison = [f"Version: {dir1_full_name}"]
    for chapter_id, text, _ in dir1_texts:  # Ignore the voice spec
        dir1_comparison.append(f"\nChapter: {chapter_id}")
        dir1_comparison.append(f"Text:\n{text}")
    
    dir2_comparison = [f"Version: {dir2_full_name}"]
    for chapter_id, text, _ in dir2_texts:  # Ignore the voice spec
        dir2_comparison.append(f"\nChapter: {chapter_id}")
        dir2_comparison.append(f"Text:\n{text}")
    
    comparison_text = "\n\n---\n\n".join(["\n".join(dir1_comparison), "\n".join(dir2_comparison)])
    
    # Load original texts for fidelity evaluation
    original_texts = {}
    chapters = [item[0] for item in dir1_texts]
    for chapter_id in chapters:
        original_texts[chapter_id] = load_original_text(chapter_id)
    
    # Extract chapter IDs for metadata  
    versions = [dir1_full_name, dir2_full_name]
    
    console.print(f"[yellow]Running critic analysis...[/]")
    with console.status("[yellow]Critics discussing the texts...[/]"):
        result = get_comparison_feedback(comparison_text, versions, chapters, original_texts)
    
    console.print(f"[bold green]✓ Comparison complete for {len(chapters)} chapters[/]")
    return result 