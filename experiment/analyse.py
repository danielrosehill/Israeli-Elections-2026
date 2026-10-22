"""Turn a run's raw answers into tables and charts (pre-election: no scoring yet).

Run from the repo root:
    uv run --with matplotlib python3 -I experiment/analyse.py <run_dir>

Writes <run_dir>/analysis/:
  answers_long.csv   model, condition, question, option, label, probability
  seats.csv          per list: poll mean, market median, and each model's expected seats per condition
  markets_vs_panel.csv  mirrored binary/choice questions next to the market price
  consistency.csv    the same quantity asked two ways, and the gap between the two answers
  summary.json       headline numbers used by the report
  fig_*.png          charts (light theme; reference palette from the dataviz skill)

Conventions:
- Expected seats are computed from the choice distribution over seat counts (key = seat count).
- "Poll mean" is the mean of standard polls released from 2026-10-08 on, i.e. the final ~2 weeks.
- "Market median" interpolates a Kalshi "Above N" ladder to the seat count where P(above) = 0.5.
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiment"))
from build_pack import POLL_TO_CEC  # noqa: E402

MODELS = {"cloudflare/clef": "Clef", "typesafe/jev-1.14": "Jev 1.14"}
CONDS = {"no_markets": "without markets", "with_markets": "with markets"}
# Reference palette (dataviz skill, references/palette.md), light mode.
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
COLOR = {"Clef": "#2a78d6", "Jev 1.14": "#eb6834"}
POLL_SINCE = "2026-10-08"
KALSHI_LADDER = {
    "Likud": "KXLIKUDCOUNT", "Yashar": "KXYASHARCOUNT", "Together (B'Yachad)": "KXTOGETHERCOUNT",
    "The Democrats": "KXISRDEMCOUNT", "Shas": "KXSHASCOUNT", "Yisrael Beiteinu": "KXBEITEINUCOUNT",
}
KALSHI_SEAT_NAMES = {  # KXISRAELANYSEAT outcome -> CEC list name
    "The Reservists and the Economic Party": "Reservists–Economic Party", "Amcha Yisrael": "People of Israel",
    "Religious Zionist Party – Zehut": "RZP-Zehut", "United Arab List (Ra'am)": "Ra'am",
    "Yisrael Beiteinu": "Yisrael Beiteinu", "Joint List": "Joint List (Hadash–Ta'al–Balad)",
    "Noam": "Noam for Israel", "Israel First": "Israel First", "Haredi Public": "Haredi Public",
}
MARKET_MIRRORS = [  # (question, option or None for noul, market event prefix, market outcome)
    ("largest_list", "yashar", "israeli-legislative-election-winner", "Yashar"),
    ("largest_list", "likud", "israeli-legislative-election-winner", "Likud"),
    ("next_pm", "eisenkot", "who-will-be-the-next-prime-minister", "Gadi Eizenkot"),
    ("next_pm", "netanyahu", "who-will-be-the-next-prime-minister", "Benjamin Netanyahu"),
    ("next_pm", "bennett", "who-will-be-the-next-prime-minister", "Naftali Bennett"),
    ("bloc_most_seats", "opposition", "KXISRAELBLOCMOST", "Opposition bloc"),
    ("no_bloc_majority", None, "israeli-election-results-in-a-hung-parliament", None),
    ("second_list", "likud", "KXISRAEL2ND", "Likud"),
    ("third_list", "together", "KXISRAEL3RD", "Together"),
]


def load_answers(run):
    out = {}
    for f in sorted((run / "answers").glob("*__*.json")):
        d = json.loads(f.read_text())
        out[(MODELS[d["model"]], d["condition"])] = d["answers"]
    return out


def prob(ans, qid, option=None):
    a = ans[qid]
    return a["noul"] if a["type"] == "noul" else a["probabilities"].get(option, 0.0)


def seat_dist(ans, qid):
    return {int(k): v for k, v in ans[qid]["probabilities"].items()}


def poll_means():
    polls = {p["poll_id"]: p for p in csv.DictReader(open(ROOT / "data/polls/polls.csv"))}
    vals, ids = defaultdict(list), set()
    for r in csv.DictReader(open(ROOT / "data/polls/poll_results.csv")):
        if r["scenario"] == "standard" and polls[r["poll_id"]]["release_date"] >= POLL_SINCE:
            ids.add(r["poll_id"])
            vals[POLL_TO_CEC.get(r["party"], r["party"])].append(int(r["seats"] or 0))
    return {k: sum(v) / len(ids) for k, v in vals.items()}, len(ids)


def markets(run):
    manifest = json.loads((run / "manifest.json").read_text())
    path = next(ROOT / p for p in manifest["inputs"] if p.startswith("data/markets/"))
    return list(csv.DictReader(open(path)))


def market_price(rows, prefix, outcome):
    for r in rows:
        if r["event_id"].startswith(prefix) and (outcome is None or r["outcome"] == outcome):
            return float(r["price"])
    return None


def ladder_median(rows, prefix):
    pts = sorted((int(r["outcome"].split()[-1]), float(r["price"])) for r in rows if r["event_id"].startswith(prefix))
    # P(X > t); find where it crosses 0.5 and interpolate linearly between thresholds.
    for (t0, p0), (t1, p1) in zip(pts, pts[1:]):
        if p0 >= 0.5 >= p1:
            return t0 + 0.5 + (t1 - t0) * (p0 - 0.5) / (p0 - p1) if p0 != p1 else t0 + 0.5
    return None


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def dot_panel(ax, labels, series, ref=None, ref_label=None, xlabel=""):
    """series: {model: {cond: [values]}}; ref: [values] drawn as grey diamonds."""
    y = list(range(len(labels)))[::-1]
    off = {"Clef": 0.14, "Jev 1.14": -0.14}
    if ref is not None:
        ax.scatter([v for v in ref if v is not None], [yy for yy, v in zip(y, ref) if v is not None],
                   marker="D", s=46, color=MUTED, zorder=3, label=ref_label, edgecolors=SURFACE, linewidths=1.5)
    for model, conds in series.items():
        c = COLOR[model]
        yy = [v + off[model] for v in y]
        a, b = conds["no_markets"], conds["with_markets"]
        for y0, v0, v1 in zip(yy, a, b):
            ax.plot([v0, v1], [y0, y0], color=c, linewidth=2, alpha=0.5, zorder=2)
        ax.scatter(a, yy, s=64, color=c, zorder=4, edgecolors=SURFACE, linewidths=1.5, label=f"{model}, {CONDS['no_markets']}")
        ax.scatter(b, yy, s=64, facecolors=SURFACE, edgecolors=c, linewidths=2, zorder=4, label=f"{model}, {CONDS['with_markets']}")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=INK, fontsize=10)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    style(ax)


def legend(fig, ax, ncol=3):
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=ncol, frameon=False, fontsize=8.5, labelcolor=INK2, bbox_to_anchor=(0.5, -0.01))


def main(run):
    run = Path(run)
    out = run / "analysis"
    out.mkdir(exist_ok=True)
    bank = json.loads((run / "questions.json").read_text())["questions"]
    ans = load_answers(run)
    mrows = markets(run)
    pmean, n_polls = poll_means()

    # answers_long.csv
    with open(out / "answers_long.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "condition", "question", "group", "option", "label", "probability"])
        for (model, cond), a in sorted(ans.items()):
            for qid, q in bank.items():
                x = a[qid]
                if x["type"] == "noul":
                    w.writerow([model, cond, qid, q["group"], "true", "true", x["noul"]])
                    continue
                labels = q["criteria"] if isinstance(q["criteria"], dict) else dict(enumerate(q["criteria"]))
                for k, p in x["probabilities"].items():
                    w.writerow([model, cond, qid, q["group"], k, labels.get(k, labels.get(int(k)) if k.isdigit() else k), p])

    # seats.csv + seat chart
    seat_q = [(qid, q["instructions"].removeprefix("How many seats will ").removesuffix(" win?"))
              for qid, q in bank.items() if q["group"] == "seats"]
    seats = []
    for qid, name in seat_q:
        row = {"list": name, "poll_mean": round(pmean.get(name, 0.0), 2),
               "market_median": ladder_median(mrows, KALSHI_LADDER[name]) if name in KALSHI_LADDER else None}
        for (model, cond), a in ans.items():
            d = seat_dist(a, qid)
            row[f"{model} {cond} expected"] = round(sum(k * v for k, v in d.items()), 2)
            row[f"{model} {cond} p_below_threshold"] = round(d.get(0, 0.0), 3)
        seats.append(row)
    with open(out / "seats.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(seats[0]))
        w.writeheader()
        w.writerows(seats)

    fig, ax = plt.subplots(figsize=(8, 7.2), facecolor=SURFACE)
    dot_panel(ax, [s["list"] for s in seats],
              {m: {c: [s[f"{m} {c} expected"] for s in seats] for c in CONDS} for m in COLOR},
              ref=[s["poll_mean"] for s in seats], ref_label=f"Poll mean ({n_polls} polls since {POLL_SINCE})",
              xlabel="Seats (model values are expected seats)")
    ax.set_title("Expected seats by list: decision models vs the final polls", loc="left", color=INK, fontsize=12, pad=12)
    legend(fig, ax)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out / "fig_seats.png", dpi=180)
    plt.close(fig)

    # markets_vs_panel.csv + flip chart
    mv = []
    for qid, opt, prefix, outcome in MARKET_MIRRORS:
        row = {"question": qid, "option": opt or "true", "market": market_price(mrows, prefix, outcome)}
        for (model, cond), a in ans.items():
            row[f"{model} {cond}"] = round(prob(a, qid, opt), 3)
        mv.append(row)
    with open(out / "markets_vs_panel.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(mv[0]))
        w.writeheader()
        w.writerows(mv)

    nice = {("largest_list", "yashar"): "Yashar is the largest list", ("largest_list", "likud"): "Likud is the largest list",
            ("next_pm", "eisenkot"): "Eisenkot is the next PM", ("next_pm", "netanyahu"): "Netanyahu is the next PM",
            ("next_pm", "bennett"): "Bennett is the next PM", ("bloc_most_seats", "opposition"): "Opposition bloc wins more seats",
            ("no_bloc_majority", "true"): "Neither bloc reaches 61", ("second_list", "likud"): "Likud comes second",
            ("third_list", "together"): "Together comes third"}
    fig, ax = plt.subplots(figsize=(8, 6), facecolor=SURFACE)
    dot_panel(ax, [nice[(r["question"], r["option"])] for r in mv],
              {m: {c: [r[f"{m} {c}"] for r in mv] for c in CONDS} for m in COLOR},
              ref=[r["market"] for r in mv], ref_label="Market price (snapshot)", xlabel="Probability")
    ax.set_xlim(-0.02, 1.02)
    ax.set_title("Showing the models the market moves them toward it", loc="left", color=INK, fontsize=12, pad=12)
    legend(fig, ax)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out / "fig_markets.png", dpi=180)
    plt.close(fig)

    # threshold chart
    tq = [(qid, q["instructions"].removeprefix("Will ").removesuffix(" pass the 3.25% electoral threshold and win seats?"))
          for qid, q in bank.items() if qid.startswith("passes_")]
    fig, ax = plt.subplots(figsize=(8, 5.6), facecolor=SURFACE)
    dot_panel(ax, [n for _, n in tq], {m: {c: [ans[(m, c)][qid]["noul"] for qid, _ in tq] for c in CONDS} for m in COLOR},
              ref=[market_price(mrows, "KXISRAELANYSEAT", KALSHI_SEAT_NAMES.get(n)) for _, n in tq],
              ref_label="Kalshi price: wins a seat", xlabel="Probability of passing the 3.25% threshold")
    ax.set_xlim(-0.02, 1.02)
    ax.set_title("Who crosses the threshold?", loc="left", color=INK, fontsize=12, pad=12)
    legend(fig, ax)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out / "fig_threshold.png", dpi=180)
    plt.close(fig)

    # consistency.csv + chart
    def p_below(a, qid, n):
        return sum(v for k, v in seat_dist(a, qid).items() if k < n)
    pairs = [
        ("Yashar largest: yes/no vs choice", lambda a: a["yashar_largest"]["noul"], lambda a: prob(a, "largest_list", "yashar")),
        ("Netanyahu next PM: yes/no vs choice", lambda a: a["netanyahu_remains_pm"]["noul"], lambda a: prob(a, "next_pm", "netanyahu")),
        ("Eisenkot next PM: yes/no vs choice", lambda a: a["eisenkot_pm"]["noul"], lambda a: prob(a, "next_pm", "eisenkot")),
        ("Likud under 32: yes/no vs seats", lambda a: a["likud_below_32"]["noul"], lambda a: p_below(a, "seats_likud", 32)),
        ("Netanyahu bloc 61+: yes/no vs bloc-seat bins", lambda a: a["netanyahu_bloc_61"]["noul"],
         lambda a: sum(v for k, v in a["netanyahu_bloc_seats"]["probabilities"].items() if int(k) >= 4)),
        ("Hung parliament vs 1 - P(either bloc 61+)", lambda a: a["no_bloc_majority"]["noul"],
         lambda a: max(0.0, 1 - a["netanyahu_bloc_61"]["noul"] - a["opposition_zionist_61"]["noul"])),
    ]
    for qid, q in bank.items():
        if qid.startswith("passes_") and f"seats_{qid[7:]}" in bank:
            name = q["instructions"].removeprefix("Will ").removesuffix(" pass the 3.25% electoral threshold and win seats?")
            short = {"The Reservists and the Economic Party": "Reservists", "Religious Zionist Party – Zehut": "RZP–Zehut",
                     "United Arab List (Ra'am)": "Ra'am"}.get(name, name)
            pairs.append((f"{short} passes: yes/no vs seats",
                          (lambda k: lambda a: a[k]["noul"])(qid),
                          (lambda k: lambda a: 1 - seat_dist(a, k).get(0, 0.0))(f"seats_{qid[7:]}")))
    cons = []
    for label, fa, fb in pairs:
        row = {"check": label}
        for (model, cond), a in sorted(ans.items()):
            row[f"{model} {cond} a"], row[f"{model} {cond} b"] = round(fa(a), 3), round(fb(a), 3)
            row[f"{model} {cond} gap"] = round(abs(fa(a) - fb(a)), 3)
        cons.append(row)
    with open(out / "consistency.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cons[0]))
        w.writeheader()
        w.writerows(cons)

    fig, ax = plt.subplots(figsize=(8, 6.4), facecolor=SURFACE)
    labels = [r["check"] for r in cons]
    y = list(range(len(labels)))[::-1]
    for i, (model, dy) in enumerate((("Clef", 0.18), ("Jev 1.14", -0.18))):
        vals = [(r[f"{model} no_markets gap"] + r[f"{model} with_markets gap"]) / 2 for r in cons]
        ax.barh([v + dy for v in y], vals, height=0.32, color=COLOR[model], label=f"{model} (mean of both conditions)")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=INK, fontsize=9)
    ax.set_xlabel("Absolute gap between the two answers (probability)", color=INK2, fontsize=9)
    fig.suptitle("Same question, asked two ways: how far apart are the answers?", x=0.02, ha="left", color=INK, fontsize=12)
    style(ax)
    legend(fig, ax, ncol=2)
    fig.tight_layout(rect=(0, 0.06, 1, 0.96))
    fig.savefig(out / "fig_consistency.png", dpi=180)
    plt.close(fig)

    # summary.json
    bloc = ["Likud", "Shas", "United Torah Judaism", "Otzma Yehudit", "Religious Zionist Party – Zehut"]
    opp = ["Yashar", "Together (B'Yachad)", "The Democrats", "Yisrael Beiteinu",
           "The Reservists and the Economic Party", "Amcha Yisrael"]
    summary = {"run": run.name, "poll_mean_window": {"since": POLL_SINCE, "polls": n_polls}, "panel": {}}
    for (model, cond), a in sorted(ans.items()):
        ev = {s["list"]: s[f"{model} {cond} expected"] for s in seats}
        summary["panel"][f"{model} / {cond}"] = {
            "largest_list": a["largest_list"]["probabilities"], "next_pm": a["next_pm"]["probabilities"],
            "netanyahu_bloc_61": a["netanyahu_bloc_61"]["noul"], "opposition_zionist_61": a["opposition_zionist_61"]["noul"],
            "no_bloc_majority": a["no_bloc_majority"]["noul"],
            "expected_seats_sum_13_lists": round(sum(ev.values()), 1),
            "expected_netanyahu_bloc_ex_noam": round(sum(ev[b] for b in bloc), 1),
            "expected_zionist_opposition": round(sum(ev[o] for o in opp), 1),
            "mean_consistency_gap": round(sum(r[f"{model} {cond} gap"] for r in cons) / len(cons), 3),
        }
    summary["poll_mean_netanyahu_bloc_ex_noam"] = round(sum(pmean.get(b, 0) for b in bloc), 1)
    summary["poll_mean_zionist_opposition"] = round(sum(pmean.get(o, 0) for o in opp), 1)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
