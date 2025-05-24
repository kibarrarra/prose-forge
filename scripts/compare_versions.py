#!/usr/bin/env python
"""
compare_versions.py – Compare multiple versions of chapters across authors/rounds

Usage:
    python scripts/compare_versions.py lotm_0001 lotm_0002 --versions cosmic_clarity_1 cosmic_clarity_3 lovecraft_2
    python scripts/compare_versions.py lotm_0001 --final-versions cosmic_clarity lovecraft
    python scripts/compare_versions.py --dir1 drafts/auditions/cosmic_clarity/round_1 --dir2 drafts/auditions/lovecraft/round_1 --output comparison.json
"""

import argparse, json, pathlib, textwrap, os, sys
from utils.io_helpers import read_utf8
from utils.paths import ROOT, CTX_DIR
from utils.logging_helper import get_logger
from utils.llm_client import get_llm_client

import tiktoken
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
from tqdm import tqdm
import re

log = get_logger()
MODEL = "gpt-4o-mini"   # cheap for discussion

client = get_llm_client()

def load_version_text(version: str, chapter: str) -> tuple[str, str]:
    """Load chapter text and voice spec for a given version."""
    # Check if this is a final version
    if not any(c.isdigit() for c in version):
        path = ROOT / "drafts" / "auditions" / version / "final" / f"{chapter}.txt"
        spec_path = ROOT / "drafts" / "auditions" / version / "final" / "voice_spec.md"
        
        # Fall back to old path structure if files don't exist
        if not path.exists():
            path = ROOT / "drafts" / "final" / version / f"{chapter}.txt"
            spec_path = ROOT / "drafts" / "final" / version / "voice_spec.md"
    else:
        # Parse audition round
        if "_" in version:
            persona, round_num = version.rsplit("_", 1)
            # Check new structure first (auditions/persona/round_N/)
            path = ROOT / "drafts" / "auditions" / persona / f"round_{round_num}" / f"{chapter}.txt"
            spec_path = ROOT / "drafts" / "auditions" / persona / f"round_{round_num}" / "voice_spec.md"
            
            # Fall back to old structure if files don't exist
            if not path.exists():
                path = ROOT / "drafts" / "auditions" / f"{persona}_{round_num}" / f"{chapter}.txt"
                spec_path = ROOT / "drafts" / "auditions" / f"{persona}_{round_num}" / "voice_spec.md"
        else:
            raise ValueError(f"Invalid version format: {version}")
    
    if not path.exists():
        raise ValueError(f"Version {version} not found for chapter {chapter} at {path}")
    
    return read_utf8(path), read_utf8(spec_path)

def load_texts_from_dir(directory: pathlib.Path) -> list[tuple[str, str, str]]:
    """Load all text files and voice spec from a directory.
    Returns a list of (chapter_id, chapter_text, voice_spec) tuples.
    """
    directory = pathlib.Path(directory)
    if not directory.exists():
        raise ValueError(f"Directory not found: {directory}")
    
    # Find voice spec file
    spec_path = directory / "voice_spec.md"
    if not spec_path.exists():
        log.warning(f"Voice spec not found in {directory}, using empty spec")
        voice_spec = ""
    else:
        voice_spec = read_utf8(spec_path)
    
    # Find all text files (assuming they're chapter files)
    results = []
    for text_file in directory.glob("*.txt"):
        # Skip files that aren't likely chapters
        if text_file.name == "voice_spec.md" or "editor" in text_file.name or "sanity" in text_file.name:
            continue
        
        chapter_id = text_file.stem
        chapter_text = read_utf8(text_file)
        results.append((chapter_id, chapter_text, voice_spec))
    
    if not results:
        raise ValueError(f"No text files found in {directory}")
    
    return results


def load_original_text(chapter_id: str) -> str:
    """Return raw source text for *chapter_id* if available."""
    path = CTX_DIR / f"{chapter_id}.txt"
    if not path.exists():
        log.warning(f"Context not found for {chapter_id} at {path}")
        return ""
    return read_utf8(path)

def chat(system: str, user: str) -> str:
    res = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}]
    )
    return res.choices[0].message.content.strip()

def compare_versions(chapters: list[str], versions: list[str]) -> dict:
    """Compare multiple versions of chapters and return critic feedback."""
    # Load all versions
    version_texts = {}
    for version in versions:
        version_texts[version] = []
        for chapter in chapters:
            text, _ = load_version_text(version, chapter)  # Ignore the voice spec
            version_texts[version].append((chapter, text))
    
    # Build comparison prompt
    comparison = []
    for version, texts in version_texts.items():
        version_comparison = [f"Version: {version}"]
        for chapter, text in texts:
            version_comparison.append(f"\nChapter: {chapter}")
            version_comparison.append(f"Text:\n{text}")
        comparison.append("\n".join(version_comparison))
    
    comparison_text = "\n\n---\n\n".join(comparison)
    
    return get_comparison_feedback(comparison_text, versions, chapters)

def compare_directories(dir1: pathlib.Path, dir2: pathlib.Path) -> dict:
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
    
    # Load texts from both directories
    try:
        dir1_texts = load_texts_from_dir(dir1)
        dir2_texts = load_texts_from_dir(dir2)
    except Exception as e:
        log.error(f"Error loading texts: {e}")
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
    
    # Extract chapter IDs for metadata
    chapters = [item[0] for item in dir1_texts]
    versions = [dir1_full_name, dir2_full_name]
    
    return get_comparison_feedback(comparison_text, versions, chapters)

def get_comparison_feedback(comparison_text: str, versions: list[str], chapters: list[str]) -> dict:
    """Get feedback from critics based on comparison text in a single prompt."""
    # Create a system prompt for two critics in conversation
    system = """You are a simulation of two literary critics (Critic A and Critic B) discussing prose drafts.
    
Critic A focuses on technical writing quality, clarity, and structure.
Critic B focuses on creative elements, atmosphere, and storytelling.

Respond in the format of a conversation between these two critics.
"""
    
    # Create a rubric for the critics to follow
    rubric = textwrap.dedent("""
        As literary critics, provide an *objective evaluation* of the following prose drafts.
        
        Each critic should first independently evaluate the texts on:
        1. Clarity and readability (1–10)
        2. Tone and atmosphere (1–10)
        3. Character development (1–10)
        4. Overall effectiveness (1–10)
        
        For each version:
        - Give the four numeric scores above.
        - Briefly justify each score (≤ 30 words).
        - Highlight most effective elements (≤ 2 bullets).
        
        After individual evaluations, discuss the relative merits of each version. Conclude with a summary paragraph naming which version works best overall and why.
        
        Format your response as a conversation:
        
        CRITIC A: [evaluation of first version]
        
        CRITIC B: [evaluation of first version]
        
        [Continue for all versions, then discussion]
        
        FINAL CONSENSUS: [which version is best and why]
    """)
    
    # Use a single prompt to get the critics' discussion
    result = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"{rubric}\n\n{comparison_text}"}
        ]
    )
    
    discussion = result.choices[0].message.content.strip()
    
    # Extract critic summaries (for backward compatibility)
    # Try to split between critics A and B first evaluations
    parts = discussion.split("CRITIC B:")
    critic_A_summary = parts[0].replace("CRITIC A:", "").strip() if len(parts) > 1 else discussion
    
    # Try to get Critic B's first evaluation
    critic_B_parts = parts[1].split("CRITIC A:") if len(parts) > 1 else []
    critic_B_summary = critic_B_parts[0].strip() if critic_B_parts else ""
    
    return {
        "critic_A_summary": critic_A_summary,
        "critic_B_summary": critic_B_summary,
        "discussion_transcript": discussion,
        "versions": versions,
        "chapters": chapters
    }

def generate_html_output(result: dict) -> str:
    """Convert comparison results to a readable HTML page."""
    # Generate a clean, readable HTML document with Bootstrap styling
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chapter Comparison</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { 
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        .comparison-card {
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .card-header {
            font-weight: bold;
            background-color: #f8f9fa;
        }
        .critic-block {
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        .critic-a {
            background-color: #e7f5ff;
            border-left: 4px solid #74c0fc;
        }
        .critic-b {
            background-color: #f8f9fa;
            border-left: 4px solid #adb5bd;
        }
        .discussion {
            background-color: #fff9db;
            border-left: 4px solid #ffd43b;
            padding: 15px;
            border-radius: 5px;
        }
        pre {
            white-space: pre-wrap;
            font-size: 14px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
        h1 { margin-bottom: 30px; }
        h3 { margin-top: 20px; margin-bottom: 15px; }
        .badge {
            font-size: 14px;
            padding: 6px 10px;
            margin-right: 5px;
        }
        .chapters-list {
            margin-bottom: 20px;
        }
        .version-badge {
            font-size: 16px;
            padding: 8px 15px;
            margin-right: 10px;
            margin-bottom: 10px;
            display: inline-block;
        }
        .version-info {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            margin-bottom: 20px;
        }
        .version-label {
            font-weight: bold;
            margin-right: 10px;
            font-size: 18px;
        }
        .version-description {
            color: #555;
            margin-top: 5px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Chapter Comparison</h1>
"""

    # Add versions and chapters info
    versions = result.get("versions", [])
    chapters = result.get("chapters", [])
    
    # Create a better version display
    html += '<div class="mb-4">\n'
    html += '    <h3>Versions Compared:</h3>\n'
    html += '    <div class="version-info">\n'
    
    for i, version in enumerate(versions):
        version_num = i + 1
        color = "primary" if version_num == 1 else "success"
        html += f'        <div class="badge bg-{color} version-badge">Version {version_num}: {version}</div>\n'
    
    html += '    </div>\n'
    
    # Helper function to enhance critic text by replacing version references
    def enhance_critic_text(text):
        enhanced = text
        
        # If we have exactly 2 versions, we can do smart replacements
        if len(versions) == 2:
            # Replace "Version: name" with "Version 1: name" or "Version 2: name"
            for i, version in enumerate(versions):
                version_num = i + 1
                enhanced = enhanced.replace(f"Version: {version}", f"<strong>Version {version_num}: {version}</strong>")
                enhanced = enhanced.replace(f"Version: {version.lower()}", f"<strong>Version {version_num}: {version}</strong>")
                # Also try to replace just the version name
                if "round" in version.lower():
                    enhanced = enhanced.replace(f"Version: {version.split()[0]}", f"<strong>Version {version_num}: {version}</strong>")
                
                # Add version context to isolated mentions
                if "round" in version.lower():
                    # Avoid double replacement
                    if f"Version {version_num}" not in enhanced:
                        enhanced = enhanced.replace(version.split()[0], f"{version}")
        
        return enhanced
    
    html += '    <h3>Chapters:</h3>\n'
    html += '    <div class="d-flex flex-wrap chapters-list">\n'
    for chapter in chapters:
        html += f'        <span class="badge bg-secondary me-2">{chapter}</span>\n'
    html += '    </div>\n'
    html += '</div>\n'
    
    # Add critic A summary
    if "critic_A_summary" in result:
        html += """
        <div class="card comparison-card">
            <div class="card-header">
                Critic A: Technical Writing & Clarity
            </div>
            <div class="card-body">
                <div class="critic-block critic-a">
"""
        # Format the critic's text, preserving paragraphs and enhancing version references
        critic_a_text = enhance_critic_text(result["critic_A_summary"])
        critic_a_text = critic_a_text.replace("\n\n", "<br><br>").replace("\n", "<br>")
        html += f"                {critic_a_text}\n"
        html += """
                </div>
            </div>
        </div>
"""

    # Add critic B summary
    if "critic_B_summary" in result:
        html += """
        <div class="card comparison-card">
            <div class="card-header">
                Critic B: Creative Writing & Atmosphere
            </div>
            <div class="card-body">
                <div class="critic-block critic-b">
"""
        critic_b_text = enhance_critic_text(result["critic_B_summary"])
        critic_b_text = critic_b_text.replace("\n\n", "<br><br>").replace("\n", "<br>")
        html += f"                {critic_b_text}\n"
        html += """
                </div>
            </div>
        </div>
"""

    # Add discussion
    if "discussion_transcript" in result:
        html += """
        <div class="card comparison-card">
            <div class="card-header">
                Critics Discussion & Final Verdict
            </div>
            <div class="card-body">
                <div class="discussion">
"""
        discussion_text = enhance_critic_text(result["discussion_transcript"])
        discussion_text = discussion_text.replace("\n\n", "<br><br>").replace("\n", "<br>")
        html += f"                {discussion_text}\n"
        html += """
                </div>
            </div>
        </div>
"""

    # Complete the HTML
    html += """
    </div>
</body>
</html>
"""
    
    return html

def gather_final_versions(
    root_dir: pathlib.Path = ROOT / "drafts" / "auditions"
) -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Gather all final versions of chapters from experiment directories.
    
    Args:
        root_dir: Root directory where experiment audition folders are located
        
    Returns:
        Dictionary mapping chapter IDs to lists of (persona_name, chapter_text, voice_spec) tuples
    """
    # Organize by chapter for easy comparison
    chapters: Dict[str, List[Tuple[str, str, str]]] = {}
    
    # Walk through all audition directories
    for persona_dir in root_dir.iterdir():
        if not persona_dir.is_dir():
            continue
            
        final_dir = persona_dir / "final"
        if not final_dir.exists() or not final_dir.is_dir():
            continue
            
        # Look for voice spec in final directory
        spec_path = final_dir / "voice_spec.md"
        if spec_path.exists():
            voice_spec = read_utf8(spec_path)
        else:
            log.warning(f"Voice spec not found in {final_dir}, using empty spec")
            voice_spec = ""
            
        # Find all chapter files in final directory
        for chapter_file in final_dir.glob("*.txt"):
            # Skip non-chapter files
            if "editor" in chapter_file.name or "sanity" in chapter_file.name:
                continue
                
            chapter_id = chapter_file.stem
            chapter_text = read_utf8(chapter_file)
            
            # Organize by chapter
            if chapter_id not in chapters:
                chapters[chapter_id] = []
                
            chapters[chapter_id].append((persona_dir.name, chapter_text, voice_spec))
    
    return chapters

def rank_chapter_versions(
    chapter_id: str,
    versions: List[Tuple[str, str, str]],
    original_text: str | None = None,
) -> Dict[str, Any]:
    """
    Rank multiple versions of a chapter and provide detailed feedback.
    
    Args:
        chapter_id: The ID of the chapter being evaluated
        versions: List of (persona_name, chapter_text, voice_spec) tuples
        original_text: Optional raw source text for fidelity judging
        
    Returns:
        Dictionary containing ranking results and analysis
    """
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
    system_prompt = """You are two literary critics (A and B) discussing prose drafts.
    
Format your response as a conversation, with each critic first evaluating each draft individually.
Then have a brief discussion comparing the merits of each draft.

End your response with a JSON block containing your consensus rankings.
"""
    
    source_block = f"\n\nRAW SOURCE:\n{original_text}" if original_text else ""

    ranking_rubric = f"""Compare {len(versions)} anonymous prose drafts of chapter {chapter_id}.
The original chapter text is provided for judging faithfulness.{source_block}
For each draft, provide:

1. Clarity & readability — score 1-10
2. Tone & atmosphere — score 1-10
3. Faithfulness to original story events — score 1-10
4. Overall literary quality — score 1-10

Each critic should evaluate each draft first. Then, have a brief discussion about the drafts.
Finally, reach a consensus on the rankings.

Your response must end with structured data in the following JSON format:

```json
{{
  "table": [
    {{"rank": 1, "id": "DRAFT_[persona name]", "clarity": 9, "tone": 8, "faithfulness": 9, "overall": 9}},
    {{"rank": 2, "id": "DRAFT_[persona name]", "clarity": 7, "tone": 8, "faithfulness": 8, "overall": 8}}
  ],
  "analysis": "Why the top draft is best...",
  "feedback": {{
    "DRAFT_[persona name]": "Feedback for second place...",
    "DRAFT_[persona name]": "Feedback for third place..."
  }}
}}
```

Below are the drafts, separated by markers:

{drafts_text}"""

    # Log the prompts to file
    log_dir = ROOT / "logs" / "prompts"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Log ranking prompt
    with open(log_dir / f"critic_ranking_{chapter_id}_{timestamp}.txt", "w", encoding="utf-8") as f:
        f.write(f"System: {system_prompt}\n\nUser: {ranking_rubric}")
    
    log.info(f"Logged ranking prompts to {log_dir}")

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
            log.warning(f"Could not find JSON data in discussion output")
            
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
            json_res = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "Generate only JSON with no other text."},
                    {"role": "user", "content": f"Based on the drafts below, output ONLY a JSON object with this structure:\n{{\"table\": [{{'rank': 1, 'id': '[DRAFT ID]', 'clarity': 9, 'tone': 8, 'faithfulness': 9, 'overall': 9}}], 'analysis': 'Why top draft is best', 'feedback': {{'[DRAFT ID]': 'Feedback'}}}}\n\nDrafts:\n{drafts_text}"}
                ],
                response_format={"type": "json_object"}
            )
            json_text = json_res.choices[0].message.content.strip()
            json_data = json.loads(json_text)
            
        # Get the structured components from the JSON
        table = json_data.get("table", [])
        analysis = json_data.get("analysis", "")
        feedback = json_data.get("feedback", {})
        
        # Check if analysis is a placeholder or empty, and try to extract better analysis from discussion
        if not analysis or analysis == "Why top draft is best" or analysis.strip() == "":
            # Try to find a consensus statement in the discussion
            consensus_patterns = [
                r"FINAL CONSENSUS:\s*(.*?)(?=$|(?:```json))",
                r"CONSENSUS:\s*(.*?)(?=$|(?:```json))",
                r"VERDICT:\s*(.*?)(?=$|(?:```json))",
                r"After discussing all drafts.*?agree that\s*(.*?)(?=$|(?:```json))",
                r"(?:In conclusion|To conclude|Ultimately|In summary),\s*(.*?)(?=$|(?:```json))",
                r"(?:After|Having) review(?:ed|ing) all (?:the )?drafts[^.]*\.(.*?)(?=$|(?:```json))",
                r"(?:Draft|DRAFT)_([a-zA-Z0-9_]+)\s+is (?:clearly|definitely|certainly) the (?:best|strongest|most effective)(.*?)(?=$|(?:```json))"
            ]
            
            for pattern in consensus_patterns:
                consensus_match = re.search(pattern, discussion_text, re.DOTALL | re.IGNORECASE)
                if consensus_match:
                    analysis = consensus_match.group(1).strip()
                    break
                    
            # If still no good analysis and we have a table, try to create one
            if (not analysis or analysis == "Why top draft is best" or analysis.strip() == "") and table:
                # Try to find the top-ranked draft
                top_entry = None
                for entry in table:
                    if entry.get("rank", 0) == 1:
                        top_entry = entry
                        break
                
                if top_entry:
                    top_id = top_entry.get("id", "")
                    
                    # If we have a proper draft ID, try to extract a comment from the discussion
                    if top_id and "DRAFT_" in top_id:
                        # Try multiple patterns to extract meaningful analysis for the top draft
                        analysis_patterns = [
                            # Look for critic comments after draft scores
                            rf"{re.escape(top_id)}.*?(?:Critic [AB]|Overall Literary Quality:\s*\d+)\s*[:\.]\s*(.*?)(?=DRAFT_|Critic [AB]:|#{1,6}|$)",
                            # Look for any paragraph following the draft scores
                            rf"{re.escape(top_id)}.*?Overall[^:]*:\s*\d+\s*[^\d\n#](.*?)(?=DRAFT_|#{1,6}|$)",
                            # Look for content between draft name and next section
                            rf"{re.escape(top_id)}.*?\n(.*?)(?=DRAFT_|-{3,}|#{1,6}|$)"
                        ]
                        
                        analysis_text = ""
                        for pattern in analysis_patterns:
                            top_match = re.search(pattern, discussion_text, re.DOTALL)
                            if top_match and top_match.group(1):
                                raw_text = top_match.group(1).strip()
                                
                                # Clean up the extracted text
                                cleaned_text = raw_text
                                # Remove Markdown headers
                                cleaned_text = re.sub(r'#{1,6}\s+[Dd]raft\s+\d+[:.]\s*', '', cleaned_text)
                                # Remove any draft references
                                cleaned_text = re.sub(r'[Dd]raft\s+\d+[:.]\s*', '', cleaned_text)
                                # Remove Markdown formatting
                                cleaned_text = re.sub(r'\*\*|\*|`|__', '', cleaned_text)
                                # Remove critic prefixes
                                cleaned_text = re.sub(r'(?:Critic [AB]:|--)', '', cleaned_text)
                                # Handle bullet points
                                cleaned_text = re.sub(r'^\s*-\s*', '', cleaned_text)
                                # Remove Markdown dividers
                                cleaned_text = re.sub(r'-{3,}', '', cleaned_text)
                                # Remove extra whitespace
                                cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                                
                                if cleaned_text and len(cleaned_text) > 10:  # Make sure it's substantive
                                    # Get the first 2-3 sentences for a more comprehensive analysis
                                    sentences = re.split(r'(?<=[.!?])\s+', cleaned_text)
                                    if sentences:
                                        analysis_text = ' '.join(sentences[:3]) if len(sentences) > 1 else sentences[0]
                                        break
                        
                        if analysis_text:
                            persona_name = top_id.replace('DRAFT_', '')
                            analysis = f"The {persona_name} draft ranks highest due to its balanced scores across all categories. {analysis_text}"
                        else:
                            # Fall back to generic analysis based on scores
                            persona_name = top_id.replace('DRAFT_', '')
                            analysis = f"The {persona_name} draft ranks highest with strong scores in clarity ({top_entry.get('clarity', '?')}), tone ({top_entry.get('tone', '?')}), faithfulness ({top_entry.get('faithfulness', '?')}), and overall quality ({top_entry.get('overall', '?')})."
        
        # Check if feedback is empty or lacking entries for all drafts except the top one
        if not feedback and table:
            # Generate feedback for each draft except the top-ranked one
            feedback = {}
            
            # Identify the top-ranked draft to skip it
            top_draft_id = None
            for entry in table:
                if entry.get("rank", 0) == 1:
                    top_draft_id = entry.get("id", "")
                    break
            
            # Generate feedback for all other drafts
            for entry in table:
                draft_id = entry.get("id", "")
                
                # Skip the top-ranked draft, as it's covered in the analysis
                if draft_id == top_draft_id:
                    continue
                
                # Try to extract feedback from the discussion
                if "DRAFT_" in draft_id:
                    # Try multiple patterns to find specific feedback for this draft
                    feedback_patterns = [
                        # Look for critic comments after draft scores
                        rf"{re.escape(draft_id)}.*?(?:Critic [AB]|Overall Literary Quality:\s*\d+)\s*[:\.]\s*(.*?)(?=DRAFT_|Critic [AB]:|#{1,6}|$)",
                        # Look for bullet points in critic assessment
                        rf"{re.escape(draft_id)}.*?- (.*?)(?=DRAFT_|-{3,}|#{1,6}|$)",
                        # Look for statements following "shows strength in" or similar
                        rf"{re.escape(draft_id)}.*?shows (?:strength|strengths) in (.*?)(?=DRAFT_|#{1,6}|$)",
                        # Look for sentences directly following the scores
                        rf"{re.escape(draft_id)}.*?Overall[^:]*:\s*\d+\s*[^\d\n#](.*?)(?=DRAFT_|#{1,6}|$)",
                        # Look for any content after the draft ID that's not just scores
                        rf"{re.escape(draft_id)}.*?Literary Quality:\s*\d+\s*[^\d\n#](.*?)(?=DRAFT_|#{1,6}|$)"
                    ]
                    
                    feedback_text = ""
                    for pattern in feedback_patterns:
                        feedback_match = re.search(pattern, discussion_text, re.DOTALL | re.IGNORECASE)
                        if feedback_match and feedback_match.group(1):
                            raw_text = feedback_match.group(1).strip()
                            
                            # Clean up the extracted text
                            cleaned_text = raw_text
                            # Remove Markdown headers
                            cleaned_text = re.sub(r'#{1,6}\s+[Dd]raft\s+\d+[:.]\s*', '', cleaned_text)
                            # Remove any draft references
                            cleaned_text = re.sub(r'[Dd]raft\s+\d+[:.]\s*', '', cleaned_text)
                            # Remove Markdown formatting
                            cleaned_text = re.sub(r'\*\*|\*|`|__', '', cleaned_text)
                            # Remove critic prefixes
                            cleaned_text = re.sub(r'(?:Critic [AB]:|--)', '', cleaned_text)
                            # Handle bullet points
                            cleaned_text = re.sub(r'^\s*-\s*', '', cleaned_text)
                            # Remove Markdown dividers
                            cleaned_text = re.sub(r'-{3,}', '', cleaned_text)
                            # Remove extra whitespace
                            cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                            
                            if cleaned_text and len(cleaned_text) > 10:  # Make sure it's substantive
                                # Extract first 1-2 sentences for concise feedback
                                sentences = re.split(r'(?<=[.!?])\s+', cleaned_text)
                                if sentences:
                                    feedback_text = ' '.join(sentences[:2]) if len(sentences) > 1 else sentences[0]
                                    break
                    
                    if feedback_text:
                        feedback[draft_id] = feedback_text
                    else:
                        # Generate generic feedback based on scores
                        strengths = []
                        if entry.get("clarity", 0) >= 8: 
                            strengths.append("clarity")
                        if entry.get("tone", 0) >= 8:
                            strengths.append("atmospheric tone")
                        if entry.get("faithfulness", 0) >= 8:
                            strengths.append("faithfulness to the original")
                        
                        strength_text = ""
                        if strengths:
                            if len(strengths) == 1:
                                strength_text = f"Shows strength in {strengths[0]}."
                            elif len(strengths) == 2:
                                strength_text = f"Shows strengths in {strengths[0]} and {strengths[1]}."
                            else:
                                strength_text = f"Shows strengths in {', '.join(strengths[:-1])}, and {strengths[-1]}."
                        
                        rank_num = entry.get('rank', '?')
                        overall = entry.get('overall', 0)
                        feedback[draft_id] = f"Ranks #{rank_num} with an overall score of {overall}/10. {strength_text}"
            
            # Make sure we have feedback entries for all drafts in the table
            for entry in table:
                draft_id = entry.get("id", "")
                # Skip the top-ranked draft and drafts that already have feedback
                if draft_id == top_draft_id or draft_id in feedback:
                    continue
                    
                # Create generic feedback for this draft
                strengths = []
                if entry.get("clarity", 0) >= 8: 
                    strengths.append("clarity")
                if entry.get("tone", 0) >= 8:
                    strengths.append("tone")
                if entry.get("faithfulness", 0) >= 8:
                    strengths.append("faithfulness")
                
                strength_text = ""
                if strengths:
                    if len(strengths) == 1:
                        strength_text = f"Shows strength in {strengths[0]}."
                    elif len(strengths) == 2:
                        strength_text = f"Shows strengths in {strengths[0]} and {strengths[1]}."
                    else:
                        strength_text = f"Shows strengths in {', '.join(strengths[:-1])}, and {strengths[-1]}."
                
                rank_num = entry.get('rank', '?')
                overall = entry.get('overall', 0)
                feedback[draft_id] = f"Ranks #{rank_num} with an overall score of {overall}/10. {strength_text}"
        
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


def pairwise_rank_chapter_versions(
    chapter_id: str,
    versions: List[Tuple[str, str, str]],
    repeats: int = 1,
) -> Dict[str, Any]:
    """Run pairwise Elo bouts and return final ranking with discussion."""
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
    )
    final["elo_ratings"] = elo.leaderboard()
    return final

def enhance_critic_text(text, chapter_id=None):
    """Helper function to format critic text for HTML display."""
    # Basic enhancements...
    return text.replace("\n\n", "<br><br>").replace("\n", "<br>")

def generate_ranking_html(rankings: List[Dict[str, Any]]) -> str:
    """
    Generate an HTML report for all chapter rankings.
    
    Args:
        rankings: List of rankings data for different chapters
        
    Returns:
        HTML string for the report
    """
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chapter Version Rankings</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { 
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        .chapter-card {
            margin-bottom: 40px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            overflow: hidden;
        }
        .card-header {
            font-weight: bold;
            background-color: #f8f9fa;
            padding: 15px 20px;
            border-bottom: 1px solid #e9ecef;
        }
        .rankings-table {
            margin: 0;
        }
        .analysis-block {
            padding: 20px;
            background-color: #fff9db;
            border-left: 4px solid #ffd43b;
            margin: 15px 20px;
            border-radius: 5px;
        }
        .feedback-block {
            padding: 20px;
            background-color: #f8f9fa;
            margin: 15px 20px;
            border-radius: 5px;
        }
        .feedback-item {
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }
        .feedback-item:last-child {
            border-bottom: none;
        }
        .rank-1 {
            background-color: #fff4e6;
        }
        .rank-1 td:first-child {
            position: relative;
        }
        .rank-1 td:first-child::before {
            content: "🏆";
            position: absolute;
            left: 5px;
            top: 50%;
            transform: translateY(-50%);
        }
        .rank-badge {
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 12px;
            display: inline-block;
            min-width: 30px;
            text-align: center;
        }
        .badge-1 { background-color: gold; color: #333; }
        .badge-2 { background-color: #C0C0C0; color: #333; }
        .badge-3 { background-color: #CD7F32; color: white; }
        .badge-other { background-color: #e9ecef; color: #333; }
        .raw-json {
            display: none;
            font-family: monospace;
            white-space: pre-wrap;
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 20px;
            max-height: 300px;
            overflow: auto;
        }
        .json-toggle {
            cursor: pointer;
            text-decoration: underline;
            color: #0d6efd;
            margin-left: 20px;
            font-size: 0.9em;
        }
        .score-cell {
            text-align: center;
            font-weight: bold;
        }
        .timestamp {
            color: #666;
            font-size: 0.8em;
            margin-bottom: 20px;
        }
        h1 { margin-bottom: 20px; }
        h2 { 
            margin-top: 40px; 
            margin-bottom: 20px;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
        }
        .critic-a {
            background-color: #e7f5ff;
            border-left: 4px solid #74c0fc;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        .critic-b {
            background-color: #f8f9fa;
            border-left: 4px solid #adb5bd;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        .nav-tabs {
            margin-bottom: 20px;
        }
        .tab-content {
            padding: 20px;
            border: 1px solid #dee2e6;
            border-top: none;
            border-radius: 0 0 5px 5px;
        }
    </style>
    <script>
        function toggleJson(chapterId) {
            const jsonElem = document.getElementById('json-' + chapterId);
            if (jsonElem.style.display === 'none' || jsonElem.style.display === '') {
                jsonElem.style.display = 'block';
            } else {
                jsonElem.style.display = 'none';
            }
        }
    </script>
</head>
<body>
    <div class="container">
        <h1>Chapter Version Rankings</h1>
        <div class="timestamp">Generated on: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</div>
"""

    # Summary section: total chapters analyzed
    html += f"""
        <div class="alert alert-info">
            <strong>{len(rankings)}</strong> chapters analyzed with multiple versions
        </div>
        
        <h2>Chapters</h2>
"""

    # Pre-process rankings to extract critic data from discussion if needed
    for ranking in rankings:
        chapter_id = ranking.get("chapter_id", "Unknown")
        # Skip if error occurred
        if "error" in ranking:
            continue
            
        # Check if we have a detailed discussion but empty critic tables
        if "discussion" in ranking:
            discussion = ranking["discussion"]
            
            # Process critic A if needed
            if not ranking.get("critic_A_rankings") or not ranking["critic_A_rankings"].get("table") or len(ranking["critic_A_rankings"].get("table", [])) <= 1:
                # Try multiple patterns to extract Critic A's evaluations
                critic_a_patterns = [
                    r"Critic A Evaluation(.*?)(?:Critic B|FINAL CONSENSUS|$)",
                    r"Critic A'?s? Evaluations?(.*?)(?:Critic B|FINAL CONSENSUS|$)",
                    r"### Critic A(.*?)(?:### Critic B|FINAL CONSENSUS|$)",
                    r"CRITIC A:(.*?)(?:CRITIC B:|FINAL CONSENSUS|$)"
                ]
                
                critic_a_text = ""
                for pattern in critic_a_patterns:
                    critic_a_match = re.search(pattern, discussion, re.DOTALL | re.IGNORECASE)
                    if critic_a_match:
                        critic_a_text = critic_a_match.group(1).strip()
                        break
                
                if critic_a_text:
                    # Extract evaluations for each draft - try different formats
                    draft_patterns = [
                        # Format: DRAFT_name, numbered list with colons (1. Clarity & readability: 8)
                        r"DRAFT_([a-zA-Z0-9_]+).*?Clarity[^:]*:\s*(\d+).*?Tone[^:]*:\s*(\d+).*?Faithfulness[^:]*:\s*(\d+).*?Overall[^:]*:\s*(\d+)",
                        # Format: **DRAFT_name**, numbered list with colons
                        r"\*\*DRAFT_([a-zA-Z0-9_]+)\*\*.*?Clarity[^:]*:\s*(\d+).*?Tone[^:]*:\s*(\d+).*?Faithfulness[^:]*:\s*(\d+).*?Overall[^:]*:\s*(\d+)",
                        # Format with different terms: clarity/tone/faith/literary quality
                        r"DRAFT_([a-zA-Z0-9_]+).*?[Cc]larity[^:]*:\s*(\d+).*?[Tt]one[^:]*:\s*(\d+).*?[Ff]aithfulness[^:]*:\s*(\d+).*?[Ll]iterary [Qq]uality[^:]*:\s*(\d+)",
                        # Format with bullets instead of numbers
                        r"DRAFT_([a-zA-Z0-9_]+).*?[Cc]larity[^:]*:\s*(\d+).*?[Tt]one[^:]*:\s*(\d+).*?[Ff]aithfulness[^:]*:\s*(\d+).*?[Oo]verall[^:]*:\s*(\d+)"
                    ]
                    
                    # Try each pattern until we find matches
                    critic_a_table = []
                    processed_personas = set()
                    
                    for draft_pattern in draft_patterns:
                        score_matches = re.findall(draft_pattern, critic_a_text, re.DOTALL | re.IGNORECASE)
                        
                        if score_matches:
                            for draft_id, clarity, tone, faith, overall in score_matches:
                                # Skip if we've already processed this persona
                                if draft_id in processed_personas:
                                    continue
                                
                                processed_personas.add(draft_id)
                                
                                entry = {
                                    "id": f"DRAFT_{draft_id}",
                                    "persona": draft_id,
                                    "clarity": int(clarity),
                                    "tone": int(tone),
                                    "faithfulness": int(faith), 
                                    "overall": int(overall)
                                }
                                critic_a_table.append(entry)
                            
                            # If we found matches, no need to try other patterns
                            break
            
            # Only proceed if we found entries
            if critic_a_table:
                # Sort by overall score descending
                critic_a_table.sort(key=lambda x: (x["overall"] + x["clarity"] + x["tone"] + x["faithfulness"]), reverse=True)
                
                # Assign ranks
                for i, entry in enumerate(critic_a_table, 1):
                    entry["rank"] = i
                
                # Extract critic A analysis - use multiple patterns
                analysis_patterns = [
                    r"After reviewing all drafts.*?(?:DRAFT_|Critic B|FINAL CONSENSUS|$)",
                    r"Overall[,\.] .*?(?:DRAFT_|Critic B|FINAL CONSENSUS|$)",
                    r"In summary[,\.] .*?(?:DRAFT_|Critic B|FINAL CONSENSUS|$)"
                ]
                
                # First try to extract a general summary from critic A
                analysis = ""
                for pattern in analysis_patterns:
                    analysis_match = re.search(pattern, critic_a_text, re.DOTALL | re.IGNORECASE)
                    if analysis_match:
                        raw_text = analysis_match.group(0).strip()
                        
                        # Clean up the extracted text
                        cleaned_text = raw_text
                        # Remove Markdown headers
                        cleaned_text = re.sub(r'#{1,6}\s+.*?$', '', cleaned_text, flags=re.MULTILINE)
                        # Remove any draft references
                        cleaned_text = re.sub(r'DRAFT_[a-zA-Z0-9_]+', '', cleaned_text)
                        # Remove Markdown formatting
                        cleaned_text = re.sub(r'\*\*|\*|`|__', '', cleaned_text)
                        # Remove extra whitespace
                        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                        
                        if cleaned_text:
                            analysis = cleaned_text
                            break
                
                # If no general summary, extract comment about top-ranked draft
                if not analysis and critic_a_table:
                    top_draft = critic_a_table[0]
                    draft_id = top_draft["persona"]
                    
                    # Look for comment about this draft
                    draft_pattern = rf"DRAFT_{re.escape(draft_id)}.*?(?:Overall.*?:\s*\d+)(.*?)(?:DRAFT_|\*\*DRAFT_|$)"
                    draft_match = re.search(draft_pattern, critic_a_text, re.DOTALL)
                    
                    if draft_match and draft_match.group(1):
                        cleaned_text = draft_match.group(1).strip()
                        # Remove Markdown formatting
                        cleaned_text = re.sub(r'\*\*|\*|`|__', '', cleaned_text)
                        # Remove extra whitespace
                        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                        
                        if cleaned_text:
                            analysis = f"The {draft_id} draft is strongest with scores of {top_draft['clarity']} for clarity, {top_draft['tone']} for tone, {top_draft['faithfulness']} for faithfulness, and {top_draft['overall']} overall. {cleaned_text}"
                
                # If still no analysis, create a generic one
                if not analysis and critic_a_table:
                    top_draft = critic_a_table[0]
                    draft_id = top_draft["persona"]
                    analysis = f"The {draft_id} draft is strongest with scores of {top_draft['clarity']} for clarity, {top_draft['tone']} for tone, {top_draft['faithfulness']} for faithfulness, and {top_draft['overall']} overall."
                
                # Create critic A rankings if they don't exist
                if not ranking.get("critic_A_rankings"):
                    ranking["critic_A_rankings"] = {}
                    
                ranking["critic_A_rankings"]["table"] = critic_a_table
                ranking["critic_A_rankings"]["analysis"] = analysis
                
                log.info(f"Rebuilt Critic A table for {chapter_id} from discussion with {len(critic_a_table)} drafts")
        
        # Process critic B if needed
        if not ranking.get("critic_B_rankings") or not ranking["critic_B_rankings"].get("table") or len(ranking["critic_B_rankings"].get("table", [])) <= 1:
            # Try multiple patterns to extract Critic B's evaluations
            critic_b_patterns = [
                r"Critic B Evaluation(.*?)(?:FINAL CONSENSUS|$)",
                r"Critic B'?s? Evaluations?(.*?)(?:FINAL CONSENSUS|$)",
                r"### Critic B(.*?)(?:FINAL CONSENSUS|$)",
                r"CRITIC B:(.*?)(?:FINAL CONSENSUS|$)"
            ]
            
            critic_b_text = ""
            for pattern in critic_b_patterns:
                critic_b_match = re.search(pattern, discussion, re.DOTALL | re.IGNORECASE)
                if critic_b_match:
                    critic_b_text = critic_b_match.group(1).strip()
                    break
            
            if critic_b_text:
                # Extract evaluations for each draft - try different formats
                draft_patterns = [
                    # Format: DRAFT_name, numbered list with colons (1. Clarity & readability: 8)
                    r"DRAFT_([a-zA-Z0-9_]+).*?Clarity[^:]*:\s*(\d+).*?Tone[^:]*:\s*(\d+).*?Faithfulness[^:]*:\s*(\d+).*?Overall[^:]*:\s*(\d+)",
                    # Format: **DRAFT_name**, numbered list with colons
                    r"\*\*DRAFT_([a-zA-Z0-9_]+)\*\*.*?Clarity[^:]*:\s*(\d+).*?Tone[^:]*:\s*(\d+).*?Faithfulness[^:]*:\s*(\d+).*?Overall[^:]*:\s*(\d+)",
                    # Format with different terms: clarity/tone/faith/literary quality
                    r"DRAFT_([a-zA-Z0-9_]+).*?[Cc]larity[^:]*:\s*(\d+).*?[Tt]one[^:]*:\s*(\d+).*?[Ff]aithfulness[^:]*:\s*(\d+).*?[Ll]iterary [Qq]uality[^:]*:\s*(\d+)",
                    # Format with bullets instead of numbers
                    r"DRAFT_([a-zA-Z0-9_]+).*?[Cc]larity[^:]*:\s*(\d+).*?[Tt]one[^:]*:\s*(\d+).*?[Ff]aithfulness[^:]*:\s*(\d+).*?[Oo]verall[^:]*:\s*(\d+)"
                ]
                
                # Try each pattern until we find matches
                critic_b_table = []
                processed_personas = set()
                
                for draft_pattern in draft_patterns:
                    score_matches = re.findall(draft_pattern, critic_b_text, re.DOTALL | re.IGNORECASE)
                    
                    if score_matches:
                        for draft_id, clarity, tone, faith, overall in score_matches:
                            # Skip if we've already processed this persona
                            if draft_id in processed_personas:
                                continue
                            
                            processed_personas.add(draft_id)
                            
                            entry = {
                                "id": f"DRAFT_{draft_id}",
                                "persona": draft_id,
                                "clarity": int(clarity),
                                "tone": int(tone),
                                "faithfulness": int(faith), 
                                "overall": int(overall)
                            }
                            critic_b_table.append(entry)
                        
                        # If we found matches, no need to try other patterns
                        break
            
            # Only proceed if we found entries
            if critic_b_table:
                # Sort by overall score descending
                critic_b_table.sort(key=lambda x: (x["overall"] + x["clarity"] + x["tone"] + x["faithfulness"]), reverse=True)
                
                # Assign ranks
                for i, entry in enumerate(critic_b_table, 1):
                    entry["rank"] = i
                
                # Extract critic B analysis - use multiple patterns
                analysis_patterns = [
                    r"After reviewing all drafts.*?(?:DRAFT_|FINAL CONSENSUS|$)",
                    r"Overall[,\.] .*?(?:DRAFT_|FINAL CONSENSUS|$)",
                    r"In summary[,\.] .*?(?:DRAFT_|FINAL CONSENSUS|$)"
                ]
                
                # First try to extract a general summary from critic B
                analysis = ""
                for pattern in analysis_patterns:
                    analysis_match = re.search(pattern, critic_b_text, re.DOTALL | re.IGNORECASE)
                    if analysis_match:
                        raw_text = analysis_match.group(0).strip()
                        
                        # Clean up the extracted text
                        cleaned_text = raw_text
                        # Remove Markdown headers
                        cleaned_text = re.sub(r'#{1,6}\s+.*?$', '', cleaned_text, flags=re.MULTILINE)
                        # Remove any draft references
                        cleaned_text = re.sub(r'DRAFT_[a-zA-Z0-9_]+', '', cleaned_text)
                        # Remove Markdown formatting
                        cleaned_text = re.sub(r'\*\*|\*|`|__', '', cleaned_text)
                        # Remove extra whitespace
                        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                        
                        if cleaned_text:
                            analysis = cleaned_text
                            break
                
                # If no general summary, extract comment about top-ranked draft
                if not analysis and critic_b_table:
                    top_draft = critic_b_table[0]
                    draft_id = top_draft["persona"]
                    
                    # Look for comment about this draft
                    draft_pattern = rf"DRAFT_{re.escape(draft_id)}.*?(?:Overall.*?:\s*\d+)(.*?)(?:DRAFT_|\*\*DRAFT_|$)"
                    draft_match = re.search(draft_pattern, critic_b_text, re.DOTALL)
                    
                    if draft_match and draft_match.group(1):
                        cleaned_text = draft_match.group(1).strip()
                        # Remove Markdown formatting
                        cleaned_text = re.sub(r'\*\*|\*|`|__', '', cleaned_text)
                        # Remove extra whitespace
                        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                        
                        if cleaned_text:
                            analysis = f"The {draft_id} draft is strongest with scores of {top_draft['clarity']} for clarity, {top_draft['tone']} for tone, {top_draft['faithfulness']} for faithfulness, and {top_draft['overall']} overall. {cleaned_text}"
                    
                    # If still no analysis, create a generic one
                    if not analysis and critic_b_table:
                        top_draft = critic_b_table[0]
                        draft_id = top_draft["persona"]
                        analysis = f"The {draft_id} draft is strongest with scores of {top_draft['clarity']} for clarity, {top_draft['tone']} for tone, {top_draft['faithfulness']} for faithfulness, and {top_draft['overall']} overall."
                    
                    # Create critic B rankings if they don't exist
                    if not ranking.get("critic_B_rankings"):
                        ranking["critic_B_rankings"] = {}
                        
                    ranking["critic_B_rankings"]["table"] = critic_b_table
                    ranking["critic_B_rankings"]["analysis"] = analysis
                    
                    log.info(f"Rebuilt Critic B table for {chapter_id} from discussion with {len(critic_b_table)} drafts")

    # Generate a section for each chapter
    for ranking in rankings:
        chapter_id = ranking.get("chapter_id", "Unknown")
        
        # Skip if error occurred
        if "error" in ranking:
            html += f"""
        <div class="card chapter-card">
            <div class="card-header">
                Chapter: {chapter_id}
            </div>
            <div class="card-body">
                <div class="alert alert-danger">
                    <strong>Error:</strong> {ranking.get("error", "Unknown error")}
                </div>
                <div class="raw-json" id="json-{chapter_id}">
                    {json.dumps(ranking, indent=2)}
                </div>
                <div class="json-toggle" onclick="toggleJson('{chapter_id}')">Show Raw JSON</div>
            </div>
        </div>
"""
            continue
        
        # Build ranking table using the main table from critic A
        table_html = """
                <ul class="nav nav-tabs" id="resultTabs" role="tablist">
                    <li class="nav-item" role="presentation">
                        <button class="nav-link active" id="consensus-tab" data-bs-toggle="tab" 
                                data-bs-target="#consensus" type="button" role="tab" 
                                aria-controls="consensus" aria-selected="true">Consensus Rankings</button>
                    </li>
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" id="critic-a-tab" data-bs-toggle="tab" 
                                data-bs-target="#critic-a" type="button" role="tab" 
                                aria-controls="critic-a" aria-selected="false">Critic A (Technical)</button>
                    </li>
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" id="critic-b-tab" data-bs-toggle="tab" 
                                data-bs-target="#critic-b" type="button" role="tab" 
                                aria-controls="critic-b" aria-selected="false">Critic B (Creative)</button>
                    </li>
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" id="discussion-tab" data-bs-toggle="tab" 
                                data-bs-target="#discussion" type="button" role="tab" 
                                aria-controls="discussion" aria-selected="false">Critics Discussion</button>
                    </li>
                </ul>
                <div class="tab-content" id="resultTabsContent">
                    <div class="tab-pane fade show active" id="consensus" role="tabpanel" aria-labelledby="consensus-tab">
"""
        
        # Process ranking table
        table_entries = ranking.get("table", [])
        
        # If we only have one entry but discussion shows multiple, try to extract from discussion
        if len(table_entries) <= 1 and "discussion" in ranking:
            discussion = ranking["discussion"]
            # Look for draft entries in the discussion
            draft_pattern = r"DRAFT_([a-zA-Z0-9_]+)"
            draft_matches = re.findall(draft_pattern, discussion)
            
            # If we found multiple drafts but our table doesn't have them, rebuild table
            unique_drafts = set(draft_matches)
            if len(unique_drafts) > 1 and len(table_entries) <= 1:
                log.info(f"Rebuilding table for {chapter_id} from discussion data ({len(unique_drafts)} drafts found)")
                
                # Extract scores by parsing the discussion text
                rebuilt_table = []
                score_pattern = r"DRAFT_([a-zA-Z0-9_]+).*?Clarity[^:]*:\s*(\d+).*?Tone[^:]*:\s*(\d+).*?Faithfulness[^:]*:\s*(\d+).*?Overall[^:]*:\s*(\d+)"
                score_matches = re.findall(score_pattern, discussion, re.DOTALL)
                
                # Keep track of personas we've already processed to avoid duplicates
                processed_personas = set()
                
                for i, (draft_id, clarity, tone, faith, overall) in enumerate(score_matches, 1):
                    # Skip if we've already processed this persona
                    if draft_id in processed_personas:
                        continue
                        
                    processed_personas.add(draft_id)
                    
                    rebuilt_entry = {
                        "rank": i,
                        "id": f"DRAFT_{draft_id}",
                        "persona": draft_id,
                        "clarity": int(clarity),
                        "tone": int(tone),
                        "faithfulness": int(faith), 
                        "overall": int(overall)
                    }
                    rebuilt_table.append(rebuilt_entry)
                
                # Sort by overall score descending
                rebuilt_table.sort(key=lambda x: (x["overall"] + x["clarity"] + x["tone"] + x["faithfulness"]), reverse=True)
                
                # Assign ranks
                for i, entry in enumerate(rebuilt_table, 1):
                    entry["rank"] = i
                    
                # Use the rebuilt table
                if rebuilt_table:
                    table_entries = rebuilt_table
                    # Also update the original ranking data for consistency
                    ranking["table"] = rebuilt_table

                    # Extract consensus analysis and feedback from discussion
                    # Try multiple patterns for consensus/final verdict
                    consensus_patterns = [
                        r"FINAL CONSENSUS:\s*(.*?)(?=$|(?:```json))",
                        r"CONSENSUS:\s*(.*?)(?=$|(?:```json))",
                        r"VERDICT:\s*(.*?)(?=$|(?:```json))",
                        r"After discussing all drafts.*?agree that\s*(.*?)(?=$|(?:```json))",
                        r"(?:In conclusion|To conclude|Ultimately|In summary),\s*(.*?)(?=$|(?:```json))",
                        r"(?:After|Having) review(?:ed|ing) all (?:the )?drafts[^.]*\.(.*?)(?=$|(?:```json))",
                        r"(?:Draft|DRAFT)_([a-zA-Z0-9_]+)\s+is (?:clearly|definitely|certainly) the (?:best|strongest|most effective)(.*?)(?=$|(?:```json))"
                    ]
                    
                    # Try to find a consensus statement
                    analysis_text = ""
                    for pattern in consensus_patterns:
                        consensus_match = re.search(pattern, discussion, re.DOTALL | re.IGNORECASE)
                        if consensus_match:
                            analysis_text = consensus_match.group(1).strip()
                            break
                    
                    # If we couldn't find a consensus statement, try to create one from the top entry
                    if not analysis_text and rebuilt_table:
                        top_entry = rebuilt_table[0]
                        persona = top_entry["persona"]
                        
                        # Look for specific evaluations of the top-ranked draft
                        top_draft_pattern = rf"DRAFT_{persona}.*?(?:-\s*(.*?)(?=DRAFT_|$))"
                        top_match = re.search(top_draft_pattern, discussion, re.DOTALL)
                        
                        if top_match and top_match.group(1):
                            comment = top_match.group(1).strip()
                            analysis_text = f"The {persona} draft ranks highest due to its balanced scores across all categories. {comment}"
                        else:
                            # Generic analysis based on scores
                            analysis_text = f"The {persona} draft ranks highest with strong scores in clarity ({top_entry['clarity']}), tone ({top_entry['tone']}), faithfulness ({top_entry['faithfulness']}), and overall quality ({top_entry['overall']})."
                    
                    # Update the analysis in the ranking data
                    ranking["analysis"] = analysis_text
                    
                    # Extract feedback for each draft except the top one
                    feedback = {}
                    for entry in rebuilt_table[1:]:  # Skip the top entry
                        draft_id = entry["id"]
                        persona = entry["persona"]
                        
                        # Try to find specific feedback for this draft
                        feedback_pattern = rf"DRAFT_{persona}.*?(?:-\s*(.*?)(?=DRAFT_|$))"
                        feedback_match = re.search(feedback_pattern, discussion, re.DOTALL)
                        
                        if feedback_match and feedback_match.group(1):
                            # Extract the first 1-2 sentences for concise feedback
                            comment = feedback_match.group(1).strip()
                            sentences = re.split(r'(?<=[.!?])\s+', comment)
                            short_comment = ' '.join(sentences[:2])
                            feedback[draft_id] = short_comment
                        else:
                            # Generate generic feedback based on scores
                            strengths = []
                            if entry["clarity"] >= 8: 
                                strengths.append("clarity")
                            if entry["tone"] >= 8:
                                strengths.append("atmospheric tone")
                            if entry["faithfulness"] >= 8:
                                strengths.append("faithfulness to the original")
                            
                            strength_text = ""
                            if strengths:
                                if len(strengths) == 1:
                                    strength_text = f"Shows strength in {strengths[0]}."
                                elif len(strengths) == 2:
                                    strength_text = f"Shows strengths in {strengths[0]} and {strengths[1]}."
                                else:
                                    strength_text = f"Shows strengths in {', '.join(strengths[:-1])}, and {strengths[-1]}."
                            
                            rank_num = entry.get('rank', '?')
                            overall = entry.get('overall', 0)
                            feedback[draft_id] = f"Ranks #{rank_num} with an overall score of {overall}/10. {strength_text}"
                    
                    # Update the feedback in the ranking data
                    ranking["feedback"] = feedback
        
        # Add consensus table
        table_html += """
                        <table class="table table-striped rankings-table">
                            <thead>
                                <tr>
                                    <th>Rank</th>
                                    <th>Version</th>
                                    <th>Clarity</th>
                                    <th>Tone</th>
                                    <th>Faithfulness</th>
                                    <th>Overall</th>
                                    <th>Total</th>
                                </tr>
                            </thead>
                            <tbody>
"""
        
        for entry in table_entries:
            rank = entry.get("rank", 0)
            draft_id = entry.get("id", "")
            
            # Extract the persona name from the entry or the draft_id
            persona = entry.get("persona", "")
            if not persona:
                if draft_id.startswith("DRAFT_"):
                    persona = draft_id.replace("DRAFT_", "")
                else:
                    persona = draft_id
            
            # Get scores
            clarity = entry.get("clarity", 0)
            tone = entry.get("tone", 0)
            faithfulness = entry.get("faithfulness", 0)
            overall = entry.get("overall", 0)
            total = clarity + tone + faithfulness + overall
            
            # Determine badge class
            badge_class = f"badge-{rank}" if rank <= 3 else "badge-other"
            
            # Add table row
            table_html += f"""
                                <tr class="{'rank-1' if rank == 1 else ''}">
                                    <td style="padding-left: 30px;"><span class="rank-badge {badge_class}">{rank}</span></td>
                                    <td>{persona}</td>
                                    <td class="score-cell">{clarity}</td>
                                    <td class="score-cell">{tone}</td>
                                    <td class="score-cell">{faithfulness}</td>
                                    <td class="score-cell">{overall}</td>
                                    <td class="score-cell">{total}</td>
                                </tr>
"""
        
        table_html += """
                            </tbody>
                        </table>
                        
                        <h4>Winner Analysis</h4>
                        <div class="analysis-block">
"""
        
        # Get analysis and feedback
        analysis = ranking.get("analysis", "No analysis provided.")
        feedback = ranking.get("feedback", {})
        
        # If analysis is missing/empty but discussion exists, try to extract from there
        if (not analysis or analysis == "No analysis provided.") and "discussion" in ranking:
            discussion = ranking["discussion"]
            # Look for a final consensus or verdict section
            final_consensus_pattern = r"FINAL CONSENSUS:\s*(.*?)(?=$|(?:CRITIC [AB]:))"
            consensus_match = re.search(final_consensus_pattern, discussion, re.DOTALL | re.IGNORECASE)
            
            if consensus_match:
                analysis = consensus_match.group(1).strip()
            else:
                # Try alternative patterns
                alt_patterns = [
                    r"(?:FINAL|CONSENSUS|VERDICT):\s*(.*?)(?=$|(?:CRITIC [AB]:))",
                    r"(?:In conclusion|To conclude|Ultimately),\s*(.*?)(?=$|(?:CRITIC [AB]:))"
                ]
                
                for pattern in alt_patterns:
                    alt_match = re.search(pattern, discussion, re.DOTALL | re.IGNORECASE)
                    if alt_match:
                        analysis = alt_match.group(1).strip()
                        break
        
        # Format the analysis for better display
        if analysis:
            analysis_html = analysis.replace("\n", "<br>")
            table_html += f"""
                            <p class="lead">{analysis_html}</p>
"""
        else:
            table_html += """
                            <p class="text-muted">No analysis provided</p>
"""
        
        table_html += """
                        </div>
                        
                        <h4>Feedback for Other Versions</h4>
                        <div class="feedback-block">
"""
        
        # Build feedback HTML
        if not feedback and "discussion" in ranking:
            discussion = ranking["discussion"]
            # Extract draft IDs
            draft_ids = []
            for entry in table_entries:
                draft_id = entry.get("id", "")
                if draft_id:
                    draft_ids.append(draft_id)
            
            # Try to extract feedback for each draft
            extracted_feedback = {}
            for draft_id in draft_ids:
                # Skip drafts that won the comparison (usually no feedback needed)
                if any(entry.get("rank", 0) == 1 and entry.get("id", "") == draft_id for entry in table_entries):
                    continue
                
                # Look for sections that discuss this draft
                draft_pattern = rf"{re.escape(draft_id)}.*?(?:-|:)\s*(.*?)(?=$|(?:DRAFT_|CRITIC [AB]:))"
                draft_match = re.search(draft_pattern, discussion, re.DOTALL)
                
                if draft_match:
                    # Extract the comment about this draft
                    comment = draft_match.group(1).strip()
                    # Keep only first 2 sentences for conciseness
                    sentences = re.split(r'(?<=[.!?])\s+', comment)
                    short_comment = ' '.join(sentences[:2])
                    extracted_feedback[draft_id] = short_comment
            
            # Use extracted feedback if we found any
            if extracted_feedback:
                feedback = extracted_feedback
        
        for draft_id, fb_text in feedback.items():
            # Extract persona name directly from draft_id
            if draft_id.startswith("DRAFT_"):
                persona = draft_id.replace("DRAFT_", "")
            else:
                persona = draft_id
                
            table_html += f"""
                            <div class="feedback-item">
                                <strong>{persona}:</strong> {fb_text}
                            </div>
"""
        
        table_html += """
                        </div>
                    </div>
"""
        
        # Add Critic A tab content
        if "critic_A_rankings" in ranking:
            critic_a = ranking["critic_A_rankings"]
            critic_a_table = critic_a.get("table", [])
            
            table_html += """
                    <div class="tab-pane fade" id="critic-a" role="tabpanel" aria-labelledby="critic-a-tab">
                        <div class="critic-a">
                            <h4>Critic A: Technical Writing & Clarity</h4>
                            <table class="table table-striped">
                                <thead>
                                    <tr>
                                        <th>Rank</th>
                                        <th>Version</th>
                                        <th>Clarity</th>
                                        <th>Tone</th>
                                        <th>Faithfulness</th>
                                        <th>Overall</th>
                                        <th>Total</th>
                                    </tr>
                                </thead>
                                <tbody>
"""
            
            for entry in critic_a_table:
                rank = entry.get("rank", 0)
                draft_id = entry.get("id", "")
                persona = entry.get("persona", "")
                clarity = entry.get("clarity", 0)
                tone = entry.get("tone", 0)
                faithfulness = entry.get("faithfulness", 0)
                overall = entry.get("overall", 0)
                total = clarity + tone + faithfulness + overall
                
                badge_class = f"badge-{rank}" if rank <= 3 else "badge-other"
                
                table_html += f"""
                                    <tr class="{'rank-1' if rank == 1 else ''}">
                                        <td style="padding-left: 30px;"><span class="rank-badge {badge_class}">{rank}</span></td>
                                        <td>{persona}</td>
                                        <td class="score-cell">{clarity}</td>
                                        <td class="score-cell">{tone}</td>
                                        <td class="score-cell">{faithfulness}</td>
                                        <td class="score-cell">{overall}</td>
                                        <td class="score-cell">{total}</td>
                                    </tr>
"""
            
            table_html += """
                                </tbody>
                            </table>
                            
                            <h5>Analysis</h5>
                            <p>""" + critic_a.get("analysis", "No analysis provided.") + """</p>
                        </div>
                    </div>
"""
        
        # Add Critic B tab content
        if "critic_B_rankings" in ranking:
            critic_b = ranking["critic_B_rankings"]
            critic_b_table = critic_b.get("table", [])
            
            table_html += """
                    <div class="tab-pane fade" id="critic-b" role="tabpanel" aria-labelledby="critic-b-tab">
                        <div class="critic-b">
                            <h4>Critic B: Creative Writing & Atmosphere</h4>
                            <table class="table table-striped">
                                <thead>
                                    <tr>
                                        <th>Rank</th>
                                        <th>Version</th>
                                        <th>Clarity</th>
                                        <th>Tone</th>
                                        <th>Faithfulness</th>
                                        <th>Overall</th>
                                        <th>Total</th>
                                    </tr>
                                </thead>
                                <tbody>
"""
            
            for entry in critic_b_table:
                rank = entry.get("rank", 0)
                draft_id = entry.get("id", "")
                persona = entry.get("persona", "")
                clarity = entry.get("clarity", 0)
                tone = entry.get("tone", 0)
                faithfulness = entry.get("faithfulness", 0)
                overall = entry.get("overall", 0)
                total = clarity + tone + faithfulness + overall
                
                badge_class = f"badge-{rank}" if rank <= 3 else "badge-other"
                
                table_html += f"""
                                    <tr class="{'rank-1' if rank == 1 else ''}">
                                        <td style="padding-left: 30px;"><span class="rank-badge {badge_class}">{rank}</span></td>
                                        <td>{persona}</td>
                                        <td class="score-cell">{clarity}</td>
                                        <td class="score-cell">{tone}</td>
                                        <td class="score-cell">{faithfulness}</td>
                                        <td class="score-cell">{overall}</td>
                                        <td class="score-cell">{total}</td>
                                    </tr>
"""
            
            table_html += """
                                </tbody>
                            </table>
                            
                            <h5>Analysis</h5>
                            <p>""" + critic_b.get("analysis", "No analysis provided.") + """</p>
                        </div>
                    </div>
"""
        
        # Add discussion tab content
        if "discussion" in ranking:
            discussion = ranking["discussion"]
            
            # Prepare the discussion tab content
            table_html += """
                    <div class="tab-pane fade" id="discussion" role="tabpanel" aria-labelledby="discussion-tab">
                        <h4>Critics' Discussion</h4>
                        <div class="discussion">
"""
            # Format discussion text and replace line breaks with <br>
            discussion_text = discussion.replace("\n", "<br>")
            
            # Clean up markdown JSON code blocks for better display
            discussion_text = re.sub(r'```json.*?```', '<em>(See structured rankings in other tabs)</em>', discussion_text, flags=re.DOTALL)
            
            table_html += f"                        {discussion_text}\n"
            table_html += """
                        </div>
                    </div>
"""
        
        # Close the tab content div
        table_html += """
                </div>
                <div class="raw-json" id="json-""" + chapter_id + """">
                    """ + json.dumps(ranking, indent=2) + """
                </div>
                <div class="json-toggle" onclick="toggleJson('""" + chapter_id + """')">Show Raw JSON</div>
"""
        
        # Add chapter card to HTML
        html += f"""
        <div class="card chapter-card">
            <div class="card-header">
                Chapter: {chapter_id}
            </div>
            <div class="card-body">
                {table_html}
            </div>
        </div>
"""
    
    # Add Bootstrap JavaScript for tabs
    html += """
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    </div>
</body>
</html>
"""
    
    return html

def rank_all_chapters(output_path: pathlib.Path, addl_dirs: Optional[pathlib.Path] = None, max_versions: int = 0) -> None:
    """
    Rank all available chapter versions and generate an HTML report.
    
    Args:
        output_path: Path to save the HTML report
        addl_dirs: Directory containing additional drafts for comparison (structure: addl_dirs/draft_type/chapter.txt)
        max_versions: Maximum number of versions to compare per chapter (0 = no limit)
    """
    log.info("Gathering all final chapter versions...")
    chapters_map = gather_final_versions()
    
    # Add additional drafts if provided
    if addl_dirs and addl_dirs.exists():
        log.info(f"Looking for additional drafts in {addl_dirs}")
        for draft_type_dir in addl_dirs.iterdir():
            if not draft_type_dir.is_dir():
                continue
                
            draft_type = draft_type_dir.name
            log.info(f"Processing additional draft type: {draft_type}")
            
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
        log.error("No chapters found with multiple versions")
        return
        
    log.info(f"Ranking multiple versions across {len(chapters_map)} chapters")
    
    # Process each chapter
    rankings = []
    with tqdm(total=len(chapters_map), desc="Ranking chapters") as progress:
        for chapter_id, versions in chapters_map.items():
            if len(versions) < 2:
                log.warning(f"Chapter {chapter_id} has only {len(versions)} version(s), skipping")
                progress.update(1)
                continue
                
            # Limit the number of versions to compare (if too many)
            if max_versions > 0 and len(versions) > max_versions:
                log.warning(f"Chapter {chapter_id} has {len(versions)} versions, limiting to {max_versions}")
                versions = versions[:max_versions]
                
            log.info(f"Ranking {len(versions)} versions of chapter {chapter_id}")
            try:
                ranking = pairwise_rank_chapter_versions(chapter_id, versions)
                rankings.append(ranking)
            except Exception as e:
                log.error(f"Failed to rank chapter {chapter_id}: {e}")
                # Add detailed error info with traceback
                import traceback
                log.error(f"Traceback: {traceback.format_exc()}")
                rankings.append({
                    "chapter_id": chapter_id,
                    "versions": [v[0] for v in versions],
                    "error": f"Ranking failed: {e}"
                })
            progress.update(1)
    
    # Generate HTML report
    log.info("Generating HTML report...")
    html_content = generate_ranking_html(rankings)
    
    # Save HTML report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    log.info(f"Ranking report saved to {output_path}")

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
    ap.add_argument("--addl-dirs", help="Directory containing additional drafts for comparison (structure: addl_dirs/draft_type/chapter.txt)")
    ap.add_argument("--max-versions", type=int, default=0,
                    help="Maximum number of versions to compare per chapter (0 = no limit)")
    args = ap.parse_args()
    
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
            out_dir = ROOT / "drafts" / "comparisons"
            out_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = out_dir / f"ranking_all_finals_{timestamp}.html"
        
        # Run the ranking process
        try:
            # Pass additional directories if specified
            addl_dirs = pathlib.Path(args.addl_dirs) if args.addl_dirs else None
            max_versions = args.max_versions
            rank_all_chapters(out_path, addl_dirs, max_versions)
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
            out_dir = ROOT / "drafts" / "comparisons"
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
        out_dir = ROOT / "drafts" / "comparisons"
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