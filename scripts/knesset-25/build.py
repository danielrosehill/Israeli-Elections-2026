"""Build the outgoing (25th) Knesset members and factions dataset.

Usage (from the repo root):
    uv run --with lxml python3 -I scripts/knesset-25/build.py --raw <raw_dir> [--fetch]

--fetch downloads every source into <raw_dir> first; without it the script
rebuilds from the files already there. Outputs go to data/knesset-25/.

Sources and join chain (see data/knesset-25/SOURCES.md):
  Knesset OData (authoritative: people, MK terms, faction membership, gender)
    KNS_Person.PersonID -> KNS_MkSiteCode.SiteId
  Wikidata P9770 "Knesset member ID" == SiteId  -> English label, en/he wiki titles
  en.wikipedia "Party lists for the 2022 Israeli legislative election" -> list + position
  he.wikipedia "הכנסת העשרים וחמש" replacements table -> reason for leaving
  en.wikipedia "List of members of the twenty-fifth Knesset" -> faction leaders, bloc
"""
import argparse, csv, datetime, difflib, json, pathlib, re, sys, time, unicodedata
import urllib.parse, urllib.request
from collections import defaultdict

import lxml.html

ODATA = "https://knesset.gov.il/Odata/ParliamentInfo.svc/"
SITE_API = "https://knesset.gov.il/WebSiteApi/knessetapi/MKs/GetMkdetailsHeader"
UA = "Israeli-Elections-2026-dataset/1.0 (https://github.com/danielrosehill)"
EN_LIST = "List_of_members_of_the_twenty-fifth_Knesset"
EN_PARTYLISTS = "Party_lists_for_the_2022_Israeli_legislative_election"
HE_K25 = "הכנסת_העשרים_וחמש"
REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "knesset-25"

MK_POSITIONS = {43: "male", 61: "female"}  # KNS_Position: חבר הכנסת / חברת הכנסת
FACTION_MEMBER = 54                          # KNS_Position: חבר/ת סיעה

# KNS_Faction.FactionID -> (English name, notes). Hebrew name comes from OData.
FACTIONS = {
    1096: ("Likud", ""),
    1102: ("Yesh Atid", ""),
    1097: ("Religious Zionism (joint faction)",
           "Joint RZP-Otzma Yehudit-Noam faction; split into three factions on 2022-11-20."),
    1105: ("Religious Zionist Party", "Split from the joint Religious Zionism faction 2022-11-20."),
    1106: ("Otzma Yehudit", "Separate faction from 2022-11-15/20 (split from joint Religious Zionism list)."),
    1107: ("Noam", "Split from the joint Religious Zionism faction 2022-11-20."),
    1098: ("National Unity", "Original National Unity faction; renamed Blue and White - National Unity 2025-07-08 "
           "after Eisenkot's departure. New Hope split off 2024-03-13."),
    1110: ("Blue and White - National Unity", "Successor of the National Unity faction from 2025-07-08."),
    1108: ("New Hope (HaYamin HaMamlachti)", "Gideon Sa'ar's New Hope; registered in the Knesset as "
           "'HaYamin HaMamlachti' (The National Right); split from National Unity 2024-03-13."),
    1095: ("Shas", ""),
    1101: ("United Torah Judaism", "Agudat Yisrael and Degel HaTorah sit as one faction."),
    1104: ("Yisrael Beiteinu", ""),
    1099: ("United Arab List (Ra'am)", ""),
    1103: ("Hadash-Ta'al", ""),
    1100: ("Labor", "Labor merged with Meretz into The Democrats (2024) outside the Knesset; "
           "the Knesset faction kept the name HaAvoda."),
    1109: ("Idan Roll (single-member faction)", "Idan Roll split from Yesh Atid 2025-01-14; resigned 2025-08-13."),
}

# 2022 electoral lists as titled on the en.wikipedia party-lists page -> our label and seats won.
LISTS_2022 = {
    "Likud": ("Likud", 32),
    "Yesh Atid": ("Yesh Atid", 24),
    "Religious Zionist Party": ("Religious Zionism (RZP-Otzma Yehudit-Noam)", 14),
    "National Unity Party": ("National Unity", 12),
    "Shas": ("Shas", 11),
    "United Torah Judaism": ("United Torah Judaism", 7),
    "Yisrael Beiteinu": ("Yisrael Beiteinu", 6),
    "United Arab List": ("United Arab List (Ra'am)", 5),
    "Hadash–Ta'al": ("Hadash-Ta'al", 5),
    "Labor": ("Labor", 4),
}

# Faction -> 2022 list it descends from.
FACTION_LIST = {1096: "Likud", 1102: "Yesh Atid", 1097: "Religious Zionist Party",
                1105: "Religious Zionist Party", 1106: "Religious Zionist Party",
                1107: "Religious Zionist Party", 1098: "National Unity Party",
                1110: "National Unity Party", 1108: "National Unity Party", 1095: "Shas",
                1101: "United Torah Judaism", 1104: "Yisrael Beiteinu", 1099: "United Arab List",
                1103: "Hadash–Ta'al", 1100: "Labor", 1109: "Yesh Atid"}

# en.wikipedia composition-table faction label -> FactionID (for leader + bloc).
EN_COMPOSITION = {"Likud": 1096, "Yesh Atid": 1102, "Shas": 1095,
                  "Blue and White - National Unity": 1110, "Otzma Yehudit": 1106,
                  "United Torah Judaism": 1101, "Religious Zionist Party": 1105,
                  "Yisrael Beiteinu": 1104, "United Arab List": 1099, "Hadash–Ta'al": 1103,
                  "Labor": 1100, "New Hope": 1108, "Noam": 1107}

# PersonID -> English name as written on the en.wikipedia party-lists page, for names the
# fuzzy matcher cannot bridge (Knesset site transliterates יצחק as "Issac"; no Wikidata P9770 yet).
LISTPOS_OVERRIDES = {30847: "Yitzhak Wasserlauf"}

# Hebrew reason text (he.wikipedia replacements table) -> English category. First match wins.
REASONS = [
    ("חזרה לכנסת במסגרת החוק הנורווגי", "Norwegian law (minister returned to Knesset)"),
    ("החוק הנורווגי", "Norwegian law (became minister/deputy minister)"),
    ("רוטציה", "resigned (rotation agreement)"),
    ("שגריר", "resigned (appointed ambassador)"),
    ("עיריית", "resigned (ran for mayor)"),
    ("מעבר למפלגה אחרת", "resigned (joined another party)"),
    ("פרישה", "retired from politics"),
    ("התפטרות", "resigned"),
]


# ---------------------------------------------------------------- fetching
def http_json(url, data=None, headers=None):
    h = {"User-Agent": UA, **(headers or {})}
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3)


def odata_all(query):
    url, rows = ODATA + query, []
    while url:
        sep = "&" if "?" in url else "?"
        d = http_json(url if "format=json" in url else url + sep + "$format=json")
        rows.extend(d["value"])
        nxt = d.get("odata.nextLink")  # server pages at 100 rows
        url = ODATA + nxt if nxt else None
    return rows


def fetch(raw):
    (raw / "odata").mkdir(parents=True, exist_ok=True)
    (raw / "wiki").mkdir(exist_ok=True)
    (raw / "wikidata").mkdir(exist_ok=True)
    od = {
        "KNS_Faction": odata_all("KNS_Faction()?$filter=KnessetNum%20eq%2025"),
        "KNS_PersonToPosition": odata_all("KNS_PersonToPosition()?$filter=KnessetNum%20eq%2025"),
        "KNS_Position": odata_all("KNS_Position()"),
    }
    pids = sorted({r["PersonID"] for r in od["KNS_PersonToPosition"]})
    od["KNS_Person"], od["KNS_MkSiteCode"] = [], []
    for i in range(0, len(pids), 20):
        chunk = pids[i:i + 20]
        od["KNS_Person"] += odata_all("KNS_Person()?$filter=" + "%20or%20".join(
            f"PersonID%20eq%20{p}" for p in chunk))
        od["KNS_MkSiteCode"] += odata_all("KNS_MkSiteCode()?$filter=" + "%20or%20".join(
            f"KnsID%20eq%20{p}" for p in chunk))
    (raw / "knesset_api").mkdir(exist_ok=True)
    for r in od["KNS_MkSiteCode"]:
        for lang in ("en", "he"):
            d = http_json(f"{SITE_API}?mkId={r['SiteId']}&languageKey={lang}")
            (raw / "knesset_api" / f"{r['SiteId']}_{lang}.json").write_text(
                json.dumps(d, ensure_ascii=False), "utf-8")
    print(f"knesset site API headers: {len(od['KNS_MkSiteCode'])} MKs x en/he")
    for k, v in od.items():
        (raw / "odata" / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), "utf-8")
        print(f"odata {k}: {len(v)} rows")
    for name, host, page in [("en_list", "en", EN_LIST), ("en_partylists", "en", EN_PARTYLISTS),
                             ("he_k25", "he", HE_K25)]:
        url = (f"https://{host}.wikipedia.org/w/api.php?action=parse&format=json&formatversion=2"
               f"&prop=text|revid&redirects=1&page=" + urllib.parse.quote(page))
        d = http_json(url)
        (raw / "wiki" / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False), "utf-8")
        print(f"wiki {name}: revid {d['parse']['revid']}")
    q = """SELECT ?item ?kid ?en ?he ?enwiki ?hewiki WHERE { ?item wdt:P9770 ?kid .
      OPTIONAL{?item rdfs:label ?en FILTER(lang(?en)="en")}
      OPTIONAL{?item rdfs:label ?he FILTER(lang(?he)="he")}
      OPTIONAL{?enwiki schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>}
      OPTIONAL{?hewiki schema:about ?item; schema:isPartOf <https://he.wikipedia.org/>} }"""
    d = http_json("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q}),
                  headers={"Accept": "application/sparql-results+json"})
    (raw / "wikidata" / "p9770.json").write_text(json.dumps(d, ensure_ascii=False), "utf-8")
    print(f"wikidata P9770 rows: {len(d['results']['bindings'])}")


# ---------------------------------------------------------------- helpers
def load(raw, rel):
    return json.loads((raw / rel).read_text("utf-8"))


def wiki_doc(raw, name):
    return lxml.html.fromstring(load(raw, f"wiki/{name}.json")["parse"]["text"])


def title_of(href):
    if not href or not href.startswith("/wiki/"):
        return None
    return urllib.parse.unquote(href[6:]).replace("_", " ").split("#")[0]


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9א-ת]", "", s.replace("’", "'"))


def d10(s):
    return s[:10] if s else ""


def grid(table):
    """Expand a wikitable with rowspan/colspan into a list of rows of <td>/<th> elements."""
    out, carry = [], {}
    for tr in table.xpath(".//tr"):
        row, col = [], 0
        cells = list(tr.xpath("./th|./td"))
        while cells or col in carry:
            if col in carry:
                el, left = carry[col]
                row.append(el)
                carry[col] = (el, left - 1)
                if left - 1 == 0:
                    del carry[col]
                col += 1
                continue
            el = cells.pop(0)
            span = int(el.get("colspan", 1) or 1)
            rs = int(el.get("rowspan", 1) or 1)
            for _ in range(span):
                row.append(el)
                if rs > 1:
                    carry[col] = (el, rs - 1)
                col += 1
        out.append(row)
    return out


# ---------------------------------------------------------------- build
HE_MONTHS = {"בינואר": 1, "בפברואר": 2, "במרץ": 3, "באפריל": 4, "במאי": 5, "ביוני": 6,
             "ביולי": 7, "באוגוסט": 8, "בספטמבר": 9, "באוקטובר": 10, "בנובמבר": 11, "בדצמבר": 12}


def he_date(s):
    m = re.match(r"(\d{1,2}) (\S+) (\d{4})", s.strip())
    if not m or m.group(2) not in HE_MONTHS:
        return None
    return datetime.date(int(m.group(3)), HE_MONTHS[m.group(2)], int(m.group(1)))


def strip_paren(t):
    return re.sub(r"\s*\(.*?\)\s*", "", t or "").strip()


def score(a, b):
    """Name similarity: full-string ratio, a token-subset bonus (middle names), and a
    surname-weighted ratio (transliteration variants such as Buaron/Boaron)."""
    ta = [norm(x) for x in re.split(r"[\s\-]+", a or "") if norm(x)]
    tb = [norm(x) for x in re.split(r"[\s\-]+", b or "") if norm(x)]
    if not ta or not tb:
        return 0.0
    r = lambda x, y: difflib.SequenceMatcher(None, x, y).ratio()
    full = r("".join(ta), "".join(tb))
    subset = 0.95 if len(ta) > 1 and len(tb) > 1 and (set(ta) <= set(tb) or set(tb) <= set(ta)) else 0.0
    surname = 0.5 * r(ta[-1], tb[-1]) + 0.3 * r(ta[0][:3], tb[0][:3]) + 0.2 * (r(ta[-1], tb[-1]) > 0.8)
    return max(full, subset, surname * 0.95)


def best_match(name, title, pool, variants, titles):
    """Return (pid, score) of the best match for a wiki name/link among pids in pool."""
    if title:
        for pid in pool:
            if title in titles.get(pid, ()):
                return pid, 1.0
    best = (None, 0.0)
    for pid in pool:
        sc = max((score(name, v) for v in variants.get(pid, ()) if v), default=0.0)
        if title:
            sc = max([sc] + [score(strip_paren(title), v) for v in variants.get(pid, ()) if v])
        if sc > best[1]:
            best = (pid, sc)
    return best


def build(raw):
    person = {p["PersonID"]: p for p in load(raw, "odata/KNS_Person.json")}
    site = {r["KnsID"]: r["SiteId"] for r in load(raw, "odata/KNS_MkSiteCode.json")}
    fac_he = {f["FactionID"]: f["Name"].strip() for f in load(raw, "odata/KNS_Faction.json")}
    ptp = load(raw, "odata/KNS_PersonToPosition.json")
    api = {}
    for f in (raw / "knesset_api").glob("*.json"):
        sid, lang = f.stem.split("_")
        api[(int(sid), lang)] = json.loads(f.read_text("utf-8"))

    wd = {}
    for b in load(raw, "wikidata/p9770.json")["results"]["bindings"]:
        g = lambda k: b.get(k, {}).get("value", "")
        t = lambda k: urllib.parse.unquote(g(k).rsplit("/wiki/", 1)[-1]).replace("_", " ") if g(k) else ""
        wd[int(g("kid"))] = {"en": g("en"), "he": g("he"), "enwiki": t("enwiki"), "hewiki": t("hewiki")}

    # MK terms (a person can have several: Norwegian-law exits and returns)
    terms, factions = defaultdict(list), defaultdict(list)
    for r in ptp:
        if r["PositionID"] in MK_POSITIONS:
            terms[r["PersonID"]].append((d10(r["StartDate"]), d10(r["FinishDate"])))
        elif r["PositionID"] == FACTION_MEMBER:
            factions[r["PersonID"]].append((d10(r["StartDate"]), d10(r["FinishDate"]), r["FactionID"]))
    # open-ended rows sort last, so the last row is the current/final faction even when a
    # rename closes one row and opens another on the same day (1098 -> 1110 on 2025-07-08)
    for v in list(terms.values()) + list(factions.values()):
        v.sort(key=lambda t: (t[0], t[1] or "9999"))
    mks = sorted(terms)

    def name_en(pid):
        return (api.get((site.get(pid), "en"), {}).get("Name") or wd.get(site.get(pid), {}).get("en") or "").strip()

    def name_he(pid):
        return (api.get((site.get(pid), "he"), {}).get("Name") or
                f"{person[pid]['FirstName'].strip()} {person[pid]['LastName'].strip()}").strip()

    var_en, var_he, tit_en, tit_he = {}, {}, {}, {}
    for pid in mks:
        w = wd.get(site.get(pid), {})
        var_en[pid] = [name_en(pid), w.get("en", ""), strip_paren(w.get("enwiki", ""))]
        var_he[pid] = [name_he(pid), f"{person[pid]['FirstName'].strip()} {person[pid]['LastName'].strip()}",
                       w.get("he", ""), strip_paren(w.get("hewiki", ""))]
        tit_en[pid] = {w["enwiki"]} if w.get("enwiki") else set()
        tit_he[pid] = {w["hewiki"]} if w.get("hewiki") else set()

    # 2022 party lists (en.wikipedia), in list order
    listpos, heading = {}, None
    for el in wiki_doc(raw, "en_partylists"):
        cls = el.get("class") or ""
        if "mw-heading" in cls:
            heading = el.text_content().replace("[edit]", "").strip()
        elif heading in LISTS_2022 and el.tag == "div" and "div-col" in cls:
            for pos, li in enumerate(el.xpath(".//li"), 1):
                a = li.xpath("./a")
                listpos.setdefault(heading, []).append(
                    (pos, li.text_content().split("[")[0].strip(), title_of(a[0].get("href")) if a else None))
            heading = None
    pos_of = {}
    for pid, wiki_name in LISTPOS_OVERRIDES.items():  # names fuzzy matching cannot bridge
        var_en.setdefault(pid, []).append(wiki_name)
    for pid in mks:
        lst = FACTION_LIST[factions[pid][0][2]] if factions.get(pid) else None
        best = (None, 0.0, None)
        for pos, nm, t in listpos.get(lst, []):
            _, sc = best_match(nm, t, [pid], var_en, tit_en)
            if sc > best[1]:
                best = (pos, sc, nm)
        if best[1] >= 0.8:
            pos_of[pid] = (lst, best[0], best[2], best[1])

    # Departures (he.wikipedia replacements table); rows are expanded for rowspans
    rep_table = next(t for t in wiki_doc(raw, "he_k25").xpath("//table[contains(@class,'wikitable')]")
                     if "חבר הכנסת היוצא" in t.xpath("string(.//tr[1])"))
    events = []
    for row in grid(rep_table)[1:]:
        if len(row) < 6:
            continue
        def who(cell):
            a = cell.xpath(".//a")
            pid, sc = best_match(cell.text_content().strip(), title_of(a[0].get("href")) if a else None,
                                 mks, var_he, tit_he)
            return pid if sc >= 0.75 else None
        reason_he = row[4].text_content().strip()
        events.append({"date": he_date(row[0].text_content()), "out": who(row[3]), "in": who(row[5]),
                       "reason_he": reason_he,
                       "reason": next((en for k, en in REASONS if k in reason_he), reason_he),
                       "raw": [c.text_content().strip() for c in row]})

    def common_en(pid):
        """Common English spelling: en.wikipedia party-list name, else Wikidata label, else Knesset site."""
        if pid in pos_of:
            return pos_of[pid][2].replace("’", "'")
        return wd.get(site.get(pid), {}).get("en") or name_en(pid)

    members = []
    for pid in mks:
        tlist, flist = terms[pid], factions.get(pid, [])
        serving = any(not f for _, f in tlist)
        end = "" if serving else max(f for _, f in tlist)
        last_fac = flist[-1][2] if flist else None
        lst = pos_of.get(pid)
        list_name = LISTS_2022[lst[0]][0] if lst else (LISTS_2022[FACTION_LIST[flist[0][2]]][0] if flist else "")
        notes = []
        if len(tlist) > 1:
            notes.append("MK terms: " + "; ".join(f"{s} to {f or 'end'}" for s, f in tlist))
        seq = []
        for _, _, fid in flist:
            nm = FACTIONS[fid][0]
            if not seq or seq[-1] != nm:
                seq.append(nm)
        if len(seq) > 1:
            notes.append("factions: " + " -> ".join(seq))
        if not lst:
            notes.append("2022 list position not matched")
        if name_en(pid) and norm(name_en(pid)) != norm(common_en(pid)):
            notes.append(f"Knesset site English name: {re.sub(' +', ' ', name_en(pid))}")
        reason = repl = ""
        if not serving:
            ed = datetime.date.fromisoformat(end)
            evs = [e for e in events if e["out"] == pid and e["date"]]
            if evs:
                e = min(evs, key=lambda e: abs((e["date"] - ed).days))
                if abs((e["date"] - ed).days) <= 5:
                    reason = e["reason"]
                    repl = common_en(e["in"]) if e["in"] else ""
            if not repl:  # same-list MK whose term starts within 2 days of this exit
                cands = [q for q in mks if q != pid and factions.get(q) and last_fac and
                         FACTION_LIST[factions[q][0][2]] == FACTION_LIST[last_fac] and
                         any(abs((datetime.date.fromisoformat(s) - ed).days) <= 2 for s, _ in terms[q])]
                if len(cands) == 1:
                    repl = common_en(cands[0])
                    notes.append("replaced_by inferred from OData term dates")
            if not reason:
                notes.append("reason_left not found on he.wikipedia")
        members.append({
            "member_id": pid, "name_en": common_en(pid), "name_he": name_he(pid),
            "list_elected_on": list_name, "list_position_2022": lst[1] if lst else "",
            "faction_at_end": FACTIONS[last_fac][0] if last_fac else "",
            "start_date": tlist[0][0], "end_date": end,
            "serving_at_end": "true" if serving else "false",
            "reason_left": reason, "replaced_by": repl,
            "gender": {"זכר": "male", "נקבה": "female"}.get(person[pid]["GenderDesc"], ""),
            "notes": "; ".join(notes),
            "source_url": f"https://main.knesset.gov.il/en/MK/APPS/mk/mk-personal-details/{site[pid]}"
                          if pid in site else f"{ODATA}KNS_Person({pid})",
            "_fac": last_fac, "_score": lst[3] if lst else 0, "_wikiname": lst[2] if lst else "",
        })
    members.sort(key=lambda m: (m["list_elected_on"], m["list_position_2022"] or 999, m["name_en"]))

    # Parties / factions
    comp = wiki_doc(raw, "en_list").xpath("//table[contains(@class,'wikitable')]")[0]
    leaders = {}
    for row in grid(comp)[1:]:
        texts = [c.text_content().strip() for c in row]
        if len(texts) < 7 or texts[1] not in EN_COMPOSITION:
            continue
        links = row[4].xpath(".//a")
        lead = links[-1].text_content().strip() if links else texts[4]
        prev = [a.text_content().strip() for a in links[:-1]]
        lpid, sc = best_match(lead, title_of(links[-1].get("href")) if links else None, mks, var_en, tit_en)
        leaders[EN_COMPOSITION[texts[1]]] = (lead, name_he(lpid) if sc >= 0.85 else "", texts[6], prev)
    seats_end = defaultdict(int)
    for m in members:
        if m["serving_at_end"] == "true":
            seats_end[m["_fac"]] += 1
    parties, won_done = [], set()
    for fid in [1096, 1102, 1097, 1105, 1106, 1107, 1098, 1110, 1108, 1095, 1101, 1104, 1099, 1103, 1100, 1109]:
        lst = FACTION_LIST[fid]
        label, won = LISTS_2022[lst]
        lead_en, lead_he, status, prev = leaders.get(fid, ("", "", "", []))
        notes = FACTIONS[fid][1]
        if prev:
            notes = (notes + " " if notes else "") + "Earlier Knesset leader(s): " + ", ".join(prev) + "."
        seats_won = ""
        if lst not in won_done and fid not in (1105, 1106, 1107, 1110, 1108, 1109):
            seats_won, _ = won, won_done.add(lst)
            if fid in (1097, 1098):
                notes += f" seats_won_2022 counts the whole {label} list."
        bloc = {"Governing coalition": "coalition", "Opposition": "opposition",
                "Unaffiliated": "unaffiliated (votes with coalition)"}.get(status, status)
        parties.append({
            "faction_en": FACTIONS[fid][0], "faction_he": fac_he.get(fid, ""),
            "list_elected_on_2022": label, "seats_won_2022": seats_won, "seats_at_end": seats_end[fid],
            "leader_en": lead_en, "leader_he": lead_he,
            "bloc_at_end": bloc if seats_end[fid] else "defunct", "notes": notes.strip(),
            "source_url": f"{ODATA}KNS_Faction({fid}) ; https://en.wikipedia.org/wiki/{EN_LIST}",
        })

    OUT.mkdir(parents=True, exist_ok=True)
    mcols = ["member_id", "name_en", "name_he", "list_elected_on", "list_position_2022", "faction_at_end",
             "start_date", "end_date", "serving_at_end", "reason_left", "replaced_by", "gender", "notes",
             "source_url"]
    with open(OUT / "members.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, mcols, extrasaction="ignore")
        w.writeheader()
        w.writerows(members)
    pcols = ["faction_en", "faction_he", "list_elected_on_2022", "seats_won_2022", "seats_at_end",
             "leader_en", "leader_he", "bloc_at_end", "notes", "source_url"]
    with open(OUT / "parties.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, pcols)
        w.writeheader()
        w.writerows(parties)

    # ---- sanity checks
    serving = sum(m["serving_at_end"] == "true" for m in members)
    print(f"members rows: {len(members)}; serving_at_end: {serving}; "
          f"original (start 2022-11-15): {sum(m['start_date'] == '2022-11-15' for m in members)}")
    print(f"parties rows: {len(parties)}; sum seats_at_end: {sum(p['seats_at_end'] for p in parties)}; "
          f"sum seats_won_2022: {sum(p['seats_won_2022'] or 0 for p in parties)}")
    for lst, (_, won) in LISTS_2022.items():
        orig = [m for m in members if m["start_date"] == "2022-11-15" and pos_of.get(m["member_id"], ("",))[0] == lst]
        bad = [m["name_en"] for m in orig if m["list_position_2022"] > won]
        print(f"  {lst}: {len(orig)} original MKs matched (won {won}); position>won: {bad}")
    seen = defaultdict(list)
    for m in members:
        if m["list_position_2022"]:
            seen[(m["list_elected_on"], m["list_position_2022"])].append(m["name_en"])
    print("  duplicate list positions:", {k: v for k, v in seen.items() if len(v) > 1})
    for m in members:
        if m["_score"] < 0.95:
            print(f"  fuzzy list match {m['_score']:.2f}: {m['name_en']} ~ {m['_wikiname']}")
        if m["serving_at_end"] == "false" and (not m["reason_left"] or not m["replaced_by"]):
            print("  GAP", m["member_id"], m["name_en"], "| reason", m["reason_left"], "| repl", m["replaced_by"])
    unmatched = [e["raw"] for e in events if not e["out"] or not e["in"]]
    print(f"  he.wikipedia replacement rows: {len(events)}; unmatched: {unmatched}")
    return members, parties


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, type=pathlib.Path)
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()
    if a.fetch:
        fetch(a.raw)
    build(a.raw)


if __name__ == "__main__":
    main()
