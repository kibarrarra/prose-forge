# ProseForge

Machine‑assisted pipeline for upgrading raw web‑novel chapters to polished English prose.

---

## 1  Quick Start

```bash
# clone and enter
git clone git@github.com:<you>/prose-forge.git
cd prose-forge

# create env
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1

# install project deps
pip install -e .

# install crawler (raw‑text puller)
pip install lightnovel-crawler
```

---

## 2  Fetching raw text (LOTM example)

LOTM spans 1,432 chapters. We download in **20‑chapter slices** to keep files manageable. `lncrawl` can’t auto‑slice by N chapters, so we drive it with a PowerShell loop that uses the `--range` flag.

```powershell
# run inside the activated venv at repo root
 lncrawl `
∙   -s "https://novelfull.com/lord-of-the-mysteries.html" `
∙   -o ".\data\raw\lotm"

# select JSON and EPUB (for legibility)
```

---

## 3  Segmenting text

Convert each raw chunk into paragraph‑level segments with stable IDs:

```powershell
Get-ChildItem data/raw/lotm/*.txt | ForEach-Object {
    python scripts/segment.py $_ --out lotm/segments --mode para
}
```

This produces files like `lotm_0001-0020_p001.txt` in `lotm/segments/`.

---

## 4  Rewriting (to‑do)

Next script `scripts/rewrite.py` will:

1. Read every segment file.
2. Call OpenAI with a style prompt.
3. Cache the rewritten passages to `lotm/rewritten/`.

*Coming soon…*

---

## 5  Data layout

```
prose-forge/
├── data/
│   └── raw/lotm/*.txt          # raw source chunks
├── lotm/
│   ├── segments/*.txt          # paragraph segments
│   └── rewritten/*.md          # polished prose (to‑do)
└── scripts/                    # helper CLI tools
```

---

## 6  License

MIT for code. No redistribution of full novel text.

