# ProseForge – Machine-Assisted Novel Polishing

ProseForge is a programmable pipeline for transforming raw web-novel chapters into polished English prose using modern LLMs.

---

## 1  Features

* End-to-end workflow from **raw scrape → segmentation → first draft → iterative critic/writer loops → final copy**.
* Pluggable **voice specifications** (markdown files) that define tone, diction, and stylistic guard-rails.
* Supports **multi-round auditions** across different personae / voice specs to find the best fit.
* Works with **Anthropic Claude 3**, **OpenAI GPT-4o**, or any chat-completion-compatible client (configure via `utils/llm_client.py`).
* Structured JSON feedback from the editor panel is round-tripped into the writer to apply mandatory and nice-to-have fixes.

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
    python scripts/segment.py $_ --out data/segments/lotm --mode para
}
```

You will get files like `lotm_0001_p001.txt`, `lotm_0001_p002.txt`, … which together equal the source chapter.

---

## 5  Writing ✍️ – First Drafts & Auditions

For a **single chapter first draft**:

```bash
python scripts/writer.py lotm_0001 \
       --spec config/voice_specs/cosmic_clarity.md \
       --persona cosmic_clarity
```

Recommended: run the **iterative audition loop** which automatically performs multiple writer ⇄ critic rounds and outputs a final version:

```bash
python scripts/audition_iterative.py cosmic_clarity 2 --rounds 2
#        ───────────────┬─── ┬───────────────
#         persona label │   │ number of chapters
#                       │   └─ feedback rounds before final pass
```

The command above will:
1. Create `drafts/auditions/cosmic_clarity/round_1` and write the first drafts (segmented mode).
2. Invoke the editor panel to generate JSON feedback.
3. Pass that feedback plus the previous draft into `writer.py` for the next round.
4. After the configured rounds, generate a *final* version in `drafts/auditions/cosmic_clarity/final`.

---

## 6  Directory Layout (key paths)

```text
prose-forge/
├── data/
│   ├── raw/                 # crawler output (JSON / EPUB / TXT)
│   └── segments/            # paragraph-level slices
├── drafts/
│   └── auditions/
│       └── <persona>/
│           ├── round_1/     # writer → critic loop dirs
│           ├── round_2/
│           └── final/
├── config/
│   └── voice_specs/*.md     # tone/voice definitions
├── scripts/                 # CLI tools (writer.py, editor_panel.py, ...)
└── utils/                   # shared helpers
```

---

## 7  Troubleshooting

* **Draft too short?** – Increase `--chunk-size` in segmented mode or tweak `estimate_max_tokens` factor in `scripts/writer.py`.
* **Windows encoding errors?** – Ensure `PYTHONIOENCODING` is set to `utf-8` (see section 2.1).
* **Model token limit reached?** – Adjust `max_tokens` calculation or switch to a model with a larger context window (Claude 3 Opus has 200 k tokens).

---

## 8  License

MIT for all code. Do **not** redistribute copyrighted novel text.

