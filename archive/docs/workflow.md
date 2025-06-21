# Prose-Forge Writing Pipeline (v0.2)

Last updated: 2025-05-02

---

## Folder Layout

```text
config/
└─ voice_specs/            # persona markdown files
data/
├─ raw/chapters/           # crawler JSON or plain-text originals
├─ segments/               # paragraph slices (ignored by Git)
└─ context/                # cleaned whole-chapter plaintext
drafts/
└─ lotm_0001/author_v1.txt # writer outputs
outputs/
└─ lotm_0001_master.txt    # locked final chapters
notes/
└─ lotm_0006_round1.json   # critic / auditor change-lists
scripts/
    segment_chapters.py
    writer.py
    critic.py              (WIP)
    auditor.py             (WIP)
    audition.py
logs/
└─ 2025-05-02T14-21-writer.log

## Command Cheat Sheet

# split crawler mega-JSON
python scripts/bin/segment_chapters.py data/raw/full.json --slug lotm

# audition all personae on chapters 1-3
python scripts/audition.py

# audition just cosmic blend
python scripts/audition.py --persona cosmic_clarity

# first production draft of chapter 6
python scripts/writer.py lotm_0006         # uses default voice_spec.md

# revision after critic notes
python scripts/writer.py lotm_0006 \
        --revise notes/lotm_0006_round1.json
