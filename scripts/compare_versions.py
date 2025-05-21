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
from utils.paths import ROOT
from utils.logging_helper import get_logger
from utils.llm_client import get_llm_client

import tiktoken
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
from tqdm import tqdm

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
            text, spec = load_version_text(version, chapter)
            version_texts[version].append((chapter, text, spec))
    
    # Build comparison prompt
    comparison = []
    for version, texts in version_texts.items():
        version_comparison = [f"Version: {version}"]
        for chapter, text, spec in texts:
            version_comparison.append(f"\nChapter: {chapter}")
            version_comparison.append(f"Voice Spec:\n{spec}")
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
    for chapter_id, text, spec in dir1_texts:
        dir1_comparison.append(f"\nChapter: {chapter_id}")
        dir1_comparison.append(f"Voice Spec:\n{spec}")
        dir1_comparison.append(f"Text:\n{text}")
    
    dir2_comparison = [f"Version: {dir2_full_name}"]
    for chapter_id, text, spec in dir2_texts:
        dir2_comparison.append(f"\nChapter: {chapter_id}")
        dir2_comparison.append(f"Voice Spec:\n{spec}")
        dir2_comparison.append(f"Text:\n{text}")
    
    comparison_text = "\n\n---\n\n".join(["\n".join(dir1_comparison), "\n".join(dir2_comparison)])
    
    # Extract chapter IDs for metadata
    chapters = [item[0] for item in dir1_texts]
    versions = [dir1_full_name, dir2_full_name]
    
    return get_comparison_feedback(comparison_text, versions, chapters)

def get_comparison_feedback(comparison_text: str, versions: list[str], chapters: list[str]) -> dict:
    """Get feedback from critics based on comparison text."""
    # Get critic feedback
    rubric = textwrap.dedent("""
        You are a literary reviewer.  Provide an *objective evaluation* **only**.
        Compare these versions on:
        1. Clarity and readability (1–10)
        2. Tone and atmosphere (1–10)
        3. Consistency with voice spec (1–10)
        4. Overall effectiveness (1–10)
        
        For each version:
        - Give the four numeric scores above.
        - Briefly justify each score (≤ 30 words).
        - Highlight most effective elements (≤ 2 bullets).
        
        Do not suggest concrete edits or improvements.  You are judging, not editing.
        
        Conclude with a summary paragraph naming which version works best overall and why.
    """)
    
    critic_A = chat("You are Critic A, focused on technical writing quality and clarity.", 
                   f"{rubric}\n\n{comparison_text}")
    critic_B = chat("You are Critic B, focused on creative writing and atmosphere.",
                   f"{rubric}\n\n{comparison_text}")
    
    discussion = chat(
        "You are Critic A and Critic B in turn. Hold up to 3 back-and-forths. "
        "End with a clear recommendation of which version works best and why.",
        f"CRITIC A:\n{critic_A}\n\nCRITIC B:\n{critic_B}"
    )
    
    return {
        "critic_A_summary": critic_A,
        "critic_B_summary": critic_B,
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
) -> Dict[str, Any]:
    """
    Rank multiple versions of a chapter and provide detailed feedback.
    
    Args:
        chapter_id: The ID of the chapter being evaluated
        versions: List of (persona_name, chapter_text, voice_spec) tuples
        
    Returns:
        Dictionary containing ranking results and analysis
    """
    # Build the user prompt with all chapter versions
    draft_sections = []
    for i, (persona, text, spec) in enumerate(versions, 1):
        # Use persona as draft ID to make results more interpretable
        draft_id = f"DRAFT_{persona}"
        
        draft_section = f"""<<<{draft_id}>>>
Voice-Spec:
{spec}

Text:
{text}
<<<END>>>"""
        draft_sections.append(draft_section)
    
    drafts_text = "\n\n".join(draft_sections)
    
    # First, get rankings from each critic independently
    critic_a_system = "You are Critic A, focused on technical writing quality and clarity."
    critic_b_system = "You are Critic B, focused on creative writing and atmosphere."
    
    ranking_rubric = f"""Compare {len(versions)} anonymous prose drafts of chapter {chapter_id}.
For each draft, provide:

1. Clarity & readability — score 1-10
2. Tone & atmosphere — score 1-10
3. Faithfulness to original story events — score 1-10
4. Overall literary quality — score 1-10

Then produce:

A. A ranked list - highest overall score first - break ties with literary quality - show the four numeric scores in a table.

B. A concise paragraph (≤150 words) explaining **why** the top draft outperforms the others, citing concrete strengths.

C. One bullet of constructive feedback for **each** non-winning draft (≤20 words each).

⚠️ Output **only** valid JSON of the form:

{{
  "table": [
     {{"rank": 1, "id": "DRAFT_X", "clarity": 9, "tone": 8, "faithfulness": 9, "overall": 9}},
     …
  ],
  "analysis": "…",
  "feedback": {{
     "DRAFT_Y": "…",
     "DRAFT_Z": "…"
  }}
}}

Below are the drafts, separated by markers:

{drafts_text}"""

    # Log the prompts to file
    log_dir = ROOT / "logs" / "prompts"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Log critic A prompt
    with open(log_dir / f"critic_A_ranking_{chapter_id}_{timestamp}.txt", "w", encoding="utf-8") as f:
        f.write(f"System: {critic_a_system}\n\nUser: {ranking_rubric}")
    
    # Log critic B prompt
    with open(log_dir / f"critic_B_ranking_{chapter_id}_{timestamp}.txt", "w", encoding="utf-8") as f:
        f.write(f"System: {critic_b_system}\n\nUser: {ranking_rubric}")
    
    log.info(f"Logged ranking prompts to {log_dir}")

    # Call the first critic for rankings
    try:
        res_a = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": critic_a_system},
                {"role": "user", "content": ranking_rubric}
            ],
            response_format={"type": "json_object"}  # Ensure JSON response
        )
        result_a = res_a.choices[0].message.content.strip()
        ranking_data_a = json.loads(result_a)
        
        # Call the second critic for rankings
        res_b = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": critic_b_system},
                {"role": "user", "content": ranking_rubric}
            ],
            response_format={"type": "json_object"}  # Ensure JSON response
        )
        result_b = res_b.choices[0].message.content.strip()
        ranking_data_b = json.loads(result_b)
        
        # Now get a discussion between the critics
        discussion_prompt = f"""Here are two critics' evaluations of {len(versions)} prose drafts.

CRITIC A (Technical & Clarity):
{result_a}

CRITIC B (Creative & Atmosphere):
{result_b}

Please create a discussion between Critic A and Critic B where they debate the merits of each draft. 
The discussion should include:

1. Each critic briefly defending their top pick and explaining their scoring
2. A back-and-forth discussion about the strengths and weaknesses of the drafts
3. An eventual consensus on the final ranking

End with a clear recommendation on which draft is best overall and why.

The response should read like a realistic conversation between two literary critics.
"""

        # Log discussion prompt
        with open(log_dir / f"critics_discussion_{chapter_id}_{timestamp}.txt", "w", encoding="utf-8") as f:
            f.write(f"System: You are facilitating a discussion between two literary critics.\n\nUser: {discussion_prompt}")
        
        discussion_res = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are facilitating a discussion between two literary critics."},
                {"role": "user", "content": discussion_prompt}
            ]
        )
        discussion_text = discussion_res.choices[0].message.content.strip()
        
        # Combine the results and discussion
        final_result = {
            "chapter_id": chapter_id,
            "versions": [v[0] for v in versions],
            "critic_A_rankings": ranking_data_a,
            "critic_B_rankings": ranking_data_b,
            "discussion": discussion_text,
            # Use the first critic's rankings as the "official" ones
            "table": ranking_data_a.get("table", []),
            "analysis": ranking_data_a.get("analysis", ""),
            "feedback": ranking_data_a.get("feedback", {})
        }
        
        return final_result
        
    except Exception as e:
        log.error(f"LLM call failed for chapter {chapter_id}: {e}")
        return {
            "chapter_id": chapter_id,
            "versions": [v[0] for v in versions],
            "error": f"LLM ranking failed: {e}"
        }

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
        .discussion {
            background-color: #fff9db;
            border-left: 4px solid #ffd43b;
            padding: 15px;
            border-radius: 5px;
            white-space: pre-wrap;
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
            
            # Extract the persona name from DRAFT_persona format
            persona = draft_id.replace("DRAFT_", "") if draft_id.startswith("DRAFT_") else draft_id
            
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
        
        table_html += f"""
                            {analysis}
                        </div>
                        
                        <h4>Feedback for Other Versions</h4>
                        <div class="feedback-block">
"""
        
        # Build feedback HTML
        for draft_id, fb_text in feedback.items():
            # Extract persona name
            persona = draft_id.replace("DRAFT_", "") if draft_id.startswith("DRAFT_") else draft_id
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
                persona = draft_id.replace("DRAFT_", "") if draft_id.startswith("DRAFT_") else draft_id
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
                persona = draft_id.replace("DRAFT_", "") if draft_id.startswith("DRAFT_") else draft_id
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
            
            table_html += """
                    <div class="tab-pane fade" id="discussion" role="tabpanel" aria-labelledby="discussion-tab">
                        <h4>Critics' Discussion</h4>
                        <div class="discussion">
                        """ + discussion.replace("\n", "<br>") + """
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
        
    log.info(f"Found {len(chapters_map)} chapters with multiple versions")
    
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
                ranking = rank_chapter_versions(chapter_id, versions)
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