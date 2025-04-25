#!/usr/bin/env python
"""
split_full.py  –  split lotm_full.json into per-chapter JSON *and*
                  (optionally) per-chapter plaintext + segments.

Run once:

    python scripts/split_full.py \
        --in  data/raw/lotm/lotm_full.json \
        --chapters-out  data/raw/chapters \
        --segments-out  data/segments      # optional

If you pass --segments-out it will auto-call your existing segment.py on
each fresh chapter file.
"""
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys

# import trusted helpers from segment.py
from segment import strip_html, normalise, _PREFERRED, load_text

from ftfy import fix_text

def extract_plain(ch_dict: dict) -> str | None:
    for k in _PREFERRED:
        if k in ch_dict and isinstance(ch_dict[k], str):
            return normalise(fix_text(strip_html(ch_dict[k])))
    # fallback
    for v in ch_dict.values():
        if isinstance(v, str) and len(v) > 20:
            return normalise(fix_text(strip_html(v)))
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", required=True, dest="src",
                    type=pathlib.Path,
                    help="Path to lotm_full.json (or any mega-JSON)")
    ap.add_argument("--chapters-out", "-c", default="data/raw/chapters",
                    dest="chapters_out",
                    help="Directory for per-chapter JSON files")
    ap.add_argument("--segments-out", "-s", default=None,
                    dest="segments_out",
                    help="If set, auto-run segment.py per chapter")
    args = ap.parse_args()

    src_path      = args.src.expanduser()
    chapters_dir  = pathlib.Path(args.chapters_out)
    chapters_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(src_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        sys.exit("Expected a list of chapter dicts in lotm_full.json")

    print(f"Splitting {len(data)} chapters → {chapters_dir}")

    for idx, ch in enumerate(data, start=1):
        chap_id = f"lotm_{idx:04d}"
        out_json = chapters_dir / f"{chap_id}.json"
        json.dump([ch], out_json.open("w", encoding="utf-8"), ensure_ascii=False)

        if args.segments_out:
            seg_dir = pathlib.Path(args.segments_out)
            seg_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["python", "scripts/segment.py",
                 "--in", str(out_json),
                 "--out", str(seg_dir)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            print(f"  {chap_id}: JSON + segments written")

        else:
            # write a plaintext context for convenience
            plain = extract_plain(ch) or "<EMPTY>"
            (chapters_dir / f"{chap_id}.txt").write_text(plain, encoding="utf-8")
            print(f"  {chap_id}: JSON written")

if __name__ == "__main__":
    main()
