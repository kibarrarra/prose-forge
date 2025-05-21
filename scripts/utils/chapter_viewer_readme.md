# Chapter Comparison Viewer

A simple tool to compare multiple text files side by side in an HTML viewer with independent scrolling.

## Features

- Display 1-3 chapter files side by side
- Each chapter panel is independently scrollable
- Chapter titles are shown at the top of each panel
- Automatically opens the generated HTML in your default browser

## Usage

```bash
python chapter_viewer.py file1.txt file2.txt [file3.txt] [--output output.html]
```

### Arguments

- `files`: 1-3 text files to compare
- `--output` or `-o`: (Optional) Path for the output HTML file (default: chapter_comparison.html)

### Examples

Compare two chapters:
```bash
python chapter_viewer.py chapter1.txt chapter2.txt
```

Compare three chapters:
```bash
python chapter_viewer.py chapter1.txt chapter2.txt chapter3.txt
```

Specify an output file:
```bash
python chapter_viewer.py chapter1.txt chapter2.txt --output my_comparison.html
```

## Notes

- The viewer works best with plain text files
- For optimal viewing, limit to 3 files maximum
- The generated HTML file can be opened in any modern web browser 