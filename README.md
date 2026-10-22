# Israeli-Elections-2026

This repo models the election to Israel's 26th Knesset, held on **27 October 2026**. A panel of *decision models* (typed-probability models; no LLMs) answers a bank of individual probability questions from a frozen evidence pack. The forecast is recorded before election day and scored against the result and the prediction markets afterwards.

## Datasets (Hugging Face, public)

| Dataset | Contents | Source folder |
|---|---|---|
| [Israel-Knesset-25-Members](https://huggingface.co/datasets/danielrosehill/Israel-Knesset-25-Members) | The outgoing 25th Knesset: 152 people who served, 16 factions, seats at the end of the term | `data/knesset-25/` |
| [Israel-Election-2026-Candidate-Lists](https://huggingface.co/datasets/danielrosehill/Israel-Election-2026-Candidate-Lists) | 38 CEC lists and 1,361 candidates, with list position and leader | `data/candidate-lists/` |
| [Israel-Election-2026-Polls](https://huggingface.co/datasets/danielrosehill/Israel-Election-2026-Polls) | 1,109 seat-projection polls from Dec 2022 to Oct 2026, with 15k poll × party rows | `data/polls/` |

Each folder has the CSVs, a `README.md` (the HF dataset card) and `SOURCES.md`. `SOURCES.md` lists which sources worked and which failed, what is confirmed versus inferred, and known gaps.

`data/markets/` holds timestamped snapshots of Kalshi and Polymarket prices for the election. This data is not on HF.

## Rebuilding

| What | Command |
|---|---|
| 25th Knesset | `uv run --with lxml python3 -I scripts/knesset-25/build.py --raw <dir> --fetch` |
| Candidate lists | `uv run --with pandas --with lxml python3 -I scripts/candidate-lists/build.py` |
| Polls | `uv run --with pandas --with lxml --with beautifulsoup4 python3 -I scripts/polls/build.py --refresh` |
| Market snapshot | `uv run --with httpx python3 -I scripts/markets/snapshot.py` |
| Publish to HF | `with-secrets uv run --with huggingface_hub python3 -I scripts/publish_hf.py [--private] [knesset-25 candidate-lists polls]` |

Rebuild notes:
- **Candidate lists:** the CEC list pages (gov.il) sit behind a Cloudflare challenge. The candidate-lists build therefore works from the browser captures saved in `data/candidate-lists/raw/` and checks them against browser-computed fingerprints.
- **Publishing:** existing HF repos keep their visibility. `--private` only affects repos created on that run.

## Decision models via OpenRouter

Verified 2026-10-22.
- **Finding them:** decision models are not listed by `GET /api/v1/models`. They appear only with `?output_modalities=all`, where `output_modalities` is `["decisions"]`. Hugging Face Inference Providers host none of them.
- **Calling them:** `POST https://openrouter.ai/api/v1/systemone`, using the OpenRouter key as the bearer token. The body is `{"model", "state", "questions": {id: {"type": "noul" | "choice" | "score", "instructions", "criteria"}}}`.
- **Response:** per-option probabilities in `answers`, plus `usage.cost`.
- **Billing:** input tokens only, about $0.042 per million tokens. Many questions sharing one `state` in one request cost about the same as a single question.
- **Context limits:** `cloudflare/clef` allows 16k on PrimeIntellect (the cheapest host) and 64k on DeepInfra ($0.24 per million tokens). `typesafe/jev-1.14` allows 262k.

## Experiment

The panel is `cloudflare/clef` (Cloudflare's post-train of Qwen 3.8 27B) and `typesafe/jev-1.14` (TypeSafe's closed model). Each answers the same question bank twice from the same evidence pack: once with the market prices included and once without. Questions mirror the Kalshi and Polymarket markets where possible, so every answer can be scored with a Brier score against the result and compared with the markets. Code, frozen inputs, answers and reports are in `experiment/`; see [experiment/README.md](experiment/README.md). First run (22 Oct 2026): [report](experiment/runs/2026-10-22T1942Z/report/report.pdf) · [interactive results (HF Space)](https://huggingface.co/spaces/danielrosehill/Israel-Election-2026-Forecast) · [blog post](https://blog.danielrosehill.com/posts/knesset-2026-decision-model-forecast-aijs1i).
