#!/usr/bin/env python3
"""Build the 2026 Knesset election seat-projection poll dataset from Wikipedia.

Usage (from the repo root):

    uv run --with pandas --with lxml --with beautifulsoup4 \
        python3 -I scripts/polls/build.py [--raw-dir DIR] [--refresh]

Steps:
  1. Download the parsed HTML of each English Wikipedia page listed in PAGES via the
     MediaWiki API (curl), caching the JSON in --raw-dir. --refresh re-downloads.
  2. Walk every wikitable whose first header cell is "Fieldwork date" inside the
     "Seat projections" (standard) or "Scenario polls" (hypothetical) sections.
  3. Expand rowspan/colspan into a full grid, derive one label per column from the
     multi-row header, and parse every data cell into seats / below-threshold share.
  4. Write data/polls/{polls,poll_results,party_aliases}.csv and print sanity checks.

See data/polls/SOURCES.md for the conventions and pitfalls.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup, Tag

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "polls"
DEFAULT_RAW = Path(
    "/var/tmp/claude-1000/-home-daniel-repos-github-israel-Israeli-Elections-2026/"
    "bfe1fe8c-7a76-4f80-b5c7-edec167abf2f/scratchpad/polls-raw"
)
API = "https://en.wikipedia.org/w/api.php"
UA = "Israeli-Elections-2026-dataset/1.0 (https://github.com/danielrosehill)"

# Page title -> default year used when a date cell has no data-sort-value.
PAGES = [
    ("Opinion polling for the 2026 Israeli legislative election", None),
    ("2025 opinion polling for the 2026 Israeli legislative election", 2025),
    ("2024 opinion polling for the 2026 Israeli legislative election", 2024),
    ("2022–2023 opinion polling for the 2026 Israeli legislative election", None),
]

ELECTION_2022 = dt.date(2022, 11, 1)
TODAY = dt.date(2026, 10, 22)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# --------------------------------------------------------------------------------------
# Normalisation tables
# --------------------------------------------------------------------------------------

# Polling-firm strings as written in the tables (abbreviations are defined in the
# "Pollsters and publishers" table at the top of the main page).
POLLSTER_MAP = {
    "Midgam R&C": "Midgam Research & Consulting",
    "Midgam": "Midgam Research & Consulting",
    "Midgam Research & Consulting": "Midgam Research & Consulting",
    "LRI+P4A": "Lazar Research Institute + Panel4All",
    "Lazar": "Lazar Research Institute",
    "LRI": "Lazar Research Institute",
    "Lazar Research Institute": "Lazar Research Institute",
    "SF+ND": "Shlomo Filber + NEXT DATA",
    "SF+DP": "Shlomo Filber + Direct Polls",
    "SF": "Shlomo Filber",
    "Shlomo Filber": "Shlomo Filber",
    "Direct Polls": "Direct Polls",
    "DP": "Direct Polls",
    "Kantar": "Kantar Institute",
    "Kantar Institute": "Kantar Institute",
    "Maagar Mochot": "Maagar Mochot",
    "MM": "Maagar Mochot",
    "MM+SN": "Maagar Mochot + Stat-Net",
    "CF+MP+SN": "Camil Fuchs + Midgam Project + Stat-Net",
    "MP+TM+SN+A": "Midgam Project + The Madad + Stat-Net + Askaria",
    "Panels Politics": "Panels Politics",
    "Yossi Tatika": "Yossi Tatika",
    "Stat-Net Research Institute": "Stat-Net Research Institute",
    "Agam": "Agam Research",
    "Agam Research": "Agam Research",
    "Filber": "Shlomo Filber",
    "MP+TM+SN+A`": "Midgam Project + The Madad + Stat-Net + Askaria",  # stray backtick in source
    "Midgam Project & Stat Net": "Midgam Project + Stat-Net",
    "S.M.L.T.": "S.M.L.T.",
    "Smith Consulting": "Smith Consulting",
    "Timor Group": "Timor Group",
    "TrendZone": "TrendZone",
}

PUBLISHER_MAP = {
    "HaHadashot 12": "Channel 12 (HaHadashot 12)",
    "Channel 12": "Channel 12 (HaHadashot 12)",
    "N12": "Channel 12 (HaHadashot 12)",
    "Channel 13": "Channel 13",
    "Channel 14": "Channel 14",
    "Channel 16": "Channel 16",
    "Kan 11": "Kan 11",
    "Kan": "Kan 11",
    "Maariv": "Maariv",
    "Walla": "Walla",
    "Walla!": "Walla",
    "Israel Hayom": "Israel Hayom",
    "i24 News": "i24 News",
    "i24NEWS": "i24 News",
    "Zman Yisrael": "Zman Yisrael",
    "Zman Israel": "Zman Yisrael",
    "Arutz Sheva": "Arutz Sheva",
    "The Jerusalem Post": "The Jerusalem Post",
    "The Times of Israel": "The Times of Israel",
    "The Truth Machine": "The Truth Machine",
    "Amit Segal": "Amit Segal (journalist)",
    "Attila Somfalvi": "Attila Somfalvi (journalist)",
    "–": "(none listed)",
    "—": "(none listed)",
    "": "(none listed)",
}

# party_as_listed (header label, or "A+B" for a cell spanning several columns)
# -> (normalised party, note). Anything not listed passes through unchanged and is
# flagged in party_aliases.csv with note "unmapped".
PARTY_MAP = {
    "Likud": ("Likud", ""),
    "Yesh Atid": ("Yesh Atid", "Ran alone in 2022; polled alone until it was folded into 'Together' with Bennett 2026 (2026)."),
    "Together": ("Together (Bennett 2026 + Yesh Atid)", "Joint list of Bennett 2026 and Yesh Atid announced in 2026."),
    "Bennett 2026+Yesh Atid": ("Together (Bennett 2026 + Yesh Atid)", "Cell spanning the Bennett 2026 and Yesh Atid sub-columns of the 'Together' header = joint run."),
    "Bennett 2026": ("Bennett 2026", "Naftali Bennett's party; earlier polls call it 'Party of Naftali Bennett' / 'Bennett'."),
    "Bennett": ("Bennett 2026", "Hypothetical Bennett party before it was founded; same entity as Bennett 2026."),
    "RZP": ("Religious Zionist Party", ""),
    "Zehut": ("Zehut", ""),
    "RZP-Zehut": ("Religious Zionist Party + Zehut", "Technical bloc RZP + Zehut for 2026."),
    "RZP - Zehut": ("Religious Zionist Party + Zehut", "Technical bloc RZP + Zehut for 2026."),
    "RZP+Zehut": ("Religious Zionist Party + Zehut", "Technical bloc RZP + Zehut for 2026."),
    "Otzma": ("Otzma Yehudit", "Ran jointly with RZP in 2022."),
    "Blue & White": ("Blue and White", "Benny Gantz's party; ran as National Unity in 2022 and polled under that name until the National Unity split (2025)."),
    "National Unity": ("National Unity", "Gantz-Eisenkot list 2022; later polled as Blue & White after Eisenkot left."),
    "New Hope": ("New Hope", "Gideon Sa'ar; ran inside National Unity in 2022, later merged into Likud."),
    "Shas": ("Shas", ""),
    "UTJ": ("United Torah Judaism", "Agudat Yisrael + Degel HaTorah (+ Homat Torat Yisrael)."),
    "Yisrael Beiteinu": ("Yisrael Beiteinu", ""),
    "Ra'am": ("Ra'am", "Technical bloc with Yoav Segalovitz in 2026."),
    "Hadash –Ta'al": ("Hadash–Ta'al", ""),
    "Hadash–Ta'al": ("Hadash–Ta'al", ""),
    "Balad": ("Balad", ""),
    "Joint List": ("Joint List (Hadash–Ta'al + Balad)", "In the newest tables 'Joint List' is a single column next to a separate Ra'am column: Hadash–Ta'al + Balad."),
    "Hadash –Ta'al+Balad": ("Joint List (Hadash–Ta'al + Balad)", "Cell spanning Hadash–Ta'al and Balad sub-columns = joint run."),
    "Ra'am+Hadash –Ta'al+Balad": ("Joint List (Ra'am + Hadash–Ta'al + Balad)", "Cell spanning all three Arab-party sub-columns = four-party Joint List incl. Ra'am."),
    "Ra'am+Hadash –Ta'al": ("Ra'am + Hadash–Ta'al", "Cell spanning two sub-columns."),
    "Labor": ("Labor", "Merged with Meretz into The Democrats (June 2024)."),
    "Meretz": ("Meretz", "Merged with Labor into The Democrats (June 2024)."),
    "Labor+Meretz": ("The Democrats (Labor + Meretz)", "Joint cell before the formal merger."),
    "Dems": ("The Democrats (Labor + Meretz)", ""),
    "The Democrats": ("The Democrats (Labor + Meretz)", ""),
    "Yashar": ("Yashar (Eisenkot)", "Gadi Eisenkot's party; polls before 16 Sep 2025 call it 'Party of Gadi Eisenkot'."),
    "Eisenkot": ("Yashar (Eisenkot)", "Hypothetical Eisenkot party, later named Yashar."),
    "Reserv.": ("The Reservists (Hendel)", "Yoaz Hendel's party; polls before 18 Sep 2025 call it 'Party of Yoaz Hendel'."),
    "Hendel": ("The Reservists (Hendel)", "Hypothetical Hendel party, later The Reservists."),
    "Reserv.-NEP": ("The Reservists + NEP", "Joint run of The Reservists and NEP (2026)."),
    "Reserv. - NEP": ("The Reservists + NEP", "Joint run of The Reservists and NEP (2026)."),
    "Reserv.+NEP": ("The Reservists + NEP", "Joint run of The Reservists and NEP (2026)."),
    "NEP": ("NEP", ""),
    "Amcha Yisrael": ("Amcha Yisrael", ""),
    "Haredi Public": ("Haredi Public", ""),
    "Zionist Home": ("Zionist Home", ""),
    "Unity": ("Unity", ""),
    "Winter party": ("Ofer Winter party", ""),
    "Winter": ("Ofer Winter party", ""),
    "Noam": ("Noam", ""),
    "Jewish Home": ("Jewish Home", ""),
    "The Jewish Home": ("Jewish Home", ""),
    "Cohen": ("Yossi Cohen party (hypothetical)", ""),
    "Gallant": ("Yoav Gallant party (hypothetical)", ""),
    "Tropper": ("Hili Tropper party", ""),
    "Simchi": ("Dedi Simchi party", ""),
    "Netanyahu": ("Benjamin Netanyahu party (hypothetical)", ""),
    "Likud B": ("Likud B (hypothetical)", ""),
    "Ahi": ("Ahi", ""),
    "Likud (led by Netanyahu)": ("Likud", "Alternative-leadership table: Likud under Netanyahu (baseline column)."),
    "Likud (led by Barkat)": ("Likud (led by Nir Barkat, scenario)", "Alternative-leadership scenario."),
    "Likud (led by Cohen)": ("Likud (led by Yossi Cohen, scenario)", "Alternative-leadership scenario."),
    "Likud (led by Gallant)": ("Likud (led by Yoav Gallant, scenario)", "Alternative-leadership scenario."),
    "Naftali Bennett": ("Bennett 2026", "Hypothetical Bennett party before it was founded."),
    "Bennett party": ("Bennett 2026", "Hypothetical Bennett party before it was founded."),
    "Hendel party": ("The Reservists (Hendel)", "Hypothetical Hendel party before it was founded."),
    "Hendel & Bennett": ("Bennett 2026 + The Reservists (Hendel) (scenario)", "Hendel-Bennett merger scenario."),
    "Bennett + Cohen": ("Bennett 2026 + Yossi Cohen party (scenario)", "Joint Bennett-Cohen party scenario."),
    "Levin": ("Yariv Levin party (hypothetical)", ""),
    "Protest Party": ("Reform protest party (hypothetical)", ""),
    "Right-wing liberal party": ("Right-wing liberal party (hypothetical)", ""),
    "Tov+ Haddad + Deri": ("Shem Tov + Haddad + Deri party (hypothetical)", "Netali Shem Tov, Yoseph Haddad and Lali Deri joint party scenario."),
}

# Sub-column labels that name a prospective party leader rather than a party
# (only honoured inside "Alternative leadership" tables).
LEADER_SUBCOLUMNS = {"Netanyahu", "Barkat", "Cohen", "Gallant"}

META_HEADERS = {
    "fieldwork date": "date",
    "date": "date",
    "polling firm": "pollster",
    "publisher": "publisher",
    "sample size": "sample",
    "others": "others",
    "other": "others",
    "gov.": "gov",
    "gov": "gov",
    "gov. total": "gov",
    "lead": "lead",
    "opp.": "opp",
}

# --------------------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------------------

def slug(s: str) -> str:
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def fetch(title: str, raw_dir: Path, refresh: bool) -> dict:
    path = raw_dir / (slug(title) + ".json")
    if refresh or not path.exists():
        raw_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["curl", "-sS", "--fail", "-G", API, "-A", UA,
             "--data-urlencode", f"page={title}",
             "-d", "action=parse", "-d", "prop=text|revid", "-d", "format=json",
             "-d", "redirects=1", "-o", str(path)],
            check=True)
    data = json.loads(path.read_text(encoding="utf-8"))
    if "error" in data:
        raise SystemExit(f"API error for {title}: {data['error']}")
    return data["parse"]


# --------------------------------------------------------------------------------------
# HTML helpers
# --------------------------------------------------------------------------------------

def cell_text(c: Tag) -> str:
    """Visible text with footnote markers and hidden sort keys removed."""
    c = BeautifulSoup(str(c), "lxml").find(["td", "th"])
    for s in c.find_all(["sup", "style", "link"]):
        s.decompose()
    for s in c.select(".sr-only, .sortkey, [style*='display:none']"):
        s.decompose()
    t = c.get_text(" ", strip=True)
    t = t.replace(" ", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def cell_notes(c: Tag) -> list[str]:
    ids = []
    for a in c.select("sup a[href^='#']"):
        ids.append(a["href"][1:])
    return ids


def expand(rows: list[Tag]):
    """Expand a list of <tr> into a grid. Each slot = (cell, is_origin_row, col_start, colspan)."""
    grid: list[list] = []
    pending: dict[int, tuple] = {}  # col -> (cell, rows_left, start, span)
    for r in rows:
        line: list = []
        col = 0
        cells = r.find_all(["td", "th"], recursive=False)
        it = iter(cells)
        nxt = next(it, None)
        while nxt is not None or col in pending:
            if col in pending:
                cell, left, start, span = pending[col]
                line.append((cell, False, start, span))
                if left - 1 <= 0:
                    del pending[col]
                else:
                    pending[col] = (cell, left - 1, start, span)
                col += 1
                continue
            cs = int(re.sub(r"\D", "", nxt.get("colspan", "1")) or 1)
            rs = int(re.sub(r"\D", "", nxt.get("rowspan", "1")) or 1)
            start = col
            for k in range(cs):
                line.append((nxt, True, start, cs))
                if rs > 1:
                    pending[col] = (nxt, rs - 1, start, cs)
                col += 1
            nxt = next(it, None)
        grid.append(line)
    return grid


def header_labels(header_rows: list[Tag]):
    """Return per-column (leaf_label, top_label, top_span_cols)."""
    grid = expand(header_rows)
    ncols = max(len(l) for l in grid)
    labels = []
    for j in range(ncols):
        texts = []
        for line in grid:
            if j < len(line):
                cell = line[j][0]
                t = cell_text(cell)
                if t and (not texts or texts[-1][0] != t):
                    texts.append((t, cell, line[j][2], line[j][3]))
        if not texts:
            labels.append(("", "", (j, 1)))
            continue
        top = texts[0]
        leaf = texts[-1]
        labels.append((leaf[0], top[0], (top[2], top[3])))
    # A multi-column top header with no sub-labels (e.g. "RZP - Zehut" colspan=2 over
    # colour cells only): split its text into one name per column when possible.
    groups = defaultdict(list)
    for j, (leaf, top, (st, sp)) in enumerate(labels):
        if sp > 1 and leaf == top:
            groups[(st, sp, top)].append(j)
    for (st, sp, top), cols in groups.items():
        parts = [p.strip() for p in re.split(r"\s+-\s+|\s*-\s*(?=[A-Z])", top) if p.strip()]
        if len(parts) == sp == len(cols):
            for j, p in zip(cols, parts):
                labels[j] = (p, top, (st, sp))
    return labels


def norm_header(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("\n", " ")).strip()


def parse_value(cell: Tag, text: str):
    """Classify a party cell. Returns dict or None for 'not in this poll'."""
    classes = cell.get("class") or []
    if "table-na" in classes or text in ("N/a", "— N/a") or text.endswith("N/a"):
        return None
    t = text.replace("−", "-").strip()
    if t == "":
        return {"status": "empty", "seats": None, "pct": None, "nt": None}
    m = re.fullmatch(r"(\d+)", t)
    if m:
        return {"status": "seats", "seats": int(m.group(1)), "pct": None, "nt": None}
    m = re.fullmatch(r"(\d+)\s*\(\s*~?(\d+(?:\.\d+)?)\s*%\s*\)", t)
    if m:  # seats plus vote share, e.g. "4 (3.5%)"
        return {"status": "seats", "seats": int(m.group(1)), "pct": float(m.group(2)), "nt": None}
    m = re.fullmatch(r"\(\s*[<~]?\s*(\d+(?:\.\d+)?)\s*%\s*\)", t)
    if m:
        return {"status": "below_threshold_pct", "seats": 0, "pct": float(m.group(1)), "nt": None,
                "lt": "<" in t}
    m = re.fullmatch(r"\(\s*(\d+)\s*\)", t)
    if m:
        return {"status": "below_threshold_no_threshold_seats", "seats": 0, "pct": None,
                "nt": int(m.group(1))}
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%", t)
    if m:  # bare percentage in a seat table: treat as below-threshold share
        return {"status": "below_threshold_pct", "seats": 0, "pct": float(m.group(1)), "nt": None}
    if t in ("–", "-", "—"):
        return {"status": "dash", "seats": 0, "pct": None, "nt": None}
    if t in ("?", "TBA"):
        return {"status": "unknown", "seats": None, "pct": None, "nt": None}
    return {"status": "unparsed", "seats": None, "pct": None, "nt": None, "raw": t}


def parse_int(text: str):
    t = re.sub(r"[,\s]", "", text)
    m = re.fullmatch(r"~?(\d+)", t)
    return int(m.group(1)) if m else None


def parse_date(cell: Tag, text: str, default_year: int | None, context_year: int | None):
    """Return (start, end) dates. data-sort-value (ISO, = end date) wins for the end."""
    end = None
    dsv = cell.get("data-sort-value")
    if dsv and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dsv):
        end = dt.date.fromisoformat(dsv)
    t = text.replace("–", "-").replace("—", "-")
    # tokens: day month? year?
    parts = [p.strip() for p in t.split("-")]
    def tok(p):
        # "3", "3 Sep", "Sep", "3 Sep 2025", "3 Sep 25" (scenario tables use 2-digit years)
        m = re.fullmatch(r"(\d{1,2})?\s*([A-Za-z]+)?\.?\s*(\d{4}|\d{2})?", p.strip())
        if not m:
            return None
        d, mo, y = m.groups()
        mo = MONTHS.get(mo[:3].lower()) if mo else None
        y = int(y) if y else None
        if y is not None and y < 100:
            y += 2000
        if d is not None and mo is None and y is None and len(p.strip()) == 4:
            return None
        return (int(d) if d else None, mo, y)
    toks = [tok(p) for p in parts if p]
    toks = [x for x in toks if x]
    if not toks:
        return None, end
    # propagate month/year backwards
    last = list(toks[-1])
    year = last[2] or (end.year if end else None) or context_year or default_year
    mo_end = last[1] or (end.month if end else None)
    d_end = last[0] or 1
    try:
        e = dt.date(year, mo_end, d_end) if year and mo_end else None
    except ValueError:
        e = None
    if end is None:
        end = e
    s = None
    if len(toks) >= 2 and end:
        d0, m0, y0 = toks[0]
        m0 = m0 or end.month
        y0 = y0 or (end.year if m0 <= end.month else end.year - 1)
        try:
            s = dt.date(y0, m0, d0 or 1)
        except ValueError:
            s = None
    elif end:
        s = end
    return s, end


# --------------------------------------------------------------------------------------
# References (for source URL + publication date)
# --------------------------------------------------------------------------------------

DATE_RE = re.compile(
    r"(\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4})"
    r"|((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})"
    r"|(\d{4}-\d{2}-\d{2})")


def build_refs(soup: BeautifulSoup):
    refs = {}
    for li in soup.select("ol.references > li[id]"):
        a = li.select_one("a.external[href]")
        text = li.get_text(" ", strip=True).lstrip("^ ").strip()
        text = re.sub(r"^(?:[a-z]{1,2} )+", "", text) if text[:2].strip() else text
        date = None
        body = re.split(r"\b(?:Retrieved|Archived from)\b", li.get_text(" ", strip=True))[0]
        for m in DATE_RE.finditer(body):
            s = next(g for g in m.groups() if g)
            for fmt in ("%d %B %Y", "%B %d, %Y", "%Y-%m-%d"):
                try:
                    date = dt.datetime.strptime(s, fmt).date()
                    break
                except ValueError:
                    pass
            if date:
                break  # first date in a citation is the publication date
        refs[li["id"]] = {"url": a["href"] if a else "", "date": date, "text": text,
                          "is_note": a is None}
    return refs


# --------------------------------------------------------------------------------------
# Main extraction
# --------------------------------------------------------------------------------------

def section_path(table: Tag):
    """Nearest preceding h2/h3/h4 headings."""
    h = {}
    for lvl in ("h2", "h3", "h4"):
        prev = table.find_previous(lvl)
        h[lvl] = (prev.get_text(" ", strip=True), prev) if prev else ("", None)
    # h3/h4 only count if they come after the h2
    out = {"h2": h["h2"][0], "h3": "", "h4": ""}
    h2 = h["h2"][1]
    for lvl in ("h3", "h4"):
        el = h[lvl][1]
        if el is not None and h2 is not None and h2 in el.find_all_previous("h2"):
            out[lvl] = h[lvl][0]
    if out["h4"] and h["h3"][1] is not None and h["h4"][1] is not None:
        # h4 must be after the current h3
        if h["h3"][1] not in h["h4"][1].find_all_previous("h3"):
            out["h4"] = ""
    return out


def extract(raw_dir: Path, refresh: bool):
    polls, results, log = [], [], Counter()
    unparsed = []
    page_meta = []
    seq = 0
    for title, default_year in PAGES:
        p = fetch(title, raw_dir, refresh)
        page_url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
        page_meta.append((title, p["revid"]))
        soup = BeautifulSoup(p["text"]["*"], "lxml")
        refs = build_refs(soup)
        for ti, table in enumerate(soup.find_all("table", class_="wikitable")):
            first = table.find("th")
            ft = cell_text(first).lower() if first else ""
            if not (ft.startswith("fieldwork") or ft == "date"):
                continue
            sec = section_path(table)
            if sec["h2"].startswith("Seat projections"):
                kind = "standard"
            elif sec["h2"].startswith("Scenario polls"):
                kind = "scenario"
            else:
                log[f"skipped table in section {sec['h2']}"] += 1
                continue
            context_year = int(sec["h3"]) if re.fullmatch(r"\d{4}", sec["h3"] or "") else default_year
            rows = table.find_all("tr")
            hdr = []
            for r in rows:
                if r.find("td"):
                    break
                hdr.append(r)
            data_rows = rows[len(hdr):]
            labels = header_labels(hdr)
            if "Alternative leadership" in sec["h3"]:
                # e.g. "Likud" spanning "Netanyahu | Barkat | Cohen | Gallant": one column
                # per prospective leader, not separate parties
                labels = [(f"{top} (led by {leaf})", top, sp) if top != leaf and leaf in LEADER_SUBCOLUMNS
                          else (leaf, top, sp) for leaf, top, sp in labels]
            colrole = []
            for leaf, top, _ in labels:
                role = "party"
                for k in (leaf, top):  # leaf first: "Gov. total" sits under "Government bloc"
                    key = re.sub(r"\s*\[.*?\]", "", norm_header(k).lower())
                    if key in META_HEADERS:
                        role = META_HEADERS[key]
                        break
                colrole.append(role)
            grid = expand(data_rows)
            group_of = {}  # id(date cell) -> group index
            group_rows = defaultdict(list)
            for ri, line in enumerate(grid):
                if not line:
                    continue
                # event / commentary rows: one cell spans most of the table
                spans = [s for (_, origin, _, s) in line]
                if max(spans) >= 8 and len({id(c) for c, *_ in line}) <= 3:
                    log["event rows skipped"] += 1
                    continue
                datecell = line[0][0]
                pollster_txt = cell_text(line[1][0]) if len(line) > 1 else ""
                if "election" in pollster_txt.lower() and "result" not in pollster_txt.lower() \
                        and re.search(r"legislative election", pollster_txt):
                    log["election-result rows skipped"] += 1
                    continue
                g = group_of.setdefault(id(datecell), len(group_of))
                group_rows[g].append(line)
            for g, lines in group_rows.items():
                base_na = None
                for k, line in enumerate(lines):
                    seq += 1
                    rec = parse_row(line, labels, colrole, refs, default_year, context_year)
                    if rec is None:
                        log["rows without any figures skipped"] += 1
                        continue
                    rec["source_page"] = title
                    rec["source_page_revid"] = p["revid"]
                    rec["source_table_index"] = ti
                    rec["source_order"] = seq
                    rec["section"] = " / ".join(x for x in (sec["h2"], sec["h3"], sec["h4"]) if x)
                    na = rec.pop("_na_parties")
                    present = {r["party_as_listed"] for r in rec["_results"]}
                    if kind == "standard":
                        if k == 0:
                            rec["scenario"] = "standard"
                            base_na = (na, present)
                        else:
                            added = sorted(present - base_na[1])
                            removed = sorted(base_na[1] - present)
                            desc = []
                            if added:
                                desc.append("with " + ", ".join(added))
                            if removed:
                                desc.append("without " + ", ".join(removed))
                            rec["scenario"] = (f"alternative {k + 1} (same poll, second row): "
                                               + ("; ".join(desc) if desc else "different list configuration"))
                    else:
                        rec["scenario"] = f"hypothetical: {sec['h4'] or sec['h3']}" + (
                            f" (row {k + 1})" if len(lines) > 1 else "")
                    rec["scenario_group"] = f"{ti}-{g}"
                    polls.append(rec)
                    for r in rec["_results"]:
                        if r["cell_status"] == "unparsed":
                            unparsed.append((rec["fieldwork_end"], r["party_as_listed"], r["raw"]))
    return polls, log, unparsed, page_meta


def parse_row(line, labels, colrole, refs, default_year, context_year):
    get = lambda role: next(((j, line[j]) for j, r in enumerate(colrole) if r == role and j < len(line)), (None, None))
    jd, d = get("date")
    jp, pc = get("pollster")
    jb, bc = get("publisher")
    js, sc = get("sample")
    jo, oc = get("others")
    jg, gc = get("gov")
    if d is None:
        return None
    dtext = cell_text(d[0])
    start, end = parse_date(d[0], dtext, default_year, context_year)
    note_ids = []
    for slot in (d, pc, bc, sc, oc):
        if slot is not None:
            note_ids += cell_notes(slot[0])
    publisher_raw = cell_text(bc[0]) if bc else ""
    pollster_raw = cell_text(pc[0]) if pc else ""
    src_refs = [refs[i] for i in (cell_notes(bc[0]) if bc else []) if i in refs and not refs[i]["is_note"]]
    if not src_refs:
        src_refs = [refs[i] for i in note_ids if i in refs and not refs[i]["is_note"]]
    pub_date = src_refs[0]["date"] if src_refs else None
    date_note = ""
    if pub_date and end is None and context_year is None:
        # scenario tables have no year heading and some rows no data-sort-value:
        # take the year from the citation's publication date
        start, end = parse_date(d[0], dtext, default_year, pub_date.year)
        date_note = "year taken from citation date"
    if pub_date and end and abs((pub_date - end).days) > 180:
        # wrong year in data-sort-value / missing year: pick the year that puts the
        # fieldwork end 0-60 days before publication
        for y in (pub_date.year, pub_date.year - 1):
            try:
                cand = end.replace(year=y)
            except ValueError:
                continue
            if 0 <= (pub_date - cand).days <= 60:
                shift = y - end.year
                date_note = f"year corrected {end.year}->{y} from citation date {pub_date}"
                end = cand
                if start:
                    try:
                        start = start.replace(year=start.year + shift)
                    except ValueError:
                        pass
                break
    rec = {
        "fieldwork_text": dtext,
        "fieldwork_start": start.isoformat() if start else "",
        "fieldwork_end": end.isoformat() if end else "",
        "citation_date": pub_date.isoformat() if pub_date else "",
        "pollster_as_listed": pollster_raw,
        "pollster": POLLSTER_MAP.get(pollster_raw, pollster_raw),
        "publisher_as_listed": publisher_raw,
        "publisher": PUBLISHER_MAP.get(publisher_raw, publisher_raw),
        "sample_size": parse_int(cell_text(sc[0])) if sc else None,
        "margin_of_error": "",
        "others_raw": cell_text(oc[0]) if oc else "",
        "gov_raw": cell_text(gc[0]) if gc else "",
        "source_url": src_refs[0]["url"] if src_refs else "",
        "notes": " | ".join(dict.fromkeys(refs[i]["text"] for i in note_ids if i in refs and refs[i]["is_note"])),
        "date_note": date_note,
    }
    # release date: citation publication date when it is plausible (on/after fieldwork
    # end and within 10 days), else the fieldwork end date.
    rel, basis = end, "fieldwork_end"
    if pub_date and end and 0 <= (pub_date - end).days <= 10:
        rel, basis = pub_date, "citation_date"
    rec["release_date"] = rel.isoformat() if rel else ""
    rec["release_date_basis"] = basis
    results = []
    na = []
    seen_cells = set()
    for j, (cell, origin, st, span) in enumerate(line):
        if colrole[j] != "party" if j < len(colrole) else True:
            continue
        if id(cell) in seen_cells:
            continue
        seen_cells.add(id(cell))
        cols = [c for c in range(st, st + span) if c < len(labels) and colrole[c] == "party"]
        leafs = [labels[c][0] for c in cols]
        tops = {labels[c][1] for c in cols}
        top_span = {labels[c][2] for c in cols}
        if len(cols) > 1 and len(tops) == 1 and len(top_span) == 1 and next(iter(top_span))[1] == len(cols):
            as_listed = next(iter(tops))  # cell covers exactly one grouped header
            as_listed_key = "+".join(leafs)
        else:
            as_listed = "+".join(dict.fromkeys(leafs))
            as_listed_key = as_listed
        as_listed = norm_header(as_listed)
        text = cell_text(cell)
        v = parse_value(cell, text)
        if v is None:
            na.append(as_listed)
            continue
        if v["status"] in ("empty",):
            continue
        party = map_party(as_listed_key, as_listed)[0]
        results.append({
            "party_as_listed": as_listed,
            "alias_key": as_listed_key,
            "party": party,
            "seats": v["seats"],
            "vote_share_pct": v["pct"],
            "seats_without_threshold": v["nt"],
            "below_threshold": v["status"].startswith("below_threshold") or v["status"] == "dash",
            "cell_status": v["status"],
            "raw": text,
            "cell_notes": " | ".join(refs[i]["text"] for i in cell_notes(cell) if i in refs and refs[i]["is_note"]),
        })
    if not results or not any(r["cell_status"] in ("seats",) or r["vote_share_pct"] is not None
                              for r in results):
        return None  # no figures at all (e.g. a row of dashes)
    rec["_results"] = results
    rec["_na_parties"] = na
    return rec


def map_party(key: str, listed: str):
    """(normalised party, note) for a column label; joint cells map component-wise."""
    for k in (key, listed):
        if k in PARTY_MAP:
            return PARTY_MAP[k]
    if "+" in key:
        # build() joins column labels with a bare "+"; a "+" with spaces is part of a
        # single header label (e.g. "Bennett + Cohen", "Tov+ Haddad + Deri")
        comps = [c.strip() for c in re.split(r"(?<!\s)\+(?!\s)", key)]
        names = [PARTY_MAP.get(c, (c, ""))[0] for c in comps]
        return (" + ".join(dict.fromkeys(names)),
                "joint cell spanning the columns " + ", ".join(comps) + " (merger scenario / joint run)")
    return (listed, "unmapped: passed through unchanged")


def make_ids(polls):
    used = Counter()
    for p in polls:
        base = "_".join([
            p["release_date"] or "nodate",
            slug(p["publisher"].split(" (")[0]) or "unknown",
            slug(p["pollster_as_listed"]) or "unknown",
        ])
        if p["scenario"] != "standard":
            if p["scenario"].startswith("hypothetical"):
                base += "_scn-" + slug(p["scenario"].split(":", 1)[1].split(" (row")[0])[:40].strip("-")
            else:
                base += "_alt"
        used[base] += 1
        p["poll_id"] = f"{base}_{used[base]}"


def write_outputs(polls):
    OUT.mkdir(parents=True, exist_ok=True)
    poll_cols = ["poll_id", "release_date", "release_date_basis", "fieldwork_start", "fieldwork_end",
                 "fieldwork_text", "pollster", "pollster_as_listed", "publisher", "publisher_as_listed",
                 "sample_size", "margin_of_error", "scenario", "scenario_group", "coalition_seats",
                 "opposition_seats", "coalition_seats_computed", "seat_sum", "seat_sum_ok", "coalition_basis", "others_raw",
                 "source_url", "citation_date", "source_page", "source_page_revid", "section",
                 "source_order", "date_note", "notes"]
    res_cols = ["poll_id", "release_date", "pollster", "publisher", "scenario", "party", "party_as_listed",
                "seats", "vote_share_pct", "seats_without_threshold", "below_threshold", "cell_status",
                "raw", "cell_notes"]
    aliases = {}
    with open(OUT / "polls.csv", "w", newline="", encoding="utf-8") as f1, \
            open(OUT / "poll_results.csv", "w", newline="", encoding="utf-8") as f2:
        w1 = csv.DictWriter(f1, poll_cols, extrasaction="ignore")
        w2 = csv.DictWriter(f2, res_cols, extrasaction="ignore")
        w1.writeheader()
        w2.writeheader()
        for p in polls:
            for r in p["_results"]:
                w2.writerow({**r, "poll_id": p["poll_id"], "release_date": p["release_date"],
                             "pollster": p["pollster"], "publisher": p["publisher"], "scenario": p["scenario"],
                             "below_threshold": str(r["below_threshold"]).lower()})
                a = aliases.setdefault((r["party_as_listed"], r["party"]), {
                    "party_as_listed": r["party_as_listed"], "party": r["party"],
                    "columns_spanned": r["alias_key"],
                    "note": map_party(r["alias_key"], r["party_as_listed"])[1],
                    "n_rows": 0, "first_seen": p["fieldwork_end"], "last_seen": p["fieldwork_end"]})
                a["n_rows"] += 1
                if p["fieldwork_end"]:
                    a["first_seen"] = min(filter(None, [a["first_seen"], p["fieldwork_end"]]))
                    a["last_seen"] = max(filter(None, [a["last_seen"], p["fieldwork_end"]]))
            w1.writerow(p)
    with open(OUT / "party_aliases.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["party_as_listed", "party", "columns_spanned", "first_seen", "last_seen",
                               "n_rows", "note"])
        w.writeheader()
        for a in sorted(aliases.values(), key=lambda a: (a["party"], a["party_as_listed"])):
            w.writerow(a)
    return aliases


GOV_PARTIES = {"Likud", "Religious Zionist Party", "Otzma Yehudit", "Shas", "United Torah Judaism",
               "Religious Zionist Party + Zehut"}


def finalize(polls):
    for p in polls:
        p["coalition_seats_computed"] = sum(
            r["seats"] or 0 for r in p["_results"]
            if r["party"] in GOV_PARTIES or (" + " in r["party"] and all(
                c in GOV_PARTIES | {"Zehut"} for c in r["party"].split(" + ")) and "Zehut" != r["party"]))
        seats = [r["seats"] for r in p["_results"] if r["seats"] is not None]
        p["seat_sum"] = sum(seats)
        p["seat_sum_ok"] = p["seat_sum"] == 120
        gov = parse_int(p["gov_raw"]) if p["gov_raw"] else None
        if gov is not None:
            p["coalition_seats"] = gov
            p["opposition_seats"] = 120 - gov
            p["coalition_basis"] = ("coalition = Wikipedia 'Gov.' column (37th-government parties); "
                                    "opposition = 120 - coalition (computed)")
        else:
            p["coalition_seats"] = ""
            p["opposition_seats"] = ""
            p["coalition_basis"] = "no Gov. figure in source"


def sanity(polls, log, unparsed, aliases):
    print("== extraction log ==")
    for k, v in log.items():
        print(f"  {k}: {v}")
    std = [p for p in polls if p["scenario"] == "standard"]
    print(f"polls (all rows): {len(polls)}; standard: {len(std)}; "
          f"alt rows: {sum(p['scenario'].startswith('alternative') for p in polls)}; "
          f"hypothetical: {sum(p['scenario'].startswith('hypothetical') for p in polls)}")
    dates = sorted(p["release_date"] for p in polls if p["release_date"])
    print(f"release_date range: {dates[0]} .. {dates[-1]}; missing: {sum(not p['release_date'] for p in polls)}")
    print(f"pollsters: {len({p['pollster'] for p in std})}; publishers: {len({p['publisher'] for p in std})}")
    bad = [p for p in std if not p["seat_sum_ok"]]
    print(f"standard polls not summing to 120: {len(bad)}")
    for p in bad:
        st = Counter(r["cell_status"] for r in p["_results"])
        print(f"   {p['poll_id']}: sum={p['seat_sum']} statuses={dict(st)} raw_gov={p['gov_raw']}")
    gm = [p for p in std if p["coalition_seats"] != "" and p["coalition_seats"] != p["coalition_seats_computed"]]
    print(f"standard polls where Wikipedia Gov. != computed 37th-gov sum: {len(gm)}")
    for p in gm:
        print(f"   {p['poll_id']}: Gov.={p['coalition_seats']} computed={p['coalition_seats_computed']}")
    ids = Counter(p["poll_id"] for p in polls)
    print(f"duplicate poll_ids: {sum(v > 1 for v in ids.values())}")
    # monotonic (reverse-chronological) within each source table
    nonmono = 0
    by_table = defaultdict(list)
    for p in polls:
        by_table[(p["source_page"], p["source_table_index"])].append(p)
    for k, ps in by_table.items():
        ds = [p["fieldwork_end"] for p in sorted(ps, key=lambda p: p["source_order"]) if p["fieldwork_end"]]
        for a, b in zip(ds, ds[1:]):
            if b > a:
                nonmono += 1
                print(f"   non-monotonic in {k}: {a} then {b}")
    print(f"date order violations (expected reverse-chronological): {nonmono}")
    out_of_range = [p["poll_id"] for p in polls if p["fieldwork_end"] and not (
        ELECTION_2022.isoformat() <= p["fieldwork_end"] <= TODAY.isoformat())]
    print(f"fieldwork_end outside 2022-11-01..{TODAY}: {len(out_of_range)} {out_of_range[:5]}")
    print(f"unparsed cells: {len(unparsed)} {unparsed[:10]}")
    print("date notes:", [(p["poll_id"], p["date_note"]) for p in polls if p["date_note"]])
    um = [a for a in aliases.values() if a["note"].startswith("unmapped")]
    print(f"unmapped party labels: {len(um)}: {[a['party_as_listed'] for a in um]}")
    print("unmapped pollsters:", sorted({p["pollster"] for p in polls if p["pollster"] not in POLLSTER_MAP.values()}))
    print("unmapped publishers:", sorted({p["publisher"] for p in polls if p["publisher"] not in PUBLISHER_MAP.values()}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    polls, log, unparsed, page_meta = extract(a.raw_dir, a.refresh)
    finalize(polls)
    make_ids(polls)
    aliases = write_outputs(polls)
    print("pages:", page_meta)
    sanity(polls, log, unparsed, aliases)


if __name__ == "__main__":
    main()
