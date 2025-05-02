#!/usr/bin/env python
import subprocess, pathlib, sys

chap_json = pathlib.Path("data/raw/chapters/lotm_0001.json")
chap_id   = chap_json.stem            # lotm_0001

subprocess.run(["python","scripts/segment.py",
                "--in", chap_json,
                "--split-per-chapter",
                "--chapters-out", "data/raw/chapters",
                "--out", "data/segments"], check=True)

subprocess.run(["python","scripts/diverge.py", chap_json], check=True)
subprocess.run(["python","scripts/pipeline_select.py",  chap_id], check=True)
subprocess.run(["python","scripts/polish.py",  chap_id], check=True)

print("POC-1 complete — see rewrite/{chap_id}_v0.txt")
