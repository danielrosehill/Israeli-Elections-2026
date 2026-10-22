"""Assemble the frozen evidence pack every decision model receives.

Run from the repo root:
    python3 -I experiment/build_pack.py <run_dir> [--markets data/markets/latest.csv] [--polls-since 2026-09-01]

Writes, into <run_dir>:
  state_no_markets.md    sections 1-5: rules, outgoing Knesset, lists, polls, news
  state_with_markets.md  the same plus section 6: prediction-market prices
  questions.json         copy of experiment/questions.json with "frozen" set
  manifest.json          sha256 of every input, the build time and the character counts

Both conditions share sections 1-5 byte for byte, so any difference in the
answers comes from the market section alone. Poll and list names are mapped to
the CEC list names (party_en in data/candidate-lists/parties.csv), which are
also the names the questions use.
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

POLL_TO_CEC = {
    "Likud": "Likud", "Yashar (Eisenkot)": "Yashar", "Together (Bennett 2026 + Yesh Atid)": "Together (B'Yachad)",
    "The Democrats (Labor + Meretz)": "The Democrats", "Shas": "Shas", "United Torah Judaism": "United Torah Judaism",
    "Otzma Yehudit": "Otzma Yehudit", "Yisrael Beiteinu": "Yisrael Beiteinu",
    "Religious Zionist Party + Zehut": "Religious Zionist Party – Zehut",
    "Joint List (Hadash–Ta'al + Balad)": "Joint List", "Ra'am": "United Arab List (Ra'am)",
    "The Reservists + NEP": "The Reservists and the Economic Party", "Amcha Yisrael": "Amcha Yisrael",
    "Haredi Public": "Haredi Public", "Blue and White": "Blue and White",
}
SHORT = {  # column headers for the poll table
    "Likud": "Likud", "Yashar": "Yashar", "Together (B'Yachad)": "Together", "The Democrats": "Dem",
    "Shas": "Shas", "United Torah Judaism": "UTJ", "Otzma Yehudit": "Otzma", "Yisrael Beiteinu": "YB",
    "Religious Zionist Party – Zehut": "RZP-Zehut", "Joint List": "Joint", "United Arab List (Ra'am)": "Ra'am",
    "The Reservists and the Economic Party": "Reservists", "Amcha Yisrael": "Amcha", "Haredi Public": "HarediPub",
    "Blue and White": "B&W",
}
TOP_N_MAJOR, TOP_N_MINOR = 10, 3

RULES = """# Evidence pack: election to Israel's 26th Knesset

Polling day: Tuesday 27 October 2026. Pack assembled {built}.

## 1. Electoral rules
- There are 120 seats, elected from one national constituency by closed party lists.
- The threshold is 3.25% of valid votes, roughly 4 seats. A list below it wins 0 seats; a list above it wins at least 4.
- Seats are allocated by the D'Hondt (Bader-Ofer) method. Pairs of lists may sign surplus-vote agreements, which can move one seat.
- Polls may not be published after 23:59 on Friday 23 October 2026.
- Final results are certified by the Central Elections Committee (CEC) about a week after polling day.
- After the results, the president tasks a Knesset member with forming a government, which then needs a Knesset confidence vote.
- In the 2022 election (25th Knesset), turnout was 70.63% of eligible voters.
"""


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def section_knesset():
    parties = read_csv(DATA / "knesset-25" / "parties.csv")
    lines = ["## 2. The outgoing 25th Knesset (elected 1 November 2022)", "",
             "| Faction | Seats won 2022 | Seats at end of term | Leader | Bloc at end |", "|---|---|---|---|---|"]
    for p in sorted(parties, key=lambda p: -int(p["seats_at_end"] or 0)):
        if int(p["seats_at_end"] or 0) == 0 and int(p["seats_won_2022"] or 0) == 0:
            continue
        lines.append(f"| {p['faction_en']} | {p['seats_won_2022']} | {p['seats_at_end']} | {p['leader_en']} | {p['bloc_at_end']} |")
    lines += ["", "Factions with 0 seats at the end of the term split or merged during it. The government at dissolution was led by Benjamin Netanyahu (Likud)."]
    return "\n".join(lines)


def section_lists(polled):
    parties = read_csv(DATA / "candidate-lists" / "parties.csv")
    cands = defaultdict(list)
    for c in read_csv(DATA / "candidate-lists" / "candidates.csv"):
        cands[c["party_en"]].append(c)
    lines = ["## 3. Candidate lists (CEC, approved 27 September 2026)", "",
             "Format: ballot letters | list | leader | component parties. Then the top candidates in list order; (MK) marks a member of the outgoing Knesset.", ""]
    running = [p for p in parties if p["list_status"] != "withdrawn"]
    running.sort(key=lambda p: (p["party_en"] not in polled, p["party_en"]))
    for p in running:
        n = TOP_N_MAJOR if p["party_en"] in polled else TOP_N_MINOR
        top = sorted(cands[p["party_en"]], key=lambda c: int(c["list_position"]))[:n]
        names = "; ".join(f"{c['list_position']}. {c['name_en'] or c['name_he']}" + (" (MK)" if c["incumbent_mk_25"] == "True" else "") for c in top)
        comp = p["alliance_components"] or "-"
        lines.append(f"- **{p['ballot_letters']} | {p['party_en']}** | leader {p['leader_en']} | {comp} | {p['candidates_count_in_dataset']} candidates")
        lines.append(f"  - {names}")
    withdrawn = [p["party_en"] for p in parties if p["list_status"] == "withdrawn"]
    lines += ["", f"Withdrawn after approval: {', '.join(withdrawn)}. All of its candidates resigned on 20-21 October 2026.",
              f"Total: {len(running)} lists running."]
    return "\n".join(lines)


def load_polls():
    polls = {p["poll_id"]: p for p in read_csv(DATA / "polls" / "polls.csv")}
    seats = defaultdict(dict)
    for r in read_csv(DATA / "polls" / "poll_results.csv"):
        if r["scenario"] != "standard":
            continue
        seats[r["poll_id"]][POLL_TO_CEC.get(r["party"], r["party"])] = int(r["seats"] or 0)
    return polls, seats


def section_polls(polls, seats, since):
    recent = sorted((pid for pid in seats if polls[pid]["release_date"] >= since),
                    key=lambda pid: polls[pid]["release_date"], reverse=True)
    cols = [p for p in SHORT if any(p in seats[pid] for pid in recent)]
    lines = [f"## 4. Opinion polls (seat projections)", "",
             f"### 4a. Every standard poll published since {since}, newest first ({len(recent)} polls)", "",
             "Columns are seats per list. 0 means the poll put the list below the threshold or gave no figure; a blank cell means the poll did not list it. "
             "'Gov' is the poll's seat total for the outgoing government's parties (Likud, Shas, UTJ, Otzma, RZP, Noam). "
             "n is the sample size where reported.", "",
             "| Date | Pollster | Outlet | n | " + " | ".join(SHORT[c] for c in cols) + " | Gov |",
             "|" + "---|" * (len(cols) + 5)]
    for pid in recent:
        p = polls[pid]
        lines.append(f"| {p['release_date']} | {p['pollster']} | {p['publisher']} | {p['sample_size'] or ''} | "
                     + " | ".join(str(seats[pid].get(c, "")) for c in cols) + f" | {p['coalition_seats']} |")

    # 4b: monthly means for 2026, to show the trend before the current table starts.
    monthly = defaultdict(lambda: defaultdict(list))
    counts = defaultdict(int)
    for pid, s in seats.items():
        d = polls[pid]["release_date"]
        if "2026-01-01" <= d < since:
            counts[d[:7]] += 1
            for party, v in s.items():
                monthly[d[:7]][party].append(v)
    months = sorted(monthly)
    trend_cols = [p for p in SHORT if p in POLL_TO_CEC.values() and all(p in monthly[m] for m in months[-3:])]
    lines += ["", f"### 4b. Monthly mean seats, January 2026 to before {since}",
              "", "A blank cell means the list did not yet exist in that form.", "",
              "| Month | polls | " + " | ".join(SHORT[c] for c in trend_cols) + " |", "|" + "---|" * (len(trend_cols) + 2)]
    for m in months:
        lines.append(f"| {m} | {counts[m]} | " + " | ".join(
            f"{statistics.mean(monthly[m][c]):.1f}" if monthly[m].get(c) else "" for c in trend_cols) + " |")

    # 4c: last-30-day mean per pollster, to expose house effects.
    cutoff = (dt.date.fromisoformat(polls[recent[0]]["release_date"]) - dt.timedelta(days=30)).isoformat()
    by_house = defaultdict(lambda: defaultdict(list))
    for pid in recent:
        if polls[pid]["release_date"] >= cutoff:
            for party, v in seats[pid].items():
                by_house[polls[pid]["pollster"]][party].append(v)
    house_cols = [c for c in ("Likud", "Yashar", "Together (B'Yachad)", "The Reservists and the Economic Party", "Amcha Yisrael", "Religious Zionist Party – Zehut") if c in cols]
    lines += ["", f"### 4c. Mean by pollster, polls since {cutoff}", "",
              "| Pollster | polls | " + " | ".join(SHORT[c] for c in house_cols) + " | Gov |", "|" + "---|" * (len(house_cols) + 3)]
    gov = defaultdict(list)
    for pid in recent:
        if polls[pid]["release_date"] >= cutoff and polls[pid]["coalition_seats"]:
            gov[polls[pid]["pollster"]].append(int(polls[pid]["coalition_seats"]))
    for house, s in sorted(by_house.items(), key=lambda kv: -len(next(iter(kv[1].values())))):
        n = max(len(v) for v in s.values())
        g = f"{statistics.mean(gov[house]):.1f}" if gov[house] else ""
        lines.append(f"| {house} | {n} | " + " | ".join(f"{statistics.mean(s[c]):.1f}" if s.get(c) else "" for c in house_cols)
                     + f" | {g} |")
    return "\n".join(lines), {c for c in cols}


MARKET_EVENTS = [  # (event_id prefix, label, max outcomes shown)
    ("israeli-legislative-election-winner", "Polymarket: list with the most seats", 6),
    ("KXISRAELKNESSET", "Kalshi: list with the most seats", 6),
    ("who-will-be-the-next-prime-minister", "Polymarket: next prime minister", 6),
    ("KXISRAELPM-", "Kalshi: prime minister after the election", 6),
    ("KXISRAELBLOCMAJ", "Kalshi: which bloc wins a majority (61+)", 3),
    ("KXISRAELBLOCMOST", "Kalshi: which bloc wins the most seats", 2),
    ("israeli-election-results-in-a-hung-parliament", "Polymarket: hung parliament", 1),
    ("KXISRAELANYSEAT", "Kalshi: which lists win a seat (pass the threshold)", 23),
    ("KXISRAEL2ND", "Kalshi: second place", 4),
    ("KXISRAEL3RD", "Kalshi: third place", 4),
    ("israel-election-likud-of-seats", "Polymarket: Likud seats", 5),
    ("KXLIKUDCOUNT", "Kalshi: Likud seats", 8), ("KXYASHARCOUNT", "Kalshi: Yashar seats", 8),
    ("KXTOGETHERCOUNT", "Kalshi: Together seats", 8), ("KXISRDEMCOUNT", "Kalshi: The Democrats seats", 8),
    ("KXSHASCOUNT", "Kalshi: Shas seats", 8), ("KXBEITEINUCOUNT", "Kalshi: Yisrael Beiteinu seats", 8),
    ("KXISRAELTURNOUT", "Kalshi: votes cast", 12),
]


def section_markets(path):
    rows = read_csv(path)
    snap = rows[0]["snapshot_utc"]
    lines = ["## 6. Prediction-market prices", "",
             f"Snapshot {snap} UTC. A price is the market's implied probability (0-1). Kalshi prices are bid/ask midpoints. "
             "Volume is in USD; thin markets (low volume, wide spread) are noisy.", ""]
    for prefix, label, n in MARKET_EVENTS:
        ev = [r for r in rows if r["event_id"].startswith(prefix)]
        if not ev:
            continue
        if "COUNT" not in prefix and "TURNOUT" not in prefix and prefix != "israel-election-likud-of-seats":
            ev.sort(key=lambda r: -float(r["price"] or 0))
        vol = sum(float(r["volume"] or 0) for r in ev)
        lines.append(f"- **{label}** (total volume ${vol:,.0f}): " + "; ".join(
            f"{r['outcome']} {float(r['price']):.2f}" for r in ev[:n] if r["price"]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--markets", type=Path, default=DATA / "markets" / "latest.csv")
    ap.add_argument("--polls-since", default="2026-09-01")
    ap.add_argument("--news", type=Path, default=ROOT / "experiment" / "evidence" / "news.md")
    args = ap.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=True)
    built = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

    polls, seats = load_polls()
    poll_text, polled = section_polls(polls, seats, args.polls_since)
    news = args.news.read_text().strip()
    base = "\n\n".join([
        RULES.format(built=built), section_knesset(), section_lists(polled), poll_text,
        "## 5. News digest\n\n" + news,
    ]) + "\n"
    with_markets = base + "\n" + section_markets(args.markets) + "\n"
    (args.run_dir / "state_no_markets.md").write_text(base)
    (args.run_dir / "state_with_markets.md").write_text(with_markets)

    bank = json.loads((ROOT / "experiment" / "questions.json").read_text())
    bank["frozen"] = built
    (args.run_dir / "questions.json").write_text(json.dumps(bank, indent=2, ensure_ascii=False))

    sources = [DATA / "knesset-25" / "parties.csv", DATA / "candidate-lists" / "parties.csv",
               DATA / "candidate-lists" / "candidates.csv", DATA / "polls" / "polls.csv",
               DATA / "polls" / "poll_results.csv", args.markets, args.news,
               ROOT / "experiment" / "questions.json"]
    manifest = {
        "built_utc": built, "polls_since": args.polls_since,
        "inputs": {str(p.resolve().relative_to(ROOT)) if p.resolve().is_relative_to(ROOT) else str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "outputs": {n: {"chars": len((args.run_dir / n).read_text()),
                        "sha256": hashlib.sha256((args.run_dir / n).read_bytes()).hexdigest()}
                    for n in ("state_no_markets.md", "state_with_markets.md", "questions.json")},
    }
    (args.run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest["outputs"], indent=2))


if __name__ == "__main__":
    main()
