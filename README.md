# ProseForge – Machine-Assisted Novel Polishing

ProseForge is a programmable pipeline for transforming raw web-novel chapters into polished English prose using modern LLMs.

---

## 1  Features

* End-to-end workflow from **raw scrape → segmentation → first draft → iterative critic/writer loops → final copy**.
* Pluggable **voice specifications** (markdown files) that define tone, diction, and stylistic guard-rails.
* Supports **multi-round experiments** across different voice specs and prompts.
* Generate cleaned plaintext context files with `scripts/export_original.py`.
* Works with **Anthropic Claude 3**, **OpenAI GPT-4o**, or any chat-completion-compatible client (configure via `utils/llm_client.py`).
* Structured JSON feedback from the editor panel is round-tripped into the writer to apply mandatory and nice-to-have fixes.
* **Experiment Runner**: Run experiments with different voice specifications, writer models, and editor configurations
* **Rich Progress Tracking**: Visual progress bars and summary tables for experiment runs
* **HTML Reports**: Detailed experiment reports with metrics and comparison suggestions
* **Multi-Version Comparison**: Compare different versions of chapters side-by-side
* **Version Ranking**: Automatically rank and evaluate all versions of chapters
* **Modular Architecture**: Refactored codebase with 60% code reduction and improved maintainability
* **External Template Support**: Compatible with custom prompt templates via environment variables
* **Production Chapter Generation**: Generate multiple chapters with a single voice spec for production use

---

## 2  Installation (Unix & Windows)

```bash
# clone and enter
git clone https://github.com/<you>/prose-forge.git
cd prose-forge

# create & activate virtual env
python -m venv .venv
#   Linux / macOS
source .venv/bin/activate
#   Windows (PowerShell)
.venv\Scripts\Activate.ps1

# install project (editable mode) + runtime deps
pip install -e .
```

### 2.1 Environment variables

| Variable           | Purpose                                   |
|--------------------|-------------------------------------------|
| `OPENAI_API_KEY`   | Key for GPT models (if using OpenAI)       |
| `ANTHROPIC_API_KEY`| Key for Claude models (default pipeline)   |
| `WRITER_MODEL`     | Override default model per run             |
| `WRITER_PROMPT_TEMPLATE` | Use external prompt template (e.g., `@baseline.prompt`) |

```powershell
# Windows UTF-8 safety (recommended)
[System.Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "User")
```

---

## 3  Fetching raw text (LOTM Example)

ProseForge is novel-agnostic; the commands below show how we grab **Lord of the Mysteries** using [`lightnovel-crawler`](https://github.com/dipu-bd/lightnovel-crawler).

```powershell
# install crawler (once)
pip install lightnovel-crawler

# fetch chapters as JSON (better structure) plus EPUB for reference
lncrawl `
  -s "https://novelfull.com/lord-of-the-mysteries.html" `
  -o "data/raw/lotm" `
  --format json,epub
```

Large novels are easier to manage in slices (e.g. 20-chapter chunks) but the crawler does not auto-slice, so you can loop over `--range` yourself.

---

## 4  Segmenting Raw Chapters

Paragraph-level segmentation gives each chunk a stable ID so later feedback can target exact passages.

```powershell
Get-ChildItem data/raw/lotm/*.json | ForEach-Object {
    python archive/segment.py $_ --out data/segments/lotm --mode para
}
```

You will get files like `lotm_0001_p001.txt`, `lotm_0001_p002.txt`, … which together equal the source chapter.

### 4.1 Exporting Clean Context

Run the helper below to create `data/context/<chapter>.txt` files used by the writer:

```bash
python scripts/export_original.py --all        # process every chapter
python scripts/export_original.py lotm_0001    # just one
```

---

## 5  Writing ✍️ – First Drafts & Experiments

For a **single chapter first draft**:

```bash
# Using built-in voice specs
python scripts/bin/writer.py lotm_0001 \
       --spec config/voice_specs/cosmic_clarity.md \
       --persona cosmic_clarity \
       --segmented-first-draft

# Using external prompt templates
WRITER_PROMPT_TEMPLATE="$(cat config/writer_specs/baseline.prompt)" \
python scripts/bin/writer.py lotm_0001 \
       --spec config/voice_specs/cosmic_clarity.md \
       --persona cosmic_clarity
```

The older `audition_iterative.py` helper that automated writer ⇄ critic loops has
been archived.  The modern workflow uses `run_experiments.py` which wraps the
writer and optional editor panel logic into a single configurable pipeline.

---

## 5.1 Running Experiments

For more structured experimentation across different voice specs, prompts, and models:

```bash
# Run all experiments defined in experiments.yaml
python scripts/bin/run_experiments.py --config experiments.yaml

# Run experiments matching a specific filter
python scripts/bin/run_experiments.py --config experiments.yaml --filter cosmic

# Compare results of two completed experiments (final outputs)
# Note: --config not needed for comparison operations
python scripts/bin/run_experiments.py --compare cosmic_clarity_standard stars_and_shadow_standard

# Compare any two draft directories (e.g., first draft vs final version)
python scripts/bin/run_experiments.py --compare-dirs "drafts/auditions/exp1/round_1" "drafts/auditions/exp1/final"
```

Experiments are defined in `experiments.yaml`:

```yaml
experiments:
  - name: cosmic_clarity_standard
    writer_spec: config/writer_specs/standard.prompt
    editor_spec: config/editor_specs/assertive.md
    voice_spec: config/voice_specs/cosmic_clarity.md
    model: claude-opus-4-20250514
    chapters:
      - lotm_0001
    rounds: 2  # With rounds > 1, editor feedback is generated and used
```

The experiment system allows you to easily compare:
- Different voice specifications (from `config/voice_specs/`)
- Different writer prompts (from `config/writer_specs/`)
- Different editor/critic prompts (from `config/editor_specs/`)
- Different LLM models (Claude, GPT-4o, etc.)

**Note on rounds parameter:**
- `rounds: 1`: Single-pass mode, writes directly to the final directory without editor feedback
- `rounds: 2`: Two-pass mode with one draft and one revision (with editor feedback)
- `rounds: 3`: Three-pass mode with one draft and two revisions (editor feedback after each round except the last)

The `rounds` parameter represents the **total number of passes** through the writer, including the final version.

Each experiment creates all necessary files in the `drafts/auditions/<experiment_name>/` directory. After running multiple experiments, you can compare their outputs with the `--compare` option, or compare specific directories (like first drafts vs finals) with `--compare-dirs`.

---

## 5.2 Production Chapter Generation

After experimenting and finding a voice spec you like, you can generate multiple chapters for production use:

```bash
# Using command line arguments with explicit chapter list
python scripts/bin/generate_chapters.py \
       --version cosmic_clarity_full \
       --voice-spec config/voice_specs/cosmic_clarity.md \
       --writer-spec config/writer_specs/baseline.prompt \
       --chapters lotm_0001 lotm_0002 lotm_0003 lotm_0004 lotm_0005 \
       --model claude-opus-4-20250514 \
       --temperature 0.7

# Using chapter ranges (much more convenient for sequential chapters)
python scripts/bin/generate_chapters.py \
       --version cosmic_clarity_full \
       --voice-spec config/voice_specs/cosmic_clarity.md \
       --writer-spec config/writer_specs/baseline.prompt \
       --range 1-20 \
       --prefix lotm \
       --model claude-opus-4-20250514

# Using count-based generation
python scripts/bin/generate_chapters.py \
       --version cosmic_clarity_full \
       --voice-spec config/voice_specs/cosmic_clarity.md \
       --writer-spec config/writer_specs/baseline.prompt \
       --count 50 \
       --start 1 \
       --prefix lotm \
       --model claude-opus-4-20250514

# Using a configuration file (recommended for larger projects)
python scripts/bin/generate_chapters.py --config chapter_generation.yaml

# Or use the run_experiments.py wrapper
python scripts/bin/run_experiments.py --generate --config chapter_generation.yaml
```

The chapter generation config file (`chapter_generation.yaml`) supports multiple ways to specify chapters:

```yaml
# Option 1: Explicit chapter list
version_name: cosmic_clarity_full
voice_spec: config/voice_specs/cosmic_clarity.md
writer_spec: config/writer_specs/baseline.prompt
model: claude-opus-4-20250514
temperature: 0.7
chapters:
  - lotm_0001
  - lotm_0002
  - lotm_0003
  - lotm_0004
  - lotm_0005

# Option 2: Chapter range (more convenient for sequential chapters)
version_name: cosmic_clarity_full
voice_spec: config/voice_specs/cosmic_clarity.md
writer_spec: config/writer_specs/baseline.prompt
model: claude-opus-4-20250514
temperature: 0.7
range: "1-20"
prefix: lotm  # optional, defaults to "lotm"

# Option 3: Count-based generation (great for entire novels)
version_name: cosmic_clarity_full_novel
voice_spec: config/voice_specs/cosmic_clarity.md
writer_spec: config/writer_specs/baseline.prompt
model: claude-opus-4-20250514
temperature: 0.7
count: 100
start: 1      # optional, defaults to 1
prefix: lotm  # optional, defaults to "lotm"
```

This creates a structured output under `drafts/[version_name]/`:

```text
drafts/cosmic_clarity_full/
├── voice_spec.md           # Copy of the voice spec used
├── generation_config.yaml  # Configuration for reproducibility
├── chapters/               # Generated chapter texts
│   ├── lotm_0001.txt
│   ├── lotm_0002.txt
│   └── ...
└── prompts/                # Prompts used for each chapter
    ├── lotm_0001_prompt.md
    ├── lotm_0002_prompt.md
    └── ...
```

**Chapter Specification Options:**
- **Explicit list**: `--chapters lotm_0001 lotm_0002 lotm_0003` or `chapters: [lotm_0001, ...]` in config
- **Range**: `--range 1-20 --prefix lotm` generates `lotm_0001` through `lotm_0020`
- **Count**: `--count 50 --start 1 --prefix lotm` generates 50 chapters starting from `lotm_0001`

**Key features:**
- **Sequential consistency**: Each chapter uses the previous chapter for context
- **Organized outputs**: All files are neatly organized by version
- **Prompt preservation**: All prompts are saved for debugging/analysis
- **Progress tracking**: Rich progress bars show generation status
- **Batch processing**: Generate entire novels or sections efficiently
- **Flexible chapter specification**: Use explicit lists, ranges, or counts

---

## 6  Architecture & Directory Layout

### 6.1 Refactored Code Structure

ProseForge has been recently refactored for improved maintainability and modularity:

```text
scripts/
├── bin/                    # CLI executables
│   ├── writer.py          # Refactored writer (61% code reduction)
│   ├── editor_panel.py
│   ├── sanity_checker.py
│   ├── run_experiments.py # Clean version using ExperimentRunner
│   ├── compare_versions.py
│   └── generate_chapters.py # Production chapter generation
├── core/                   # Business logic modules
│   ├── writing/           # Core writing functionality
│   │   ├── prompts.py     # PromptBuilder class
│   │   ├── drafting.py    # DraftWriter class
│   │   ├── revision.py    # RevisionHandler class
│   │   └── __init__.py
│   ├── experiments/       # Experiment execution
│   │   ├── runner.py      # ExperimentRunner class
│   │   └── __init__.py
│   ├── analysis/          # Text analysis (future)
│   │   └── __init__.py
│   └── __init__.py
└── utils/                 # Shared utilities
    ├── subprocess_helpers.py  # Safe subprocess execution
    ├── file_helpers.py        # File operations & validation
    ├── text_processing.py     # Text manipulation
    ├── io_helpers.py          # File I/O utilities
    ├── llm_client.py          # Unified LLM interface
    ├── logging_helper.py      # Logging setup
    ├── paths.py               # Path definitions
    └── __init__.py
```

**Key Improvements:**
- **60% code reduction** through elimination of duplication
- **Modular design** with clear separation of concerns
- **Preserved backward compatibility** - all existing functionality works
- **External template support** maintained for `@baseline.prompt` style templates
- **Better error handling** and retry logic
- **Improved testability** with dependency injection patterns

### 6.2 Project Directory Layout

```text
prose-forge/
├── data/
│   ├── raw/                 # crawler output (JSON / EPUB / TXT)
│   ├── context/             # clean plaintext context files
│   └── segments/            # paragraph-level slices
├── drafts/
│   ├── auditions/           # experiment outputs
│   │   └── <experiment_name>/
│   │       ├── round_1/     # writer → critic loop dirs
│   │       ├── round_2/
│   │       └── final/
│   └── <version_name>/      # production outputs
│       ├── voice_spec.md
│       ├── generation_config.yaml
│       ├── chapters/
│       └── prompts/
├── config/
│   ├── voice_specs/*.md     # tone/voice definitions
│   ├── writer_specs/*.prompt  # writer prompt templates with placeholders
│   └── editor_specs/*.md    # editor/critic prompt templates
├── examples/                # sample files to demonstrate usage
│   ├── raw/                 # sample chapter in JSON format
│   ├── segments/            # pre-segmented version of the sample chapter
│   └── voice_spec_example.md # example voice specification
├── archive/                 # legacy scripts and docs
├── scripts/                 # refactored CLI tools and core modules
├── utils/                   # shared helpers (legacy location)
├── experiments.yaml         # configuration for experiment runs
└── chapter_generation.yaml  # configuration for production generation
```

---

## 7  Trying the Examples

The repository includes example files to help you get started:

```bash
# Run the writer on the sample chapter with the example voice spec
python scripts/bin/writer.py examples/raw/sample_001.json \
       --spec examples/voice_spec_example.md \
       --persona example \
       --segmented-first-draft

# Or use pre-segmented files
python scripts/bin/writer.py sample_001 \
       --spec examples/voice_spec_example.md \
       --persona example \
       --segmented-first-draft
```

To create your own voice specifications, use the examples as a template. Each voice spec should define the narrative style, tone, language characteristics, and other stylistic elements.

---

## 8  Troubleshooting

* **Draft too short?** – In writer.py, use `--segmented-first-draft` for better handling of longer content.
* **Windows encoding errors?** – Ensure `PYTHONIOENCODING` is set to `utf-8` (see section 2.1).
* **Model token limit reached?** – Switch to a model with a larger context window (Claude 3 Opus has 200k tokens).
* **Experiment not running correctly?** – Check experiments.yaml format and make sure all referenced files exist.
* **Cannot find sanity checker?** – The sanity checker is only used for rounds with previous drafts and feedback.
* **Script path issues?** – Use `scripts/bin/` prefix for CLI tools after refactoring.

---

## 9  Usage Examples

### Running Experiments

```bash
# Run all experiments in the config file
python scripts/bin/run_experiments.py --config experiments.yaml

# Run experiments matching a regex pattern (supports pipe | for OR)
python scripts/bin/run_experiments.py --config experiments.yaml --filter "cosmic_clarity_baseline|cosmic_clarity_4o"

# Compare two experiments
python scripts/bin/run_experiments.py --compare exp1 exp2

# Compare specific directories
python scripts/bin/run_experiments.py --compare-dirs dir1 dir2
```

### Generating Production Chapters

```bash
# Generate multiple chapters with a single voice spec
python scripts/bin/generate_chapters.py --config chapter_generation.yaml

# Or use the run_experiments wrapper
python scripts/bin/run_experiments.py --generate --config chapter_generation.yaml

# Command line usage
python scripts/bin/generate_chapters.py \
       --version my_novel_v1 \
       --voice-spec config/voice_specs/cosmic_clarity.md \
       --writer-spec config/writer_specs/baseline.prompt \
       --chapters chapter1 chapter2 chapter3
```

### Comparing and Ranking Versions

```bash
# Compare specific versions of chapters
python scripts/bin/compare_versions.py chapter_id --versions version1 version2

# Compare final versions of experiments
python scripts/bin/compare_versions.py chapter_id --final-versions exp1 exp2

# Compare specific directories
python scripts/bin/compare_versions.py --dir1 dir1 --dir2 dir2

# Rank all final versions of all chapters
python scripts/bin/compare_versions.py --all-finals
```

### External Template Usage

```bash
# Use external prompt template
WRITER_PROMPT_TEMPLATE="$(cat config/writer_specs/baseline.prompt)" \
python scripts/bin/writer.py lotm_0001 --spec config/voice_specs/cosmic_clarity.md --persona test

# Template supports placeholders like {voice_spec}, {segments}, {persona}, etc.
```

---

## 10  Output

- Experiment results are saved in the `drafts/experiment_summaries` directory
- HTML reports provide detailed metrics and comparisons
- Version rankings show scores for clarity, tone, faithfulness, and overall quality
- Production chapters are organized under `drafts/<version_name>/` with all prompts preserved

---

## 11  License

MIT for all code. Do **not** redistribute copyrighted novel text.

