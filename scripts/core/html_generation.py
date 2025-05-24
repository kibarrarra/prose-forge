"""
html_generation.py - HTML report generation for comparison results

This module handles:
- Converting comparison results to HTML format
- Generating ranking reports with interactive elements
- Formatting critic discussions and analyses
"""

import json
import re
from typing import Dict, List, Any
from datetime import datetime

def generate_html_output(result: Dict[str, Any]) -> str:
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
        
        # Build ranking table using the main table
        table_html = """
                <ul class="nav nav-tabs" id="resultTabs" role="tablist">
                    <li class="nav-item" role="presentation">
                        <button class="nav-link active" id="consensus-tab" data-bs-toggle="tab" 
                                data-bs-target="#consensus" type="button" role="tab" 
                                aria-controls="consensus" aria-selected="true">Consensus Rankings</button>
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
                                    <th>Plot Fidelity</th>
                                    <th>Tone Fidelity</th>
                                    <th>Overall</th>
                                    <th>Total</th>"""
        
        # Add extra columns for smart ranking
        if ranking.get("method") == "smart_ranking":
            table_html += """
                                    <th>Elo Rating</th>
                                    <th>Avg Initial Rank</th>"""
        
        table_html += """
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
            
            # Get scores - handle both new format (plot_fidelity, tone_fidelity) and old format (faithfulness)
            clarity = entry.get("clarity", 0)
            tone = entry.get("tone", 0)
            
            # Handle backward compatibility with old "faithfulness" field
            plot_fidelity = entry.get("plot_fidelity", 0)
            tone_fidelity = entry.get("tone_fidelity", 0)
            if plot_fidelity == 0 and tone_fidelity == 0 and "faithfulness" in entry:
                # Use old faithfulness score for both if new fields are not present
                plot_fidelity = entry.get("faithfulness", 0)
                tone_fidelity = entry.get("faithfulness", 0)
            
            overall = entry.get("overall", 0)
            total = clarity + tone + plot_fidelity + tone_fidelity + overall
            
            # Determine badge class
            badge_class = f"badge-{rank}" if rank <= 3 else "badge-other"
            
            # Add table row
            table_html += f"""
                                <tr class="{'rank-1' if rank == 1 else ''}">
                                    <td style="padding-left: 30px;"><span class="rank-badge {badge_class}">{rank}</span></td>
                                    <td>{persona}</td>
                                    <td class="score-cell">{clarity}</td>
                                    <td class="score-cell">{tone}</td>
                                    <td class="score-cell">{plot_fidelity}</td>
                                    <td class="score-cell">{tone_fidelity}</td>
                                    <td class="score-cell">{overall}</td>
                                    <td class="score-cell">{total}</td>"""
            
            # Add extra columns for smart ranking
            if ranking.get("method") == "smart_ranking":
                elo_rating = entry.get("elo_rating", "N/A")
                avg_initial_rank = entry.get("avg_initial_rank", "N/A")
                if isinstance(avg_initial_rank, float):
                    avg_initial_rank = f"{avg_initial_rank:.1f}"
                    
                table_html += f"""
                                    <td class="score-cell">{elo_rating}</td>
                                    <td class="score-cell">{avg_initial_rank}</td>"""
            
            table_html += """
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
"""
        
        # Add Initial Rankings section for smart ranking method
        if ranking.get("method") == "smart_ranking" and "initial_avg_ranks" in ranking:
            initial_avg_ranks = ranking.get("initial_avg_ranks", {})
            initial_runs = ranking.get("initial_runs", 3)
            
            table_html += f"""
                        <h4>Initial Average Rankings</h4>
                        <div class="feedback-block">
                            <p class="text-muted mb-3">
                                These are the average rankings from {initial_runs} initial evaluation runs across all {len(initial_avg_ranks)} versions analyzed. 
                                The top candidates were then selected for focused pairwise comparisons.
                            </p>
                            <table class="table table-sm table-striped">
                                <thead>
                                    <tr>
                                        <th>Version</th>
                                        <th>Average Initial Rank</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
"""
            
            # Sort by average rank (best to worst)
            sorted_initial_ranks = sorted(initial_avg_ranks.items(), key=lambda x: x[1])
            
            # Get the list of versions that made it to final ranking (from the main table)
            final_versions = {entry.get("persona", "") for entry in table_entries}
            
            for persona, avg_rank in sorted_initial_ranks:
                status = "Advanced to pairwise" if persona in final_versions else "Eliminated in initial screening"
                status_class = "text-success" if persona in final_versions else "text-muted"
                
                table_html += f"""
                                    <tr>
                                        <td>{persona}</td>
                                        <td class="text-center">{avg_rank:.1f}</td>
                                        <td class="{status_class}"><em>{status}</em></td>
                                    </tr>
"""
            
            table_html += """
                                </tbody>
                            </table>
                        </div>
"""
        
        table_html += """
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