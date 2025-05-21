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
    args = ap.parse_args()
    
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