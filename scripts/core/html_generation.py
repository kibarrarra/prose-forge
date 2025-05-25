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
        .critic-speaker-a {
            background-color: #e7f5ff;
            border-left: 4px solid #74c0fc;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .critic-speaker-b {
            background-color: #f8f9fa;
            border-left: 4px solid #adb5bd;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .consensus-section {
            background-color: #fff9db;
            border-left: 4px solid #ffd43b;
            padding: 15px;
            margin: 15px 0;
            border-radius: 5px;
            font-weight: 500;
        }
        .evaluation-scores {
            background-color: #f1f3f4;
            padding: 10px;
            border-radius: 3px;
            font-family: monospace;
            margin: 5px 0;
        }
        .key-decision {
            background-color: #e8f5e8;
            border-left: 3px solid #28a745;
            padding: 10px;
            margin: 10px 0;
            border-radius: 3px;
        }
        .json-reference {
            color: #6c757d;
            font-style: italic;
        }
        .raw-discussion {
            display: none;
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-top: 20px;
            white-space: pre-wrap;
            font-family: monospace;
            font-size: 0.9em;
        }
        .discussion-toggle {
            cursor: pointer;
            text-decoration: underline;
            color: #0d6efd;
            font-size: 0.9em;
            margin-top: 15px;
            display: inline-block;
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
        
        function toggleRawDiscussion(chapterId) {
            const rawElem = document.getElementById('raw-discussion-' + chapterId);
            if (rawElem.style.display === 'none' || rawElem.style.display === '') {
                rawElem.style.display = 'block';
            } else {
                rawElem.style.display = 'none';
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
                                    <th>Avg Initial Rank</th>
                                    <th>Score Consistency</th>"""
        
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
                
                # Format score consistency information
                score_consistency = entry.get("score_consistency", {})
                if isinstance(score_consistency, dict) and score_consistency:
                    # Count consistency levels
                    high_count = sum(1 for v in score_consistency.values() if v == "High")
                    medium_count = sum(1 for v in score_consistency.values() if v == "Medium")
                    low_count = sum(1 for v in score_consistency.values() if v == "Low")
                    total_metrics = len(score_consistency)
                    
                    if high_count == total_metrics:
                        consistency_summary = "High"
                    elif high_count >= total_metrics // 2:
                        consistency_summary = f"Mostly High ({high_count}/{total_metrics})"
                    elif medium_count >= total_metrics // 2:
                        consistency_summary = f"Mostly Medium ({medium_count}/{total_metrics})"
                    else:
                        consistency_summary = f"Mixed (H:{high_count} M:{medium_count} L:{low_count})"
                else:
                    consistency_summary = "N/A"
                    
                table_html += f"""
                                    <td class="score-cell">{elo_rating}</td>
                                    <td class="score-cell">{avg_initial_rank}</td>
                                    <td class="score-cell">{consistency_summary}</td>"""
            
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
            
            # Check for ties in initial rankings
            tie_groups = []
            sorted_ranks = sorted(initial_avg_ranks.items(), key=lambda x: x[1])
            current_tie_group = []
            current_rank = None
            
            for persona, rank in sorted_ranks:
                if current_rank is None or abs(rank - current_rank) < 0.01:
                    current_tie_group.append((persona, rank))
                    current_rank = rank
                else:
                    if len(current_tie_group) > 1:
                        tie_groups.append(current_tie_group)
                    current_tie_group = [(persona, rank)]
                    current_rank = rank
            
            if len(current_tie_group) > 1:
                tie_groups.append(current_tie_group)
            
            table_html += f"""
                        <h4>Initial Average Rankings</h4>
                        <div class="feedback-block">
                            <p class="text-muted mb-3">
                                These are the average rankings from {initial_runs} initial evaluation runs across all {len(initial_avg_ranks)} versions analyzed. 
                                The top candidates were then selected for focused pairwise comparisons.
                            </p>"""
            
            # Add tie warning if ties detected
            if tie_groups:
                table_html += f"""
                            <div class="alert alert-warning" style="margin-bottom: 15px;">
                                <strong>⚠️ Ties Detected:</strong> {len(tie_groups)} group(s) of versions had identical average initial rankings. 
                                This suggests these versions may be very similar in quality, making pairwise comparisons especially important.
                            </div>"""
            
            table_html += """
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
                
                # Check if this persona is in a tie
                in_tie = any(persona in [p for p, _ in group] for group in tie_groups)
                tie_indicator = " [TIE]" if in_tie else ""
                
                table_html += f"""
                                    <tr>
                                        <td>{persona}{tie_indicator}</td>
                                        <td class="text-center">{avg_rank:.1f}</td>
                                        <td class="{status_class}"><em>{status}</em></td>
                                    </tr>
"""
            
            table_html += """
                                </tbody>
                            </table>"""
            
            # Add detailed tie analysis if ties found
            if tie_groups:
                table_html += """
                        <h5>Tie Analysis</h5>
                        <div class="feedback-block">
                            <p class="text-muted">
                                When versions have identical average rankings, it indicates they received very similar scores 
                                across multiple evaluation runs. This is why the smart ranking method uses pairwise comparisons 
                                to break ties among top candidates.
                            </p>"""
                
                for i, group in enumerate(tie_groups, 1):
                    personas = [p for p, _ in group]
                    avg_rank = group[0][1]
                    table_html += f"""
                            <div style="margin-bottom: 10px;">
                                <strong>Tie Group {i}:</strong> {', '.join(personas)} (all ranked {avg_rank:.1f})
                            </div>"""
                
                table_html += """
                        </div>"""
            
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
            
            # Use enhanced formatting for the discussion
            # Temporarily bypass enhancement and use basic formatting directly
            discussion_text = discussion.replace("\n\n", "</p><p>").replace("\n", "<br>")
            discussion_text = re.sub(r'```json.*?```', '<em class="json-reference">[Structured rankings available in consensus tab]</em>', discussion_text, flags=re.DOTALL)
            table_html += f"                        <div class='basic-discussion'><p>{discussion_text}</p></div>\n"
            
            table_html += f"""
                        </div>
                        <div class="discussion-toggle" onclick="toggleRawDiscussion('{chapter_id}')">Show Raw Discussion Text</div>
                        <div class="raw-discussion" id="raw-discussion-{chapter_id}">
                            {discussion}
                        </div>
                    </div>
"""
        else:
            print(f"DEBUG: No discussion found for {chapter_id}, keys: {list(ranking.keys())}")
        
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

def enhance_critics_discussion(raw_discussion: str, chapter_id: str = "") -> str:
    """
    Use an LLM to parse and enhance the formatting of critics discussion for HTML display.
    
    Args:
        raw_discussion: The raw discussion text from the ranking JSON
        chapter_id: Chapter identifier for context
        
    Returns:
        Enhanced HTML-formatted discussion
    """
    try:
        # Import here to avoid circular dependencies
        try:
            from utils.llm_client import get_llm_client
        except ImportError:
            # Handle cases where utils module isn't available in the current path
            import sys
            import os
            # Add the root directory to the path
            current_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(os.path.dirname(current_dir))
            if root_dir not in sys.path:
                sys.path.insert(0, root_dir)
            from utils.llm_client import get_llm_client
        
        # Check if discussion is substantial enough to warrant enhancement
        if not raw_discussion or len(raw_discussion.strip()) < 100:
            return f"<p class='text-muted'>Limited discussion available for {chapter_id}</p>"
        
        # If discussion is very long, truncate it for enhancement to avoid token limits
        max_chars = 8000  # Conservative limit to avoid LLM token issues
        is_truncated = len(raw_discussion) > max_chars
        discussion_to_enhance = raw_discussion[:max_chars] if is_truncated else raw_discussion
        
        client = get_llm_client()
        
        enhancement_prompt = """You are a formatting assistant that converts critic discussion text into clean, structured HTML.

Your task:
1. Parse the given critic discussion text
2. Identify different speakers (Critic A, Critic B, consensus sections, etc.)
3. Format it as clean HTML with appropriate styling classes
4. Preserve all content but make it more readable
5. Highlight key decisions and rankings

Use these HTML classes:
- critic-speaker-a: For Critic A sections
- critic-speaker-b: For Critic B sections  
- consensus-section: For final consensus/summary sections
- evaluation-scores: For numeric score sections
- key-decision: For important ranking decisions

Rules:
- Preserve all original content and meaning
- Use <div>, <p>, <strong>, <em> as needed
- Don't add content not in the original
- If there are JSON blocks, replace them with: <em class="json-reference">[Structured rankings available in consensus tab]</em>
- Use line breaks appropriately
- Keep it concise but clear
- IMPORTANT: End tags properly - ensure all <div> tags are closed

Format as clean HTML only (no markdown, no ```html blocks)."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use the same model as critics
            messages=[
                {"role": "system", "content": enhancement_prompt},
                {"role": "user", "content": f"Format this critic discussion for HTML display:\n\n{discussion_to_enhance}"}
            ],
            max_tokens=3000,  # Generous but not excessive
            temperature=0.1  # Low temperature for consistent formatting
        )
        
        enhanced_html = response.choices[0].message.content.strip()
        
        # Clean up any markdown artifacts that might have slipped through
        enhanced_html = re.sub(r'```.*?```', '<em class="json-reference">[Structured rankings available in consensus tab]</em>', enhanced_html, flags=re.DOTALL)
        enhanced_html = re.sub(r'```', '', enhanced_html)
        
        # Basic validation - check if HTML is properly formed
        open_divs = enhanced_html.count('<div')
        close_divs = enhanced_html.count('</div>')
        
        # If we have unclosed divs, try to fix them
        if open_divs > close_divs:
            # Add missing closing divs
            for _ in range(open_divs - close_divs):
                enhanced_html += '</div>'
        
        # If the LLM response was truncated or malformed, fall back to simple formatting
        if not enhanced_html or len(enhanced_html.strip()) < 50:
            raise ValueError("Enhanced discussion too short or empty")
        
        # Add truncation notice if original was truncated
        if is_truncated:
            enhanced_html += """
            <div class="alert alert-info mt-3">
                <small><em>Note: Discussion was truncated for formatting. See raw discussion below for complete content.</em></small>
            </div>"""
        
        return enhanced_html
        
    except Exception as e:
        print(f"DEBUG: Enhancement failed, using fallback: {e}")
        # Fallback to basic formatting if enhancement fails
        # IMPORTANT: Make sure we actually include the content!
        fallback_html = raw_discussion.replace("\n\n", "</p><p>").replace("\n", "<br>")
        fallback_html = f"<p>{fallback_html}</p>"
        fallback_html = re.sub(r'```json.*?```', '<em class="json-reference">[Structured rankings available in consensus tab]</em>', fallback_html, flags=re.DOTALL)
        
        # Add a note about the formatting failure
        fallback_html = f"""<div class="alert alert-warning">
            <small>Note: Enhanced formatting unavailable ({str(e)}). Showing basic formatting.</small>
        </div>
        {fallback_html}"""
        
        return fallback_html