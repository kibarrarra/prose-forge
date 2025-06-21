"""
Pick the best of N drafts via 3 lightweight judges.
"""
import openai, pathlib, statistics, json, sys, os

client = openai.OpenAI()

JUDGES = [
    ("flow",      "Rate 1-10: narrative flow and pacing."),
    ("fidelity",  "Rate 1-10: factual fidelity to original plot."),
    ("voice",     "Rate 1-10: engaging prose and consistent voice.")
]

def ask_judge(prompt, temp=0):
    r = client.chat.completions.create(model="gpt-4.1-mini",
            messages=[{"role":"system","content":"Return ONLY a number 1-10."},
                      {"role":"user","content":prompt}],
            temperature=temp, max_tokens=5)
    return int(r.choices[0].message.content.strip())

def main(chap_id):
    draft_dir = pathlib.Path("drafts")/chap_id
    drafts    = list(draft_dir.glob("*.txt"))
    scores    = {d.name: [] for d in drafts}

    for role, rubric in JUDGES:
        for d in drafts:
            prompt = f"{rubric}\n\n---\n{d.read_text()}\n---"
            scores[d.name].append(ask_judge(prompt))

    # average & pick max
    avg = {k: statistics.mean(v) for k,v in scores.items()}
    winner = max(avg, key=avg.get)
    pathlib.Path("selected").mkdir(exist_ok=True)
    sel_path = pathlib.Path("selected")/f"{chap_id}.txt"
    sel_path.write_text(pathlib.Path(winner).read_text(), encoding="utf-8")
    print("winner:", winner, "score:", avg[winner])

if __name__ == "__main__":
    main(sys.argv[1])        # chap_id e.g. lotm_0001
