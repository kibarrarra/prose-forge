"""
elo_ranking.py - Elo rating system and advanced ranking algorithms

This module handles:
- Elo rating calculations and updates
- Smart ranking with initial filtering and pairwise comparisons
- Ranking result formatting and analysis
"""

import random
import statistics
import json
import re
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, SpinnerColumn

from utils.paths import ROOT
from utils.logging_helper import get_logger
from .file_loaders import load_original_text
from .critics import CRITIC_SYSTEM_PROMPT, get_scoring_rubric
from utils.llm_client import get_llm_client

console = Console()
log = get_logger()
MODEL = "gpt-4o-mini"

class Elo:
    """Minimal Elo rating helper."""

    def __init__(self, k: float = 20.0, base: float = 1000.0) -> None:
        self.k = k
        self.base = base
        self._ratings: Dict[str, float] = {}

    def rating(self, name: str) -> float:
        return self._ratings.get(name, self.base)

    def _expect(self, ra: float, rb: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))

    def update(self, winner: str, loser: str) -> None:
        ra, rb = self.rating(winner), self.rating(loser)
        ea = self._expect(ra, rb)
        eb = 1.0 - ea
        self._ratings[winner] = ra + self.k * (1.0 - ea)
        self._ratings[loser] = rb + self.k * (0.0 - eb)

    def leaderboard(self) -> List[Tuple[str, float]]:
        return sorted(self._ratings.items(), key=lambda x: x[1], reverse=True)

def rank_chapter_versions(
    chapter_id: str,
    versions: List[Tuple[str, str, str]],
    original_text: str | None = None,
    output_console: Console = None,
) -> Dict[str, Any]:
    """
    Rank multiple versions of a chapter and provide detailed feedback.
    
    Args:
        chapter_id: The ID of the chapter being evaluated
        versions: List of (persona_name, chapter_text, voice_spec) tuples
        original_text: Optional raw source text for fidelity judging
        output_console: Console instance to use for output (defaults to global console)
        
    Returns:
        Dictionary containing ranking results and analysis
    """
    client = get_llm_client()
    
    # Use provided console or fall back to global console
    active_console = output_console or console
    
    # Create a map of persona names for later reference
    persona_map = {f"DRAFT_{persona}": persona for persona, _, _ in versions}
    
    # Build the user prompt with all chapter versions
    draft_sections = []
    for i, (persona, text, _) in enumerate(versions, 1):  # Ignore voice spec
        # Use persona as draft ID to make results more interpretable
        draft_id = f"DRAFT_{persona}"
        
        draft_section = f"""<<<{draft_id}>>>
Text:
{text}
<<<END>>>"""
        draft_sections.append(draft_section)
    
    drafts_text = "\n\n".join(draft_sections)
    
    # Get rankings with structured JSON output
    system_prompt = CRITIC_SYSTEM_PROMPT + """
    
Format your response as a conversation, with each critic first evaluating each draft individually.
Then have a brief discussion comparing the merits of each draft.

End your response with a JSON block containing your consensus rankings."""
    
    source_block = f"\n\nRAW SOURCE:\n{original_text}" if original_text else ""

    ranking_rubric = f"""Compare {len(versions)} anonymous prose drafts of chapter {chapter_id}.
The original chapter text is provided for judging faithfulness.{source_block}

{get_scoring_rubric("ranking")}

Below are the drafts, separated by markers:

{drafts_text}"""

    # Log the prompts to file
    log_dir = ROOT / "logs" / "prompts"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Log ranking prompt
    with open(log_dir / f"critic_ranking_{chapter_id}_{timestamp}.txt", "w", encoding="utf-8") as f:
        f.write(f"System: {system_prompt}\n\nUser: {ranking_rubric}")
    
    # Only show logging message if we're not using a progress-aware console, or do it quietly
    if output_console is None:
        active_console.print(f"[dim]📝 Logged ranking prompts to {log_dir}[/]")

    # Call the model for rankings with discussion
    try:
        # First, get a discussion between critics
        discussion_res = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": ranking_rubric}
            ]
        )
        discussion_text = discussion_res.choices[0].message.content.strip()
        
        # Check for truncated response
        if not discussion_text:
            log.error(f"Empty response from LLM for chapter {chapter_id}")
            return {
                "chapter_id": chapter_id,
                "versions": [v[0] for v in versions],
                "error": "Empty LLM response"
            }
        
        # Check for common signs of truncation
        truncation_indicators = [
            "- Fidelity to original plot",  # Specific case we saw
            "- Tone & atmosphere: ",
            "- Clarity & readability: ",
            "**Comments**:",
            "**DRAFT_"
        ]
        
        is_truncated = any(discussion_text.rstrip().endswith(indicator.rstrip()) for indicator in truncation_indicators)
        
        if is_truncated:
            log.warning(f"Detected truncated response for chapter {chapter_id} - retrying with shorter prompt")
            
            # Try again with a more concise prompt
            concise_rubric = f"""Rank {len(versions)} prose drafts of chapter {chapter_id} from best to worst.

{get_scoring_rubric("ranking")}

Drafts:
{drafts_text}

Respond with brief analysis followed by JSON rankings."""
            
            discussion_res = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a literary critic. Provide brief analysis and JSON rankings."},
                    {"role": "user", "content": concise_rubric}
                ]
            )
            discussion_text = discussion_res.choices[0].message.content.strip()
            
            # If still truncated, we have a deeper issue
            if any(discussion_text.rstrip().endswith(indicator.rstrip()) for indicator in truncation_indicators):
                log.error(f"Response still truncated after retry for chapter {chapter_id}")
                return {
                    "chapter_id": chapter_id,
                    "versions": [v[0] for v in versions],
                    "error": "LLM response consistently truncated"
                }
        
        # Try to extract the JSON part from the discussion
        json_data = {}
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', discussion_text, re.DOTALL)
        
        if json_match:
            try:
                json_text = json_match.group(1)
                json_data = json.loads(json_text)
                log.info(f"Successfully extracted JSON data from discussion")
            except Exception as json_err:
                log.error(f"Error parsing JSON from discussion: {json_err}")
        else:
            log.debug(f"Could not find JSON data in discussion output - using fallback")
            
            # Try to extract just the JSON object if it exists without the markers
            json_obj_match = re.search(r'\{\s*"table"\s*:\s*\[.*?\]\s*,\s*"analysis"\s*:.*?\}', discussion_text, re.DOTALL)
            if json_obj_match:
                try:
                    json_text = json_obj_match.group(0)
                    json_data = json.loads(json_text)
                    log.info(f"Found JSON object without markers")
                except Exception as json_err2:
                    log.error(f"Error parsing loose JSON from discussion: {json_err2}")
        
        # If we failed to extract JSON, get it separately with a structured format
        if not json_data:
            log.warning(f"Requesting structured JSON separately")
            try:
                json_res = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "Generate only JSON with no other text."},
                        {"role": "user", "content": f"Based on the drafts below, output ONLY a JSON object with this structure:\n{{\"table\": [{{'rank': 1, 'id': '[DRAFT ID]', 'clarity': 9, 'tone': 8, 'plot_fidelity': 9, 'tone_fidelity': 8, 'overall': 9}}], 'analysis': 'Why top draft is best', 'feedback': {{'[DRAFT ID]': 'Feedback'}}}}\n\nDrafts:\n{drafts_text}"}
                    ],
                    response_format={"type": "json_object"}
                )
                json_text = json_res.choices[0].message.content.strip()
                json_data = json.loads(json_text)
            except Exception as json_fallback_err:
                log.error(f"Fallback JSON generation failed: {json_fallback_err}")
                return {
                    "chapter_id": chapter_id,
                    "versions": [v[0] for v in versions],
                    "error": f"Failed to get valid JSON rankings: {json_fallback_err}"
                }
            
        # Get the structured components from the JSON
        table = json_data.get("table", [])
        analysis = json_data.get("analysis", "")
        feedback = json_data.get("feedback", {})
        
        # Validate that we have a complete table
        if not table or len(table) == 0:
            log.error(f"Empty table in JSON response for chapter {chapter_id}")
            return {
                "chapter_id": chapter_id,
                "versions": [v[0] for v in versions],
                "error": "Empty ranking table in LLM response"
            }
        
        # Validate that we have rankings for all versions
        expected_versions = len(versions)
        ranked_versions = len(table)
        if ranked_versions < expected_versions:
            log.warning(f"Only {ranked_versions}/{expected_versions} versions ranked for chapter {chapter_id}")
            # Continue anyway, but note the discrepancy
        
        # Process the table to replace DRAFT_ IDs with actual persona names
        processed_table = []
        for entry in table:
            draft_id = entry.get("id", "")
            # If the ID is in our persona map, replace it with the actual persona name
            if draft_id in persona_map:
                entry["id"] = draft_id
                entry["persona"] = persona_map[draft_id]
            else:
                # Try to handle cases where the LLM might have modified the draft ID format
                for key in persona_map:
                    if key.lower() in draft_id.lower() or persona_map[key].lower() in draft_id.lower():
                        entry["id"] = key
                        entry["persona"] = persona_map[key]
                        break
            processed_table.append(entry)
        
        # Process the feedback to replace DRAFT_ IDs with actual persona names
        processed_feedback = {}
        for draft_id, fb_text in feedback.items():
            # Extract persona name directly from draft_id
            if draft_id.startswith("DRAFT_"):
                persona = draft_id.replace("DRAFT_", "")
            else:
                persona = draft_id
                
            processed_feedback[draft_id] = fb_text
        
        # Return both discussion and structured data
        final_result = {
            "chapter_id": chapter_id,
            "versions": [v[0] for v in versions],
            "discussion": discussion_text,
            "table": processed_table,
            "analysis": analysis,
            "feedback": processed_feedback,
            # For compatibility with old format
            "critic_A_rankings": {"table": processed_table, "analysis": analysis, "feedback": processed_feedback},
            "critic_B_rankings": {"table": processed_table, "analysis": analysis, "feedback": processed_feedback}
        }
        
        return final_result
        
    except Exception as e:
        log.error(f"LLM call failed for chapter {chapter_id}: {e}")
        import traceback
        log.error(f"Traceback: {traceback.format_exc()}")
        return {
            "chapter_id": chapter_id,
            "versions": [v[0] for v in versions],
            "error": f"LLM ranking failed: {e}"
        }

def smart_rank_chapter_versions(
    chapter_id: str,
    versions: List[Tuple[str, str, str]],
    initial_runs: int = 3,
    top_candidates: int = 4,
    temperature: float = 0.8,
    progress: Optional[Progress] = None,
) -> Dict[str, Any]:
    """
    Smart ranking using initial filtering + focused pairwise comparisons.
    
    Args:
        chapter_id: The ID of the chapter being evaluated
        versions: List of (persona_name, chapter_text, voice_spec) tuples
        initial_runs: Number of randomized ranking runs to identify top candidates
        top_candidates: Number of top candidates for pairwise comparisons
        temperature: Higher temperature for more varied initial rankings
        progress: Optional existing progress instance to use
        
    Returns:
        Dictionary containing final ranking results and analysis
    """
    original = load_original_text(chapter_id)
    n_versions = len(versions)
    
    # Use progress.console if available, otherwise use global console
    active_console = progress.console if progress else console
    active_console.print(f"[bold green]Smart ranking {n_versions} versions of {chapter_id}[/]")
    
    # Initialize variables that will be used regardless of progress context
    initial_results = []
    rank_accumulator = {v[0]: [] for v in versions}  # persona -> list of ranks
    avg_ranks = {}
    top_versions = []
    elo = Elo(k=30.0)  # Slightly higher K-factor for faster convergence
    
    # Simple position bias tracking - just store winners for each comparison
    comparison_results = []  # List of (persona_a, persona_b, winner, first_persona)
    
    # Use existing progress or create a new one
    if progress is not None:
        # Use the existing progress instance
        # Step 1: Initial randomized rankings to identify top candidates
        initial_task = progress.add_task(
            f"[cyan]Initial ranking runs for {chapter_id}", 
            total=initial_runs
        )
        
        for run in range(initial_runs):
            # Shuffle the order for this run
            shuffled_versions = versions.copy()
            random.shuffle(shuffled_versions)
            
            progress.update(initial_task, description=f"[cyan]Initial run {run + 1}/{initial_runs} for {chapter_id}")
            
            try:
                result = rank_chapter_versions(
                    chapter_id, 
                    shuffled_versions, 
                    original_text=original,
                    output_console=progress.console  # Use progress-aware console
                )
                
                table = result.get("table", [])
                if table:
                    # Record ranks for each persona
                    for entry in table:
                        persona = entry.get("persona", "")
                        rank = entry.get("rank", n_versions)
                        if persona:
                            rank_accumulator[persona].append(rank)
                            
                    initial_results.append(result)
                    
                    # Temporarily stop the progress to show results cleanly
                    progress.stop()
                    progress.console.print(f"[blue]Initial run {run + 1} results:[/]")
                    sorted_table = sorted(table, key=lambda x: x.get("rank", 0))
                    for entry in sorted_table[:3]:  # Show top 3
                        persona = entry.get("persona", "Unknown")
                        rank = entry.get("rank", "?")
                        overall = entry.get("overall", "?")
                        progress.console.print(f"  [green]{rank}.[/] {persona} (overall: {overall})")
                    progress.start()  # Resume progress
                else:
                    log.warning(f"No table returned for initial run {run + 1}")
                    
            except Exception as e:
                log.error(f"Initial run {run + 1} failed: {e}")
                continue
            
            progress.update(initial_task, advance=1)
        
        # Remove the initial task before proceeding
        progress.remove_task(initial_task)
        
        # Calculate average ranks to identify top candidates
        for persona, ranks in rank_accumulator.items():
            if ranks:
                avg_ranks[persona] = statistics.mean(ranks)
            else:
                avg_ranks[persona] = n_versions  # Worst possible rank
        
        # Sort by average rank (lower is better) and take top candidates
        sorted_personas = sorted(avg_ranks.items(), key=lambda x: x[1])
        top_persona_names = [persona for persona, _ in sorted_personas[:top_candidates]]
        
        # Temporarily stop progress to show detailed average ranking results
        progress.stop()
        progress.console.print(f"[bold yellow]Average rankings across {initial_runs} runs:[/]")
        for i, (persona, avg_rank) in enumerate(sorted_personas, 1):
            if i <= top_candidates:
                progress.console.print(f"  [green]{i}.[/] {persona}: {avg_rank:.1f} → [bold green]ADVANCING[/]")
            else:
                progress.console.print(f"  [dim]{i}.[/] {persona}: {avg_rank:.1f}")
        
        progress.console.print(f"[bold yellow]Top candidates:[/] {', '.join(top_persona_names)}")
        progress.start()  # Resume progress
        
        # Filter versions to only top candidates
        top_versions = [v for v in versions if v[0] in top_persona_names]
        
        # Step 2: Focused pairwise comparisons using Elo
        n_top = len(top_versions)
        total_pairs = (n_top * (n_top - 1)) // 2
        total_comparisons = total_pairs * 2  # Each pair compared in both orders
        
        pairwise_task = progress.add_task(
            f"[magenta]Pairwise comparisons for {chapter_id}", 
            total=total_comparisons
        )
        
        # Compare each pair of top candidates
        comparison_count = 0
        
        for i in range(n_top):
            for j in range(i + 1, n_top):
                left, right = top_versions[i], top_versions[j]
                
                # Run comparison in both orders to cancel position bias
                for swap in [False, True]:
                    first, second = (right, left) if swap else (left, right)
                    comparison_count += 1
                    
                    progress.update(pairwise_task, 
                        description=f"[magenta]{first[0]} vs {second[0]} ({comparison_count}/{total_comparisons})"
                    )
                    
                    try:
                        result = rank_chapter_versions(
                            chapter_id,
                            [first, second],
                            original_text=original,
                            output_console=progress.console  # Use progress-aware console
                        )
                        
                        table = result.get("table", [])
                        if table:
                            table.sort(key=lambda x: x.get("rank", 0))
                            winner_id = table[0].get("id", "").replace("DRAFT_", "")
                            
                            # Store this comparison result
                            comparison_results.append((left[0], right[0], winner_id, first[0]))
                            
                            if winner_id == first[0]:
                                elo.update(first[0], second[0])
                            else:
                                elo.update(second[0], first[0])
                        else:
                            log.warning(f"No ranking returned for {first[0]} vs {second[0]}")
                            
                    except Exception as e:
                        log.error(f"Pairwise comparison failed: {first[0]} vs {second[0]}: {e}")
                        continue
                    
                    progress.update(pairwise_task, advance=1)
        
        # Remove the pairwise task and show bias check results
        progress.remove_task(pairwise_task)
        
        # Temporarily stop progress for final summaries
        progress.stop()
    
    else:
        # Create a standalone progress context (fallback for when called independently)
        progress_columns = [
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
        ]
        
        with Progress(*progress_columns, console=console) as standalone_progress:
            # Step 1: Initial randomized rankings to identify top candidates
            initial_task = standalone_progress.add_task(
                f"[cyan]Initial ranking runs for {chapter_id}", 
                total=initial_runs
            )
            
            for run in range(initial_runs):
                # Shuffle the order for this run
                shuffled_versions = versions.copy()
                random.shuffle(shuffled_versions)
                
                standalone_progress.update(initial_task, description=f"[cyan]Initial run {run + 1}/{initial_runs} for {chapter_id}")
                
                try:
                    result = rank_chapter_versions(
                        chapter_id, 
                        shuffled_versions, 
                        original_text=original,
                        output_console=standalone_progress.console  # Use progress-aware console
                    )
                    
                    table = result.get("table", [])
                    if table:
                        # Record ranks for each persona
                        for entry in table:
                            persona = entry.get("persona", "")
                            rank = entry.get("rank", n_versions)
                            if persona:
                                rank_accumulator[persona].append(rank)
                                
                        initial_results.append(result)
                        
                        # Temporarily stop the progress to show results cleanly
                        standalone_progress.stop()
                        standalone_progress.console.print(f"[blue]Initial run {run + 1} results:[/]")
                        sorted_table = sorted(table, key=lambda x: x.get("rank", 0))
                        for entry in sorted_table[:3]:  # Show top 3
                            persona = entry.get("persona", "Unknown")
                            rank = entry.get("rank", "?")
                            overall = entry.get("overall", "?")
                            standalone_progress.console.print(f"  [green]{rank}.[/] {persona} (overall: {overall})")
                        standalone_progress.start()  # Resume progress
                    else:
                        log.warning(f"No table returned for initial run {run + 1}")
                        
                    standalone_progress.update(initial_task, advance=1)
                
                except Exception as e:
                    log.error(f"Initial run {run + 1} failed: {e}")
                    continue
            
            # Calculate average ranks to identify top candidates
            for persona, ranks in rank_accumulator.items():
                if ranks:
                    avg_ranks[persona] = statistics.mean(ranks)
                else:
                    avg_ranks[persona] = n_versions  # Worst possible rank
            
            # Sort by average rank (lower is better) and take top candidates
            sorted_personas = sorted(avg_ranks.items(), key=lambda x: x[1])
            top_persona_names = [persona for persona, _ in sorted_personas[:top_candidates]]
            
            # Temporarily stop progress to show detailed average ranking results
            standalone_progress.stop()
            standalone_progress.console.print(f"[bold yellow]Average rankings across {initial_runs} runs:[/]")
            for i, (persona, avg_rank) in enumerate(sorted_personas, 1):
                if i <= top_candidates:
                    standalone_progress.console.print(f"  [green]{i}.[/] {persona}: {avg_rank:.1f} → [bold green]ADVANCING[/]")
                else:
                    standalone_progress.console.print(f"  [dim]{i}.[/] {persona}: {avg_rank:.1f}")
            
            standalone_progress.console.print(f"[bold yellow]Top candidates:[/] {', '.join(top_persona_names)}")
            standalone_progress.start()  # Resume progress
            
            # Filter versions to only top candidates
            top_versions = [v for v in versions if v[0] in top_persona_names]
            
            # Step 2: Focused pairwise comparisons using Elo
            n_top = len(top_versions)
            total_pairs = (n_top * (n_top - 1)) // 2
            total_comparisons = total_pairs * 2  # Each pair compared in both orders
            
            pairwise_task = standalone_progress.add_task(
                f"[magenta]Pairwise comparisons for {chapter_id}", 
                total=total_comparisons
            )
            
            # Compare each pair of top candidates
            comparison_count = 0
            
            for i in range(n_top):
                for j in range(i + 1, n_top):
                    left, right = top_versions[i], top_versions[j]
                    
                    # Run comparison in both orders to cancel position bias
                    for swap in [False, True]:
                        first, second = (right, left) if swap else (left, right)
                        comparison_count += 1
                        
                        standalone_progress.update(pairwise_task, 
                            description=f"[magenta]{first[0]} vs {second[0]} ({comparison_count}/{total_comparisons})"
                        )
                        
                        try:
                            result = rank_chapter_versions(
                                chapter_id,
                                [first, second],
                                original_text=original,
                                output_console=standalone_progress.console  # Use progress-aware console
                            )
                            
                            table = result.get("table", [])
                            if table:
                                table.sort(key=lambda x: x.get("rank", 0))
                                winner_id = table[0].get("id", "").replace("DRAFT_", "")
                                
                                # Store this comparison result
                                comparison_results.append((left[0], right[0], winner_id, first[0]))
                                
                                if winner_id == first[0]:
                                    elo.update(first[0], second[0])
                                else:
                                    elo.update(second[0], first[0])
                            else:
                                log.warning(f"No ranking returned for {first[0]} vs {second[0]}")
                                
                        except Exception as e:
                            log.error(f"Pairwise comparison failed: {first[0]} vs {second[0]}: {e}")
                            continue
                        
                        standalone_progress.update(pairwise_task, advance=1)
            
            # Stop progress for final summaries
            standalone_progress.stop()
    
    # Step 3: Check for position bias by looking for contradictions
    contradictions = []
    if comparison_results:
        # Group results by pair (regardless of order)
        pair_results = {}
        for persona_a, persona_b, winner, first_persona in comparison_results:
            # Create canonical pair key (alphabetically sorted)
            pair_key = tuple(sorted([persona_a, persona_b]))
            
            if pair_key not in pair_results:
                pair_results[pair_key] = []
            
            pair_results[pair_key].append({
                'winner': winner,
                'first_persona': first_persona
            })
        
        # Check for contradictions (same pair, different winners)
        for pair_key, results in pair_results.items():
            if len(results) == 2:  # Both orders tested
                winner1 = results[0]['winner']
                winner2 = results[1]['winner']
                
                if winner1 != winner2:
                    contradictions.append({
                        'pair': pair_key,
                        'results': results
                    })
        
        # Show simple position bias summary
        total_pairs = len(pair_results)
        contradiction_count = len(contradictions)
        
        active_console.print(f"\n[bold cyan]Position Bias Check:[/]")
        active_console.print(f"  Pairs tested: {total_pairs}")
        active_console.print(f"  Contradictory results: {contradiction_count} ({contradiction_count/max(total_pairs,1):.1%})")
        
        if contradictions:
            active_console.print(f"  [yellow]⚠️ {contradiction_count} pairs had different winners depending on order:[/]")
            for contradiction in contradictions[:3]:  # Show first few
                pair = contradiction['pair']
                active_console.print(f"    {pair[0]} vs {pair[1]}: winner varies by position")
        else:
            active_console.print(f"  [green]✓ No position bias detected - results were consistent[/]")
    
    # Step 4: Generate final ranking based on Elo scores
    final_leaderboard = elo.leaderboard()
    active_console.print(f"[bold green]Final rankings for {chapter_id}:[/] {', '.join([name for name, _ in final_leaderboard])}")
    
    # Restart progress if we were using an external progress instance (to keep parent progress working)
    if progress is not None:
        progress.start()
    
    # Create final ranking in the expected format
    final_table = []
    for rank, (persona, elo_rating) in enumerate(final_leaderboard, 1):
        # Find the persona in top_versions to get their average initial scores
        persona_version = next((v for v in top_versions if v[0] == persona), None)
        
        # Calculate average scores from initial runs for this persona
        avg_scores = {"clarity": 0, "tone": 0, "plot_fidelity": 0, "tone_fidelity": 0, "overall": 0}
        score_counts = {"clarity": 0, "tone": 0, "plot_fidelity": 0, "tone_fidelity": 0, "overall": 0}
        
        for result in initial_results:
            table = result.get("table", [])
            for entry in table:
                if entry.get("persona", "") == persona:
                    for score_type in avg_scores:
                        if score_type in entry:
                            avg_scores[score_type] += entry[score_type]
                            score_counts[score_type] += 1
                        # Handle backward compatibility with old "faithfulness" field
                        elif score_type in ["plot_fidelity", "tone_fidelity"] and "faithfulness" in entry:
                            avg_scores[score_type] += entry["faithfulness"]
                            score_counts[score_type] += 1
        
        # Calculate averages (or use reasonable defaults)
        for score_type in avg_scores:
            if score_counts[score_type] > 0:
                avg_scores[score_type] = round(avg_scores[score_type] / score_counts[score_type])
            else:
                avg_scores[score_type] = 7  # Default score
        
        final_table.append({
            "rank": rank,
            "id": f"DRAFT_{persona}",
            "persona": persona,
            "clarity": avg_scores["clarity"],
            "tone": avg_scores["tone"], 
            "plot_fidelity": avg_scores["plot_fidelity"],
            "tone_fidelity": avg_scores["tone_fidelity"],
            "overall": avg_scores["overall"],
            "elo_rating": round(elo_rating, 1),
            "avg_initial_rank": avg_ranks.get(persona, n_versions)
        })
    
    # Generate analysis focusing on the winner
    winner = final_leaderboard[0]
    winner_persona = winner[0]
    winner_elo = winner[1]
    winner_avg_rank = avg_ranks.get(winner_persona, n_versions)
    
    analysis = f"The {winner_persona} draft emerges as the clear winner with an Elo rating of {winner_elo:.1f}. This draft consistently ranked {winner_avg_rank:.1f} on average across {initial_runs} initial evaluations and then dominated in focused pairwise comparisons against the other top candidates."
    
    # Generate feedback for non-winning drafts
    feedback = {}
    for rank, (persona, elo_rating) in enumerate(final_leaderboard[1:], 2):
        persona_avg_rank = avg_ranks.get(persona, n_versions)
        feedback[f"DRAFT_{persona}"] = f"Ranks #{rank} with Elo rating {elo_rating:.1f}. Averaged rank {persona_avg_rank:.1f} in initial evaluations but fell short in head-to-head comparisons with top candidates."
    
    # Combine initial run discussions for full context
    combined_discussions = []
    for i, result in enumerate(initial_results, 1):
        if "discussion" in result:
            combined_discussions.append(f"=== Initial Run {i} ===\n{result['discussion']}")
    
    full_discussion = "\n\n".join(combined_discussions)
    
    # Save detailed initial rankings for user review
    if initial_results:
        log_dir = ROOT / "logs" / "initial_rankings"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        initial_summary = {
            "chapter_id": chapter_id,
            "method": "smart_ranking",
            "initial_runs": initial_runs,
            "timestamp": datetime.now().isoformat(),
            "runs": []
        }
        
        for i, result in enumerate(initial_results, 1):
            run_data = {
                "run_number": i,
                "table": result.get("table", []),
                "versions_order": [v[0] for v in (result.get("versions", []) if isinstance(result.get("versions"), list) else versions)],
                "discussion_snippet": result.get("discussion", "")[:500] + "..." if len(result.get("discussion", "")) > 500 else result.get("discussion", "")
            }
            initial_summary["runs"].append(run_data)
        
        # Add average rankings summary
        sorted_personas = sorted(avg_ranks.items(), key=lambda x: x[1])
        initial_summary["average_rankings"] = dict(sorted_personas)
        initial_summary["top_candidates"] = [persona for persona, _ in sorted_personas[:top_candidates]]
        
        log_file = log_dir / f"{chapter_id}_initial_rankings.json"
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(initial_summary, f, indent=2, ensure_ascii=False)
        
        console.print(f"[dim]Initial rankings saved to: {log_file}[/]")
    
    return {
        "chapter_id": chapter_id,
        "versions": [v[0] for v in versions],
        "method": "smart_ranking",
        "initial_runs": initial_runs,
        "top_candidates_evaluated": len(top_versions),
        "table": final_table,
        "analysis": analysis,
        "feedback": feedback,
        "elo_ratings": final_leaderboard,
        "initial_avg_ranks": dict(sorted(avg_ranks.items(), key=lambda x: x[1])),
        "discussion": full_discussion,
        "initial_results": initial_results,  # For debugging/analysis
        # Backward compatibility
        "critic_A_rankings": {"table": final_table, "analysis": analysis, "feedback": feedback},
        "critic_B_rankings": {"table": final_table, "analysis": analysis, "feedback": feedback}
    }

# Keep the old function for backward compatibility but rename it
def pairwise_rank_chapter_versions(
    chapter_id: str,
    versions: List[Tuple[str, str, str]],
    repeats: int = 1,
) -> Dict[str, Any]:
    """
    DEPRECATED: Use smart_rank_chapter_versions instead.
    
    Run pairwise Elo bouts and return final ranking with discussion.
    This function compares ALL pairs which can be expensive.
    """
    log.warning("pairwise_rank_chapter_versions is deprecated. Consider using smart_rank_chapter_versions for better performance.")
    
    original = load_original_text(chapter_id)
    elo = Elo()
    n = len(versions)
    for i in range(n):
        for j in range(i + 1, n):
            left, right = versions[i], versions[j]
            for r in range(repeats):
                first, second = (right, left) if r % 2 else (left, right)
                res = rank_chapter_versions(
                    chapter_id,
                    [first, second],
                    original_text=original,
                    output_console=None  # Keep current behavior for deprecated function
                )
                table = res.get("table", [])
                if table:
                    table.sort(key=lambda x: x.get("rank", 0))
                    winner = table[0].get("id", "").replace("DRAFT_", "")
                else:
                    winner = first[0]
                if winner == first[0]:
                    elo.update(first[0], second[0])
                else:
                    elo.update(second[0], first[0])

    ordered = sorted(versions, key=lambda x: elo.rating(x[0]), reverse=True)
    final = rank_chapter_versions(
        chapter_id,
        ordered,
        original_text=original,
        output_console=None  # Keep current behavior for deprecated function
    )
    final["elo_ratings"] = elo.leaderboard()
    return final 