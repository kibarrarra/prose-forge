"""
simple.py - Basic chapter version ranking

This module provides simple ranking functionality for comparing
multiple versions of the same chapter using critic feedback.
"""

import json
import re
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

from rich.console import Console

from scripts.utils.paths import ROOT
from scripts.utils.logging_helper import get_logger
from scripts.utils.llm_client import get_llm_client
from ..file_loaders import load_original_text
from ..critics import CRITIC_SYSTEM_PROMPT, get_scoring_rubric

console = Console()
log = get_logger()

# Model configuration
MODEL = "claude-3-5-sonnet-20241022"

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
    
    # Log the prompts to console
    if output_console is None:
        active_console.print(f"[dim]📝 Logged ranking prompts to {log_dir}[/]")
    else:
        # For progress-aware consoles, use Rich's log method which handles line breaks properly
        output_console.log(f"📝 Logged ranking prompts to {log_dir}")

    # Call the model for rankings with discussion
    try:
        # Calculate appropriate max_tokens based on content size to prevent truncation
        input_length = len(system_prompt) + len(ranking_rubric)
        # Estimate ~4 chars per token, then add generous buffer for output
        estimated_input_tokens = input_length // 4
        # Allow for substantial output based on number of versions
        output_buffer = max(2000, len(versions) * 800)  # More tokens for more versions
        max_tokens = min(4096, output_buffer)  # Cap at reasonable limit
        
        # Log the call details without disrupting progress
        if output_console is not None:
            output_console.log(f"Making LLM call for {chapter_id} with {len(versions)} versions, max_tokens={max_tokens}")
        else:
            active_console.print(f"[dim]Making LLM call with max_tokens={max_tokens}[/]")
        
        # First, get a discussion between critics
        discussion_res = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": ranking_rubric}
            ],
            max_tokens=max_tokens,
            temperature=0.1  # Lower temperature for more consistent results
        )
        discussion_text = discussion_res.choices[0].message.content.strip()
        
        # Log the actual response for debugging
        with open(log_dir / f"critic_response_{chapter_id}_{timestamp}.txt", "w", encoding="utf-8") as f:
            f.write(discussion_text)
        
        # Check for truncated response
        if not discussion_text:
            if output_console is not None:
                output_console.log(f"[red]Empty response from LLM for chapter {chapter_id}[/red]")
            else:
                log.error(f"Empty response from LLM for chapter {chapter_id}")
            return {
                "chapter_id": chapter_id,
                "versions": [v[0] for v in versions],
                "error": "Empty LLM response"
            }
        
        # More comprehensive truncation detection
        truncation_indicators = [
            "- Fidelity to original plot",  # Specific case we saw
            "- Tone & atmosphere: ",
            "- Clarity & readability: ",
            "**Comments**:",
            "**DRAFT_",
            "- Fidelity to original",
            "Plot fidelity:",
            "Tone fidelity:",
            ": ["  # Incomplete list starts
        ]
        
        # Check if response was truncated by the LLM due to max_tokens
        finish_reason = getattr(discussion_res.choices[0], 'finish_reason', None)
        api_truncated = finish_reason in ['length', 'max_tokens']
        
        # Check for content-based truncation signs
        content_truncated = any(discussion_text.rstrip().endswith(indicator.rstrip()) for indicator in truncation_indicators)
        
        is_truncated = api_truncated or content_truncated
        
        if is_truncated:
            if api_truncated:
                if output_console is not None:
                    output_console.log(f"[yellow]API truncated response (finish_reason: {finish_reason}) for chapter {chapter_id} - retrying with simpler prompt[/yellow]")
                else:
                    log.warning(f"API truncated response (finish_reason: {finish_reason}) for chapter {chapter_id} - retrying with simpler prompt")
            else:
                if output_console is not None:
                    output_console.log(f"[yellow]Detected content truncation in response for chapter {chapter_id} - retrying with simpler prompt[/yellow]")
                else:
                    log.warning(f"Detected content truncation in response for chapter {chapter_id} - retrying with simpler prompt")
            
            # Try again with a much more concise prompt to avoid truncation
            concise_rubric = f"""Rank these {len(versions)} prose drafts from best (rank 1) to worst:

{drafts_text}

Rate each draft 1-10 on: clarity, tone, plot_fidelity, tone_fidelity, overall.

End with JSON:
```json
{{"table": [{{"rank": 1, "id": "DRAFT_name", "clarity": 9, "tone": 8, "plot_fidelity": 9, "tone_fidelity": 8, "overall": 9}}], "analysis": "Brief winner analysis", "feedback": {{"DRAFT_name": "Brief feedback"}}}}
```"""
            
            discussion_res = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a literary critic. Provide rankings with brief analysis."},
                    {"role": "user", "content": concise_rubric}
                ],
                max_tokens=max_tokens,
                temperature=0.1
            )
            discussion_text = discussion_res.choices[0].message.content.strip()
            
            # Log the retry response
            with open(log_dir / f"critic_response_retry_{chapter_id}_{timestamp}.txt", "w", encoding="utf-8") as f:
                f.write(discussion_text)
            
            # Check retry for truncation
            retry_finish_reason = getattr(discussion_res.choices[0], 'finish_reason', None)
            retry_truncated = retry_finish_reason in ['length', 'max_tokens'] or any(discussion_text.rstrip().endswith(indicator.rstrip()) for indicator in truncation_indicators)
            
            if retry_truncated:
                if output_console is not None:
                    output_console.log(f"[red]Response still truncated after retry (finish_reason: {retry_finish_reason}) for chapter {chapter_id}[/red]")
                else:
                    log.error(f"Response still truncated after retry (finish_reason: {retry_finish_reason}) for chapter {chapter_id}")
                return {
                    "chapter_id": chapter_id,
                    "versions": [v[0] for v in versions],
                    "error": f"LLM response consistently truncated (finish_reason: {retry_finish_reason})"
                }
        
        # Try to extract the JSON part from the discussion
        json_data = {}
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', discussion_text, re.DOTALL)
        if json_match:
            try:
                json_text = json_match.group(1)
                if output_console is not None:
                    output_console.log(f"Successfully extracted JSON data from discussion for {chapter_id}")
                else:
                    active_console.print(f"[dim]✓ Extracted JSON from discussion[/]")
                json_data = json.loads(json_text)
            except json.JSONDecodeError as e:
                if output_console is not None:
                    output_console.log(f"[yellow]⚠ JSON parse failed: {e}[/yellow]")
                else:
                    active_console.print(f"[yellow]⚠ JSON parse failed: {e}[/]")
                json_data = {}
        
        # If we failed to extract JSON, get it separately with a structured format
        if not json_data:
            if output_console is not None:
                output_console.log(f"[yellow]⚠ Requesting structured JSON separately for {chapter_id}[/yellow]")
            else:
                active_console.print(f"[yellow]⚠ Requesting fallback JSON[/]")
            try:
                # Create a very explicit JSON request
                json_request = f"""Based on these drafts, output ONLY valid JSON with this exact structure:

{drafts_text}

JSON format (copy exactly, replace values):
{{
  "table": [
    {{"rank": 1, "id": "DRAFT_[persona_name]", "clarity": [1-10], "tone": [1-10], "plot_fidelity": [1-10], "tone_fidelity": [1-10], "overall": [1-10]}},
    {{"rank": 2, "id": "DRAFT_[persona_name]", "clarity": [1-10], "tone": [1-10], "plot_fidelity": [1-10], "tone_fidelity": [1-10], "overall": [1-10]}}
  ],
  "analysis": "[Brief analysis of why top draft wins]",
  "feedback": {{
    "DRAFT_[persona_name]": "[Brief feedback for non-winners]"
  }}
}}

Output ONLY the JSON object."""
                
                json_res = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "You are a JSON generator. Output only valid JSON with no other text."},
                        {"role": "user", "content": json_request}
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=max_tokens,
                    temperature=0.0  # Deterministic for JSON
                )
                json_text = json_res.choices[0].message.content.strip()
                json_data = json.loads(json_text)
                
                # Log the JSON response
                with open(log_dir / f"critic_json_{chapter_id}_{timestamp}.txt", "w", encoding="utf-8") as f:
                    f.write(json_text)
                    
                if output_console is not None:
                    output_console.log(f"✓ Successfully got structured JSON for {chapter_id}")
                else:
                    active_console.print(f"[dim]✓ Got structured JSON[/]")
                    
            except Exception as json_err:
                if output_console is not None:
                    output_console.log(f"[red]✗ Failed to get JSON: {json_err}[/red]")
                else:
                    log.error(f"Failed to get JSON for {chapter_id}: {json_err}")
                return {
                    "chapter_id": chapter_id,
                    "versions": [v[0] for v in versions],
                    "error": f"Failed to get structured JSON: {json_err}"
                }
        
        # Validate and process the JSON data
        if not json_data or "table" not in json_data:
            if output_console is not None:
                output_console.log(f"[red]✗ Invalid JSON structure for {chapter_id}[/red]")
            else:
                log.error(f"Invalid JSON structure for {chapter_id}")
            return {
                "chapter_id": chapter_id,
                "versions": [v[0] for v in versions],
                "error": "Invalid JSON structure in response"
            }
        
        # Map draft IDs back to persona names in the results
        table = json_data.get("table", [])
        for entry in table:
            if "id" in entry and entry["id"] in persona_map:
                entry["persona"] = persona_map[entry["id"]]
        
        # Build the final result
        result = {
            "chapter_id": chapter_id,
            "versions": [v[0] for v in versions],
            "table": table,
            "analysis": json_data.get("analysis", ""),
            "feedback": json_data.get("feedback", {}),
            "discussion": discussion_text,
            "timestamp": timestamp
        }
        
        if output_console is not None:
            output_console.log(f"✓ Completed ranking for {chapter_id}")
        else:
            active_console.print(f"[green]✓ Ranking complete for {chapter_id}[/]")
        
        return result
        
    except Exception as e:
        if output_console is not None:
            output_console.log(f"[red]✗ Error ranking {chapter_id}: {e}[/red]")
        else:
            log.error(f"Error ranking chapter {chapter_id}: {e}")
        return {
            "chapter_id": chapter_id,
            "versions": [v[0] for v in versions],
            "error": str(e)
        } 