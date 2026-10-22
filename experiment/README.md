# Experiment: decision-model forecast of the 2026 Knesset election

A panel of two decision models, `cloudflare/clef` and `typesafe/jev-1.14`, answers a fixed bank of 39 election-only questions. Both models read the same frozen evidence pack, once with prediction-market prices and once without. The forecast is recorded before polling day (27 Oct 2026) and scored with Brier scores against the certified CEC result. The market prices are scored the same way.

## Pipeline

Run every step from the repo root.

| Step | Command | Output |
|---|---|---|
| 1. Question bank | `python3 -I experiment/questions.py` | `experiment/questions.json` (v2, 39 questions, each with its resolution rule) |
| 2. Market snapshot | `uv run --with httpx python3 -I scripts/markets/snapshot.py` | `data/markets/snapshot_<ts>.csv`, `latest.csv` |
| 3. News digest | written by hand or by an agent: facts only, dated | `experiment/evidence/news.md` |
| 4. Evidence pack | `python3 -I experiment/build_pack.py experiment/runs/<ts>` (`--markets`, `--news` and `--polls-since` default to `latest.csv`, `news.md` and 2026-09-01) | `state_no_markets.md`, `state_with_markets.md`, a frozen `questions.json`, and `manifest.json` (input sha256s) |
| 5. Pilot | `with-secrets uv run --with httpx python3 -I experiment/run.py <run_dir> --pilot` | `pilot/`: one question per model, to measure tokens and cost |
| 6. Run | `with-secrets uv run --with httpx python3 -I experiment/run.py <run_dir>` | `answers/<model>__<condition>.json`, `answers/summary.json` |
| 7. Analysis | `uv run --with matplotlib python3 -I experiment/analyse.py <run_dir>` | `analysis/*.csv`, `analysis/fig_*.png`, `analysis/summary.json` |
| 8. Report | `uv run --with markdown --with weasyprint python3 -I experiment/render_report.py <run_dir>` | `report/report.pdf` (written from `report/report.md`) |
| 9. Space | `with-secrets uv run --with huggingface_hub --with matplotlib python3 -I experiment/build_space.py <run_dir> --push` | `space/data.json`, uploaded with `space/index.html` to [the HF Space](https://huggingface.co/spaces/danielrosehill/Israel-Election-2026-Forecast) (static SDK) |

## Runs

| Run | Frozen | Report | Cost |
|---|---|---|---|
| `runs/2026-10-22T1942Z` | 22 Oct 2026, 19:42 UTC | [report.pdf](runs/2026-10-22T1942Z/report/report.pdf), [report.md](runs/2026-10-22T1942Z/report/report.md), [Space](https://huggingface.co/spaces/danielrosehill/Israel-Election-2026-Forecast) | $0.0159 |

## System One API gotchas (verified 2026-10-22)

- **Clef on PrimeIntellect truncates silently.** PrimeIntellect is the cheapest provider and the router's default. It cuts the state to 16,384 tokens without an error: `usage.input_tokens` is exactly 16384 and the answers come from the prefix only. `run.py` therefore pins Clef to DeepInfra with `"provider": {"only": ["deepinfra"]}` (64k context, about $0.24/M). It also fails the run if any response is billed at a context cap (`TRUNCATION_CAPS`).
- **`score` questions take at most 10 criteria.** Jev returned HTTP 422 with "List should have at most 10 items". Clef returned only "Invalid request" for the same body. `choice` questions accepted 38 options, so the seat questions are `choice` questions keyed by seat count.
- **Answer shapes differ by type:**
  - `noul` returns `{"noul": p}`;
  - `choice` returns `{"probabilities": {key: p}}`;
  - `score` returns `{"score", "legend", "probabilities", "confidence"}`, keyed by **index** into the criteria list, not by label.
- **Billing is on input only.** One request carries every question and the state is billed once, so the 39-question run cost about the same as the 1-question pilot.

Model discovery and the endpoint shape are in the top-level `README.md`.

## Scoring (after the result)

Every question in `questions.json` carries `resolution`, `resolves_by` and `mirrors`, the market outcomes it can be compared with. The scoring script is not written yet. It will:

1. read the final CEC results;
2. resolve each question;
3. compute Brier scores per model × condition, and for the mirrored market prices from the same snapshot.

## Space notes (verified 2026-10-22)

- Plotly 2.35.2 is **not** on cdnjs (404), so `space/index.html` loads it from jsDelivr (`plotly.js-dist-min@2.35.2`).
- Charts on a hidden tab are drawn only once the tab is shown. Otherwise Plotly measures a hidden container and renders at the wrong width.
- Creating the Space with `create_repo(space_sdk="static")` adds a template `style.css`. It was deleted after the first push.
- Headless Chrome won't lay out narrower than 500px, so a 390px screenshot crops the page. Don't mistake that for a layout bug.
