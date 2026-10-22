"""Build the Hugging Face Space (static HTML) that shows one run interactively.

Run from the repo root, after experiment/analyse.py:
    uv run --with matplotlib python3 -I experiment/build_space.py <run_dir>
    with-secrets uv run --with huggingface_hub python3 -I experiment/build_space.py <run_dir> --push

Writes space/data.json from the run's frozen questions, raw answers, the market snapshot it used and
the late-campaign poll mean. space/index.html and space/README.md are hand-written and only read data.json.
--push uploads space/ to the Space SPACE_ID (created public with sdk=static if missing).
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I drops the script dir from sys.path
from analyse import (KALSHI_LADDER, KALSHI_SEAT_NAMES, MARKET_MIRRORS, MODELS, POLL_SINCE, ladder_median,
                     load_answers, market_price, markets, poll_means)  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPACE = ROOT / "space"
SPACE_ID = "danielrosehill/Israel-Election-2026-Forecast"


def options(q):
    if q["type"] == "noul":
        return {"yes": "Yes", "no": "No"}
    if q["type"] == "score":
        return {str(i): c for i, c in enumerate(q["criteria"])}
    return q["criteria"]


def dist(q, a):
    if q["type"] == "noul":
        return {"yes": a["noul"], "no": 1 - a["noul"]}
    return {k: round(v, 4) for k, v in a["probabilities"].items()}


def main(run, push):
    bank = json.loads((run / "questions.json").read_text())
    ans = load_answers(run)
    rows = markets(run)
    means, n_polls = poll_means()

    mkt = {}  # question id -> {option: price}
    for qid, opt, prefix, outcome in MARKET_MIRRORS:
        p = market_price(rows, prefix, outcome)
        if p is not None:
            mkt.setdefault(qid, {})[opt or "yes"] = p
    for name, outcome in KALSHI_SEAT_NAMES.items():
        p = market_price(rows, "KXISRAELANYSEAT", outcome)
        qid = next((k for k, q in bank["questions"].items()
                    if k.startswith("passes_") and q["instructions"].startswith(f"Will {name} pass")), None)
        if p is not None and qid:
            mkt.setdefault(qid, {})["yes"] = p

    questions = []
    for qid, q in bank["questions"].items():
        seat_list = q["instructions"].removeprefix("How many seats will ").removesuffix(" win?") \
            if q["group"] == "seats" else None
        questions.append({
            "id": qid, "group": q["group"], "type": q["type"], "text": q["instructions"],
            "resolution": q["resolution"], "options": options(q),
            "answers": {f"{m}|{c}": dist(q, a[qid]) for (m, c), a in sorted(ans.items())},
            "market": mkt.get(qid),
            "poll_mean": round(means[seat_list], 2) if seat_list in means else None,
            "market_median": round(ladder_median(rows, KALSHI_LADDER[seat_list]), 1)
            if seat_list in KALSHI_LADDER and ladder_median(rows, KALSHI_LADDER[seat_list]) else None,
        })

    summary = json.loads((run / "answers" / "summary.json").read_text())
    data = {
        "run": run.name, "frozen": bank.get("frozen"), "definitions": bank["definitions"],
        "models": list(MODELS.values()), "conditions": ["no_markets", "with_markets"],
        "poll_window": {"since": POLL_SINCE, "polls": n_polls},
        "market_snapshot": rows[0]["snapshot_utc"] if rows else None,
        "cost_usd": round(sum(s["cost_usd"] for s in summary), 5),
        "requests": [{"model": MODELS[s["model"]], "condition": s["condition"], "provider": s["provider"],
                      "input_tokens": s["usage"]["input_tokens"], "cost_usd": s["cost_usd"]} for s in summary],
        "consistency": list(csv.DictReader(open(run / "analysis" / "consistency.csv"))),
        "questions": questions,
    }
    (SPACE / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"{len(questions)} questions -> {SPACE / 'data.json'}")

    if push:
        from huggingface_hub import HfApi
        api = HfApi()
        api.create_repo(SPACE_ID, repo_type="space", space_sdk="static", exist_ok=True)
        api.upload_folder(repo_id=SPACE_ID, repo_type="space", folder_path=SPACE,
                          commit_message=f"Update from run {run.name}")
        print(f"https://huggingface.co/spaces/{SPACE_ID}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()
    main(a.run_dir.resolve(), a.push)
