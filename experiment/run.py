"""Ask the decision-model panel the question bank, in both evidence conditions.

Run from the repo root, after experiment/build_pack.py has filled <run_dir>:
    with-secrets uv run --with httpx python3 -I experiment/run.py <run_dir> [--pilot]

For each model × condition (no_markets, with_markets), one POST to OpenRouter's
/api/v1/systemone carries the whole state and every question, so the state is
billed once per request. Writes <run_dir>/answers/<model>__<condition>.json
(the request ids, the provider, usage, cost and raw answers) and
<run_dir>/answers/summary.json.

--pilot sends a single question with the full no_markets state to each model,
which measures input tokens and cost before the full run.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

PANEL = ["typesafe/jev-1.14", "cloudflare/clef"]
CONDITIONS = ["no_markets", "with_markets"]
URL = "https://openrouter.ai/api/v1/systemone"
API_FIELDS = ("type", "instructions", "criteria")


async def ask(client, model, state, questions):
    r = await client.post(URL, json={"model": model, "state": state, "questions": questions})
    if r.status_code != 200:
        return {"model": model, "http_status": r.status_code, "error": r.text[:2000]}
    data = r.json()
    missing = sorted(set(questions) - set(data.get("answers", {})))
    return {
        "model": model, "served_by": data.get("model"), "provider": data.get("provider"),
        "generation_id": data.get("id"), "usage": data.get("usage"),
        "cost_usd": (data.get("usage") or {}).get("cost"),
        "missing_answers": missing, "answers": data.get("answers"),
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--models", default=",".join(PANEL))
    ap.add_argument("--pilot", action="store_true")
    args = ap.parse_args()

    bank = json.loads((args.run_dir / "questions.json").read_text())["questions"]
    questions = {qid: {k: q[k] for k in API_FIELDS if k in q} for qid, q in bank.items()}
    if args.pilot:
        first = next(iter(questions))
        questions = {first: questions[first]}
    conditions = ["no_markets"] if args.pilot else CONDITIONS
    out = args.run_dir / ("pilot" if args.pilot else "answers")
    out.mkdir(exist_ok=True)

    jobs = [(m, c) for m in args.models.split(",") for c in conditions]
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    async with httpx.AsyncClient(headers=headers, timeout=300) as client:
        results = await asyncio.gather(*(
            ask(client, m, (args.run_dir / f"state_{c}.md").read_text(), questions) for m, c in jobs))

    summary = []
    for (model, cond), res in zip(jobs, results):
        res["condition"] = cond
        (out / f"{model.replace('/', '__')}__{cond}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
        summary.append({k: res.get(k) for k in ("model", "condition", "provider", "usage", "cost_usd",
                                                 "missing_answers", "http_status", "error")})
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    json.dump(summary, sys.stdout, indent=2, ensure_ascii=False)
    print(f"\ntotal cost: ${sum(s.get('cost_usd') or 0 for s in summary):.5f}")


if __name__ == "__main__":
    asyncio.run(main())
