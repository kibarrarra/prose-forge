import os
import sys
import argparse
from pathlib import Path
import webbrowser


def read_file(file_path):
    """Read the content of a text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return f"Error reading file: {e}"


def generate_html(files_content, file_names):
    """Generate an HTML page with side-by-side chapter comparison."""
    num_files = len(files_content)
    
    # Calculate the width for each column
    column_width = 100 // num_files
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chapter Comparison Viewer</title>
    <style>
        body, html {{
            margin: 0;
            padding: 0;
            height: 100%;
            font-family: Arial, sans-serif;
            overflow: hidden;
        }}
        .container {{
            display: flex;
            height: 100vh;
            width: 100%;
        }}
        .chapter {{
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            border-right: 1px solid #ccc;
            height: 100%;
            box-sizing: border-box;
        }}
        .chapter:last-child {{
            border-right: none;
        }}
        h2 {{
            position: sticky;
            top: 0;
            background-color: #fff;
            padding: 10px 0;
            margin-top: 0;
            border-bottom: 1px solid #eee;
            z-index: 10;
        }}
        pre {{
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: inherit;
            line-height: 1.5;
        }}
    </style>
</head>
<body>
    <div class="container">
"""
    
    # Add each chapter
    for i, (content, name) in enumerate(zip(files_content, file_names)):
        html += f"""
        <div class="chapter" style="width: {column_width}%;">
            <h2>{name}</h2>
            <pre>{content}</pre>
        </div>"""
    
    html += """
    </div>
</body>
</html>"""
    
    return html


def save_html(html_content, output_path):
    """Save the HTML content to a file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Generate a side-by-side chapter comparison view')
    parser.add_argument('files', nargs='+', help='Text files to compare (1-3 files)')
    parser.add_argument('--output', '-o', help='Output HTML file path', default='chapter_comparison.html')
    args = parser.parse_args()
    
    if len(args.files) > 3:
        print("Warning: This viewer works best with 1-3 files. Only the first 3 files will be used.")
        args.files = args.files[:3]
    
    # Read files
    file_contents = []
    file_names = []
    
    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"Error: File {file_path} does not exist.")
            sys.exit(1)
        
        content = read_file(file_path)
        file_contents.append(content)
        file_names.append(path.name)
    
    # Generate HTML
    html_content = generate_html(file_contents, file_names)
    
    # Save HTML to file
    output_path = save_html(html_content, args.output)
    
    print(f"HTML chapter comparison saved to: {output_path}")
    
    # Open the HTML file in the default browser
    webbrowser.open('file://' + os.path.abspath(output_path))


if __name__ == "__main__":
    main()

# Example usage (from project root):
# python scripts/utils/chapter_viewer.py "drafts/addl_drafts/original/lotm_0001.txt" "drafts/auditions/cosmic_clarity_baseline/final/lotm_0001.txt" "drafts/auditions/cosmic_clarity_4o/final/lotm_0001.txt"