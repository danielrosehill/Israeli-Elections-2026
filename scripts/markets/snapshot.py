"""Snapshot prediction-market prices for the 2026 Knesset election.

Run from the repo root:
    uv run --with httpx python3 -I scripts/markets/snapshot.py

Writes data/markets/snapshot_<UTC timestamp>.csv (one row per market outcome)
and copies it to data/markets/latest.csv. Both APIs are public and keyless:
- Kalshi:     https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=...
- Polymarket: https://gamma-api.polymarket.com/events?slug=...
Prices are probabilities in [0, 1]; `price` is the bid/ask midpoint (Kalshi) or
Polymarket's displayed outcome price. Thin Kalshi markets can have very wide
spreads (e.g. 0.26/0.91), so check bid/ask/last before trusting a midpoint. A snapshot is only meaningful with its
timestamp, so old snapshots are kept rather than overwritten.
"""

import csv
import datetime as dt
import json
import shutil
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "markets"

# Series found via /series?category=Elections on 2026-10-22.
KALSHI_SERIES = [
    "KXISRAELBLOCMAJ", "KXISRAELBLOCMOST", "KXISRAELANYSEAT", "KXISRAELKNESSET",
    "KXISRAEL2ND", "KXISRAEL3RD", "KXISRAEL4TH", "KXISRAELPM", "KXISRAELGOVT",
    "KXISRAELTURNOUT", "KXLIKUDCOUNT", "KXYASHARCOUNT", "KXTOGETHERCOUNT",
    "KXISRDEMCOUNT", "KXSHASCOUNT", "KXBEITEINUCOUNT", "KXKNESSETSEAT",
    "KXISRKNESSETCOUNT", "KXABRAHAMSA",  # mirrored by repercussion questions
]
# Event slugs found via gamma-api /events?tag_slug=israel on 2026-10-22.
POLYMARKET_SLUGS = [
    "israeli-legislative-election-winner",
    "who-will-be-the-next-prime-minister-of-israel-after-the-next-election",
    "israeli-election-results-in-a-hung-parliament",
    "israel-election-will-likud-lose-seats",
    "israel-election-likud-of-seats",
]

FIELDS = ["snapshot_utc", "source", "event_id", "event_title", "market_id", "outcome",
          "price", "bid", "ask", "last", "volume", "liquidity", "url"]


def dollars(market, key):
    # Kalshi returns either cents ("yes_bid") or dollar strings ("yes_bid_dollars").
    if market.get(f"{key}_dollars") not in (None, ""):
        return float(market[f"{key}_dollars"])
    if market.get(key) not in (None, ""):
        return market[key] / 100
    return None


def kalshi(client, now):
    for series in KALSHI_SERIES:
        r = client.get("https://api.elections.kalshi.com/trade-api/v2/events",
                       params={"series_ticker": series, "with_nested_markets": "true", "status": "open"})
        r.raise_for_status()
        for ev in r.json().get("events", []):
            for m in ev.get("markets", []):
                bid, ask = dollars(m, "yes_bid"), dollars(m, "yes_ask")
                last = dollars(m, "last_price")
                mid = (bid + ask) / 2 if bid is not None and ask is not None and ask > 0 else last
                outcome = m.get("yes_sub_title") or json.dumps(m.get("custom_strike") or {}) or m["ticker"]
                yield {
                    "snapshot_utc": now, "source": "kalshi", "event_id": ev["event_ticker"],
                    "event_title": ev.get("title"), "market_id": m["ticker"], "outcome": outcome,
                    "price": mid and round(mid, 4), "bid": bid, "ask": ask, "last": last,
                    "volume": m.get("volume_fp") or m.get("volume"), "liquidity": m.get("liquidity_dollars"),
                    "url": f"https://kalshi.com/markets/{series.lower()}",
                }


def polymarket(client, now):
    for slug in POLYMARKET_SLUGS:
        r = client.get("https://gamma-api.polymarket.com/events", params={"slug": slug})
        r.raise_for_status()
        for ev in r.json():
            for m in ev.get("markets", []):
                if m.get("closed"):
                    continue
                outcomes = json.loads(m.get("outcomes") or "[]")
                prices = json.loads(m.get("outcomePrices") or "[]")
                # Multi-outcome events are a set of Yes/No markets; keep the Yes side.
                for name, price in zip(outcomes, prices):
                    if len(outcomes) == 2 and outcomes[0] == "Yes" and name != "Yes":
                        continue
                    label = m.get("groupItemTitle") or m.get("question")
                    yield {
                        "snapshot_utc": now, "source": "polymarket", "event_id": slug,
                        "event_title": ev.get("title"), "market_id": m.get("slug"),
                        "outcome": label if name == "Yes" else f"{label}: {name}",
                        "price": round(float(price), 4), "bid": m.get("bestBid"), "ask": m.get("bestAsk"),
                        "last": m.get("lastTradePrice"),
                        "volume": m.get("volume"), "liquidity": m.get("liquidity"),
                        "url": f"https://polymarket.com/event/{slug}",
                    }


def main():
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"snapshot_{now.replace(':', '').replace('+0000', 'Z')}.csv"
    with httpx.Client(timeout=30) as client, path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        n = 0
        for row in [*kalshi(client, now), *polymarket(client, now)]:
            w.writerow(row)
            n += 1
    shutil.copy(path, OUT / "latest.csv")
    print(f"{n} rows -> {path}")


if __name__ == "__main__":
    main()
