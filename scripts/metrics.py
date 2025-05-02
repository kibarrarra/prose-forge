#!/usr/bin/env python
"""
Compute ROUGE-L, sacreBLEU, and embedding similarity for rewritten chapters.
Usage: python scripts/metrics.py lotm_0001
"""
import pathlib, sys, openai, textwrap
from rouge_score import rouge_scorer
import sacrebleu
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np, os, json, tqdm

def embed(txt: str) -> np.ndarray:
    r = openai.Embedding.create(model="text-embedding-3-small",
                                input=txt[:8000])  # truncate safety
    return np.array(r["data"][0]["embedding"], dtype=np.float32)

def main(chap_id: str):
    raw  = pathlib.Path(f"data/context/{chap_id}.txt").read_text()
    rew  = pathlib.Path(f"rewrite/{chap_id}_v0.txt").read_text()

    scorer = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=True)
    rouge  = scorer.score(raw, rew)['rougeL'].fmeasure

    bleu   = sacrebleu.corpus_bleu([rew], [[raw]]).score / 100  # 0-1 scale

    v1, v2 = embed(raw), embed(rew)
    style  = float(cosine_similarity(v1.reshape(1,-1), v2.reshape(1,-1))[0][0])

    out = {"chapter": chap_id, "rougeL": round(rouge,3),
           "bleu": round(bleu,3), "style_sim": round(style,3)}

    pathlib.Path("reports").mkdir(exist_ok=True)
    (pathlib.Path("reports")/f"{chap_id}_metrics.json").write_text(
        json.dumps(out, indent=2))
    print(textwrap.dedent(f"""
        ROUGE-L  : {out['rougeL']}
        BLEU     : {out['bleu']}
        StyleSim : {out['style_sim']}
    """))

if __name__ == "__main__":
    openai.api_key = os.getenv("OPENAI_API_KEY")
    main(sys.argv[1])
