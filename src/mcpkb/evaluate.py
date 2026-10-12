import json
from pathlib import Path

from .docs import DocIndex


def evaluate(index: DocIndex, questions_path: Path, min_score: float, k: int = 3) -> dict:
    questions = json.loads(questions_path.read_text())
    groups: dict[str, dict] = {}
    misses = []
    for q in questions:
        hits = index.search(q["question"], k=k, min_score=min_score)
        g = groups.setdefault(q["kind"], {"n": 0, "hit1": 0, "hitk": 0, "rr": 0.0, "empty": 0})
        g["n"] += 1
        if not hits:
            g["empty"] += 1
        if q["doc"] is None:
            continue
        ranks = [i for i, h in enumerate(hits, 1) if h.doc == q["doc"] and h.section == q["section"]]
        if ranks:
            g["hitk"] += 1
            g["rr"] += 1 / ranks[0]
            g["hit1"] += ranks[0] == 1
        if not ranks or ranks[0] > 1:
            top = f"{hits[0].doc} / {hits[0].section}" if hits else "nothing"
            misses.append({"id": q["id"], "question": q["question"], "expected": q["section"], "got": top})
    report = {}
    for kind, g in groups.items():
        if kind == "unanswerable":
            report[kind] = {"n": g["n"], "correctly_empty": round(g["empty"] / g["n"], 3)}
        else:
            report[kind] = {
                "n": g["n"],
                "hit@1": round(g["hit1"] / g["n"], 3),
                f"hit@{k}": round(g["hitk"] / g["n"], 3),
                "mrr": round(g["rr"] / g["n"], 3),
                "wrongly_empty": g["empty"],
            }
    return {"min_score": min_score, "k": k, "groups": report, "misses": misses}
