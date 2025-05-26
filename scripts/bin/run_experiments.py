#!/usr/bin/env python
"""
run_experiments.py - Run experiments defined in a YAML configuration file.

This script reads experiment configurations from a YAML file and runs each
experiment, following the workflow established in audition_iterative.py but
with configurable prompts, voice specs, and models.

Usage:
    python scripts/bin/run_experiments.py --config experiments.yaml
    python scripts/bin/run_experiments.py --config experiments.yaml --filter cosmic
    python scripts/bin/run_experiments.py --config experiments.yaml --compare exp1 exp2
"""

import argparse
import pathlib
import sys
import yaml
import time
import re
from datetime import datetime
from typing import Dict, List, Any

# Rich imports for progress tracking and tables
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich import box

# Add project root to path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from scripts.utils.logging_helper import get_logger
from scripts.utils.paths import EXP_SUMM_DIR
from scripts.core.experiments.runner import ExperimentRunner

# Create Rich console for pretty output
console = Console()
log = get_logger()

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
                cmd = f'python scripts/bin/run_experiments.py --compare {exp1} {exp2}'
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
    ap.add_argument("--output-dir", default=EXP_SUMM_DIR,
                    help="Directory for experiment outputs")
    
    args = ap.parse_args()
    
    # Create output directory
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # For all operations, require config file
    if not args.config:
        ap.error("the --config argument is required")
    
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
                runner = ExperimentRunner(experiment, output_dir)
                result = runner.run(exp_progress)
                experiment_results.append(result)
                
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
        
        # Track completed experiments for reference
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
    report_file = None
    if experiment_results:
        report_file = generate_html_report(experiment_results, output_dir)
        console.print(f"[bold green]Experiment HTML report generated:[/] [blue]{report_file}[/]")
    
    # Show completion message with suggestions for next steps
    if len(completed_experiments) >= 2:
        console.print(Panel.fit(
            f"[bold green]All experiments completed![/]\n\n"
            f"[yellow]Next steps:[/]\n"
            f"• View the HTML report: {report_file or 'No report generated'}\n"
            f"• Compare experiment results:\n"
            f"  [cyan]python scripts/bin/compare_versions.py --all-finals[/]\n"
            f"• Compare specific experiments:\n"
            f"  [cyan]python scripts/bin/compare_versions.py --dir1 drafts/auditions/{completed_experiments[0]}/final --dir2 drafts/auditions/{completed_experiments[1]}/final[/]",
            title="Experiments Complete",
            border_style="green"
        ))
    elif report_file:
        console.print(f"[bold green]Experiments completed![/] View the HTML report: {report_file}")
    else:
        console.print(f"[bold green]Experiments completed![/] No successful experiments to report.")

if __name__ == "__main__":
    main() 