"""Build the 2026 (26th Knesset) candidate-list dataset.

Run from the repo root:
    uv run --with pandas --with lxml python3 -I scripts/candidate-lists/build.py

Inputs (all under data/candidate-lists/raw/):
  cec/*.txt         Snapshot of the Central Elections Committee (CEC) list pages on
                    gov.il, captured 2026-10-22 through a real Chrome session (gov.il
                    sits behind a Cloudflare JS challenge; curl/WebFetch get HTTP 403).
                    One file per list; `_index.txt` maps ballot letters -> page slug.
                    Line format: `<pos>|<name as printed, surname first>|<component code>`
                    with `COMP <code>=<registered party>` headers. shas_list19.txt keeps
                    the page's raw "1. name 2. name 3. name" rows; both forms are parsed.
                    `_browser_fnv1a_hashes.txt` holds FNV-1a hashes computed in the
                    browser over "pos|name" lines; this script re-checks them so a
                    transcription error fails the build.
  wikipedia/*.json  MediaWiki `action=parse` output, pinned by revision id (fetched on
                    first run with curl-equivalent urllib, then reused). Used only for
                    English names (top slots), and for the incumbent-MK flag.

Outputs: data/candidate-lists/candidates.csv, data/candidate-lists/parties.csv
"""
from __future__ import annotations

import difflib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
from lxml import html as lhtml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "candidate-lists"
RAW = OUT / "raw"
CEC = RAW / "cec"
WIKI = RAW / "wikipedia"
AS_OF = "2026-10-22"
CEC_BASE = "https://www.gov.il/he/pages/"
UA = "Israeli-Elections-2026-research/1.0 (daniel@danielrosehill.co.il)"

# Wikipedia pages, pinned to the revision read on 2026-10-22.
WIKI_PAGES = {
    "en_party_lists": ("en", "Party_lists_for_the_2026_Israeli_legislative_election", 1380861115),
    "en_mk25": ("en", "List_of_members_of_the_twenty-fifth_Knesset", 1381139795),
    "he_k25": ("he", "הכנסת_העשרים_וחמש", 44096838),
}

# ---------------------------------------------------------------- curated mappings
# slug -> (party_en, en-Wikipedia section id on the party-lists page or None)
PARTY_EN = {
    "hademokratim_list17": ("The Democrats", "The_Democrats"),
    "yehudit-meuhedet_list14": ("Otzma Yehudit", "Otzma_Yehudit"),
    "beyachad-natzliah_list10": ("Together We Will Succeed (Beyachad Natzliach)", "Beyachad_Natzliach"),
    "tzomet-beit-israel_list33": ("Tzomet – Beit Yisrael", "Tzomet_-_Beit_Yisrael"),
    "orot_list26": ("Dawn's Light (Orot HaShahar)", "Orot_HaShahar"),
    "yahadut-degel_list37": ("United Torah Judaism", "United_Torah_Judaism"),
    "hashutafut-lekulam_iist": ("Partnership for Everyone (Ihud Bnei HaBrit)", "Ihud_Bnei_HaBrit"),
    "hamiluimnikim-vehakalkalit_list16": ("The Reservists and the Economic Party", "The_Reservists_and_the_Economic_Party"),
    "yashar_list_2": ("Yashar", "Yashar"),
    "gan-eden_list_8": ("Garden of Eden (Paradise)", "Paradise"),
    "hareshima-hameshutefet_list35": ("Joint List", "Joint_List"),
    "betach_list25": ("Betach – Social Security", "Betach"),
    "tzibur-charedi_list20": ("Haredi Public", "Haredi_Public"),
    "brit-olam_list22": ("Eternal Covenant (Brit Olam)", "Brit_Olam"),
    "tzionutdatit-zehut_list31": ("Religious Zionist Party – Zehut", "Religious_Zionist_Party-Zehut"),
    "israel-tchila_list7": ("Israel First", "Israel_First"),
    "gush-tanachi_list24": ("The Bible Bloc", "Bible_Bloc"),
    "amcha-israel_list6": ("Amcha Yisrael", "Amcha_Yisrael"),
    "kachol-lavan_list30": ("Blue and White", "Blue_and_White"),
    "israel-beitenu_list11": ("Yisrael Beiteinu", "Yisrael_Beiteinu"),
    "halikud-tikvahadasha_iist29": ("Likud", "Likud"),
    "noam_list38": ("Noam", "Noam"),
    "shama": ("Shema", "Shma"),
    "demokratura_list27": ("Personal Security (Democtatorship)", "Democtatorship"),
    "tikun_list23": ("Fixing the Electoral and Governing System (HaTikun)", "HaTikun"),
    "shachor_list28": ("The Color Black – Guarding the World of Torah", "The_Color_Black"),
    "raam_list18": ("United Arab List (Ra'am)", "United_Arab_List"),
    "miflegat-am-israelit_list21": ("You and I (Ani VeAta)", "You_and_I"),
    "chozrim-leshorashim_list32": ("Ahi Movement", "Ahi"),
    "sharshar_list3": ("Sharshar for Love and Unity of the People", "Sharshar"),
    "pirates_list_5": ("Pirate Party", "Pirate_Party"),
    "tekuma_list34": ("Tkuma (Derech Hazon VeTkuma)", "Tkuma"),
    "kol-ha-nashim_list9": ("Women's Voice", "Women's_Voice"),
    "seder-chadash_list15": ("New Order", "New_Order"),
    "mishpat-tzedek_list12": ("Just Law (Mishpat Tzedek)", "Mishpat_Tzedek"),
    "machane-israel_list36": ("Hakahal", "Hakahal"),
    "beyahad_list1": ("Together (B'Yachad)", "Together"),
    "shas_list19": ("Shas", "Shas"),
}

# Registered party names as printed by the CEC ("מטעם מפלגת ...") -> English short name.
# Only used for joint lists (>1 component). Names marked (translit.) have no
# established English name; they are transliterations.
COMPONENT_EN = {
    "הליכוד, תנועה לאומית ליברלית": "Likud",
    "תקווה חדשה הימין הממלכתי": "New Hope – The National Right",
    "ביחד בראשות בנט מחזירים את התקווה": "Bennett 2026",
    "יש עתיד - בראשות יאיר לפיד": "Yesh Atid",
    "הדמוקרטים מיסודה של תנועת העבודה": "The Democrats",
    "מרצ": "Meretz",
    "חזית יהודית לאומית": "Otzma Yehudit (registered as Jewish National Front)",
    "ארץ ישראל שלנו - מפלגה יהודית מאוחדת לשלמות התורה העם והארץ": "Eretz Yisrael Shelanu (translit.)",
    "אגודת החרדים - דגל התורה": "Degel HaTorah",
    "הסתדרות אגודת ישראל בארץ ישראל": "Agudat Yisrael",
    "חומת תורת ישראל": "Homat Torat Yisrael",
    "האיחוד הלאומי - תקומה": "Religious Zionist Party (registered as National Union–Tkuma)",
    "זהות- תנועה ישראלית יהודית": "Zehut",
    "עתיד אחד - עתיד טוב לישראל": "Atid Ehad (translit.)",
    "המפלגה הקומוניסטית הישראלית": "Hadash (Maki)",
    "התנועה הערבית להתחדשות": "Ta'al",
    "אלתג'מוע אלווטני אלדמוקרטי": "Balad",
    "אלתג'מוע אללאומי אלדמוקרטי": "Balad",  # one CEC row spells it this way (pos 110)
    "ישר לישראל עם איזנקוט": "Yashar",
    "יסודות ישראל": "Yesodot Yisrael",
    "המילואימניקים": "The Reservists",
    "הכלכלית החדשה": "New Economic Party",
    "לזוז": "Lazuz (translit.; Avi Maoz's vehicle)",
    "אחריות לאומית - למען עתיד ילדינו": "National Responsibility (translit.)",
    "צומת - התנועה לציונות מתחדשת": "Tzomet",
    "בית ימני חברתי ציוני לכלל עם ישראל": "Beit Yisrael (registered as Beit Yamini Hevrati Tzioni)",
}

# Lists the CEC records as approved on 27.9.2026 but with a later status event.
STATUS_NOTES = {
    "raam_list18": "CEC barred the list on 24.9.2026 (s.7A); Supreme Court reversed on 2.10.2026; list running.",
    "hareshima-hameshutefet_list35": "CEC barred the list (and Cassif, Abu Shehadeh) on 24.9.2026; Supreme Court reversed for the list and Cassif on 2.10.2026; Abu Shehadeh resigned 2.10.2026.",
    "kachol-lavan_list30": "All candidates resigned 20-21.10.2026; CEC: the list is not contesting the 26th Knesset election (ballot letters כן).",
}

WIKI_EN_URL = "https://en.wikipedia.org/wiki/Party_lists_for_the_2026_Israeli_legislative_election"


# ---------------------------------------------------------------- fetch helpers
def wiki(key: str) -> dict:
    lang, page, oldid = WIKI_PAGES[key]
    path = WIKI / f"{key}_{oldid}.json"
    if not path.exists():
        WIKI.mkdir(parents=True, exist_ok=True)
        q = urllib.parse.urlencode({"action": "parse", "oldid": oldid, "prop": "text|revid",
                                    "format": "json", "formatversion": 2})
        req = urllib.request.Request(f"https://{lang}.wikipedia.org/w/api.php?{q}", headers={"User-Agent": UA})
        path.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    d = json.loads(path.read_text(encoding="utf-8"))
    if "parse" not in d:
        sys.exit(f"wikipedia fetch failed for {key}: {d.get('error')}")
    return d["parse"]


# ---------------------------------------------------------------- CEC parsing
def parse_cec(slug: str) -> dict:
    comps, rows, notes, head = {}, [], [], []
    for line in (CEC / f"{slug}.txt").read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if m := re.match(r"^COMP (\S)=(.+)$", line):
            comps[m[1]] = m[2].strip()
        elif m := re.match(r"^(\d+)\|([^|]*)\|(\S?)$", line):
            rows.append((int(m[1]), m[2].strip(), m[3]))
        elif re.match(r"^\d+\.\s", line):  # raw "1. name 2. name" layout
            for mm in re.finditer(r"(\d+)\.\s*(.+?)(?=\s+\d+\.\s|$)", line):
                rows.append((int(mm[1]), mm[2].strip(), ""))
        elif line.startswith("NOTE: "):
            notes.append(line[6:])
        elif line.startswith(("HEAD: ", "TITLE: ", "SUBMITTED: ", "DATES: ")):
            head.append(line.split(": ", 1)[1])
    rows.sort()
    return {"comps": comps, "rows": rows, "notes": notes, "head": head}


def fnv1a(b: bytes) -> str:
    h = 0x811C9DC5
    for c in b:
        h ^= c
        h = (h * 0x01000193) & 0xFFFFFFFF
    return format(h, "x")


def verify_hashes(parsed: dict) -> None:
    bad = []
    for line in (CEC / "_browser_fnv1a_hashes.txt").read_text().split("\n"):
        if not line.strip():
            continue
        slug, n, h = line.split()
        rows = parsed[slug]["rows"]
        s = "\n".join(f"{p}|{name}" for p, name, _ in rows).encode()
        if len(rows) != int(n) or fnv1a(s) != h:
            bad.append(slug)
    if bad:
        sys.exit(f"CEC snapshot does not match browser hashes: {bad}")


# Blue and White: every candidate resigned; names survive only in the CEC notes.
def blue_white_rows(notes: list[str]) -> list[tuple]:
    out = {}
    for n in notes:
        if "שהוצבו במקומות 1–8" in n:
            names = [x.strip() for x in n.split(", שהוצבו")[0].split(",")]
            slots = list(range(1, 9)) + [11, 12, 14, 16, 17, 18, 20, 22, 23, 24]
            for i, nm in enumerate(names):
                out[nm] = slots[i] if i < len(slots) else None  # 26-41 ambiguous: 15 names, 16 slots
        elif "במקומות ה-9 וה-10" in n:
            out["אריאל בזיז"], out["מוריה סילפן"] = 9, 10
        elif "במקום ה-21" in n:
            out["דוד אסייג"] = 21
        elif "במקומות ה-13, ה-15 וה-25" in n:
            out["שי זולדן"], out["שי דוד"], out["מיכאל שי גרבי"] = 13, 15, 25
    return sorted(((p, nm) for nm, p in out.items()), key=lambda x: (x[0] is None, x[0] or 0))


# ---------------------------------------------------------------- English names
def en_lists() -> dict[str, list[str]]:
    doc = lhtml.fromstring(wiki("en_party_lists")["text"])
    out, cur = {}, None
    for el in doc.iter():
        if el.tag in ("h2", "h3") and el.get("id"):
            cur = el.get("id")
            out.setdefault(cur, [])
        elif el.tag == "li" and cur and el.getparent() is not None and el.getparent().tag == "ol":
            if el.xpath("ancestor::*[contains(@class,'reflist') or contains(@class,'references')]"):
                continue
            for bad in el.xpath(".//sup | .//span[contains(@class,'ilh-link')]"):
                bad.drop_tree()
            t = re.sub(r"\s+", " ", el.text_content()).strip()
            t = re.sub(r"\s*\[\s*he\s*\]", "", t)
            t = re.sub(r"\s+(RZ|Z|H|T|B|D|A|R|N|Y|M|YE)$", "", t)  # party-key suffixes
            t = t.replace("⁠", "").strip()
            if t:
                out[cur].append(t)
    return out


HEB = {"א": "", "ב": "b", "ג": "g", "ד": "d", "ה": "", "ו": "", "ז": "z", "ח": "h", "ט": "t", "י": "",
       "כ": "k", "ך": "k", "ל": "l", "מ": "m", "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "", "פ": "p",
       "ף": "p", "צ": "z", "ץ": "z", "ק": "k", "ר": "r", "ש": "s", "ת": "t"}


def skel_he(tok: str) -> str:
    tok = tok.replace("ג'", "j").replace("ז'", "z").replace("צ'", "c").replace("ח'", "h")
    return "".join(HEB.get(c, c if c in "jzc" else "") for c in tok)


def skel_en(tok: str) -> str:
    t = tok.lower()
    for a, b in (("sch", "s"), ("sh", "s"), ("ch", "h"), ("kh", "h"), ("tz", "z"), ("ts", "z"), ("ph", "p"),
                 ("th", "t"), ("ck", "k"), ("dj", "j"), ("zh", "z")):
        t = t.replace(a, b)
    m = {"b": "b", "v": "b", "w": "", "f": "p", "p": "p", "k": "k", "c": "k", "q": "k", "g": "g", "j": "j",
         "d": "d", "t": "t", "z": "z", "s": "s", "x": "ks", "l": "l", "m": "m", "n": "n", "r": "r", "h": "h", "y": ""}
    return "".join(m.get(c, "") for c in t)


def name_sim(en: str, he: str) -> float:
    et = [skel_en(x) for x in re.split(r"[\s\-']+", en) if x]
    ht = [skel_he(x) for x in re.split(r"[\s\-]+", re.sub(r"[()\"״׳]", " ", he)) if x]
    if not et or not ht:
        return 0.0
    # token-set score: each English token against its best Hebrew token; drop 'h' noise
    score = 0.0
    for e in et:
        best = max(difflib.SequenceMatcher(None, e.replace("h", ""), h.replace("h", "")).ratio() for h in ht)
        score += best
    return score / len(et)


def align(en: list[str], he: list[str]) -> dict[int, tuple[str, float]]:
    """Assign English names to CEC rows. Returns he-index -> (en, score).

    Wikipedia's order is not always the CEC's (it lags renumbering after resignations and
    sometimes swaps adjacent slots), so this is a global greedy assignment on a crude
    consonant-skeleton similarity, with a small penalty for positional distance. A pair is
    accepted when similarity >= 0.75, or >= 0.45 when the positions differ by <= 2.
    """
    pairs = []
    for i, e in enumerate(en):
        for j, h in enumerate(he):
            sim = name_sim(e, h)
            d = abs(i - j)
            if sim >= 0.75 or (sim >= 0.45 and d <= 2):
                pairs.append((sim - 0.02 * d, sim, i, j))
    pairs.sort(reverse=True)
    used_i, out = set(), {}
    for _, sim, i, j in pairs:
        if i in used_i or j in out:
            continue
        used_i.add(i)
        out[j] = (en[i], sim)
    return out


# ---------------------------------------------------------------- incumbents
def norm_he(s: str) -> list[str]:
    s = re.sub(r"[()\"״׳`]", " ", s).replace("'", "'").replace("-", " ")
    return [t for t in s.split() if t]


def he_mk_match(mk: list[str], cec: list[str]) -> bool:
    """MK names are given-first; CEC names are surname-first. Match when, for some split of
    the MK name into given + surname, the CEC name starts with the surname and contains the
    given-name tokens after it (CEC often adds middle names)."""
    for k in range(1, len(mk)):
        given, sur = mk[:k], mk[k:]
        if cec[: len(sur)] == sur and set(given) <= set(cec[len(sur):]):
            return True
    return False


# Name-only collisions reviewed by hand on 2026-10-22 (same name as a sitting MK, different person).
NOT_INCUMBENT = {("yahadut-degel_list37", 23)}  # כץ חיים מאיר is not Likud MK Haim Katz

# English spellings on en-Wikipedia's MK list that differ from the party-lists page.
EN_OVERRIDES = {("gush-tanachi_list24", 3): "Hanna Hava"}  # חווא חנא; skeleton match too weak


def incumbents() -> tuple[list[list[str]], set]:
    """Sitting members of the 25th Knesset, from the per-faction member tables."""
    he_doc = lhtml.fromstring(wiki("he_k25")["text"])
    he_sets = []
    tables = pd.read_html(io.StringIO(lhtml.tostring(he_doc, encoding="unicode")))
    mt = next(t for t in tables if t.shape[1] == 3 and t.iloc[0, 0] and "חברים" in str(t.iloc[0, 0]))
    for cell in mt.iloc[:, 2].dropna():
        for nm in str(cell).split(","):
            toks = norm_he(nm.strip())
            if toks:
                he_sets.append(toks)
    en_tables = pd.read_html(io.StringIO(wiki("en_mk25")["text"]))
    et = next(t for t in en_tables if "Members" in t.columns and t.shape[0] > 5)
    en_names = set()
    for cell in et["Members"].dropna():
        for nm in str(cell).split("•"):
            nm = re.sub(r"\[.*?\]", "", nm).strip()
            if nm:
                en_names.add(nm.lower())
    return he_sets, en_names


# ---------------------------------------------------------------- main
def main() -> None:
    index = []
    for line in (CEC / "_index.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        letters, title, slug = [x.strip() for x in line.split("|")]
        index.append((letters, title, slug))
    parsed = {slug: parse_cec(slug) for _, _, slug in index}
    verify_hashes(parsed)
    enl = en_lists()
    he_mks, en_mks = incumbents()

    cand_rows, party_rows, align_log = [], [], []
    for letters, title, slug in index:
        p = parsed[slug]
        party_en, sec = PARTY_EN[slug]
        party_he = re.sub(r"\s+–\s+הרשימה אינה מתמודדת.*$", "", title)
        withdrawn = slug == "kachol-lavan_list30"
        comps = p["comps"]
        comp_names = list(dict.fromkeys(COMPONENT_EN.get(v, v) for v in comps.values()))
        is_alliance = len(comp_names) > 1
        alliance = "; ".join(comp_names) if is_alliance else ""
        status = "withdrawn" if withdrawn else "approved"
        url = CEC_BASE + slug

        if withdrawn:
            rows = [(pos, nm, "") for pos, nm in blue_white_rows(p["notes"])]
            order = "given_first"
        else:
            rows = p["rows"]
            order = "surname_first"
        en_names = enl.get(sec, [])
        if slug == "shama" and not en_names:
            en_names = ["Naftali Goldman"]  # en-Wikipedia: "led by Naftali Goldman, who is also its sole member"
        amap = align(en_names, [r[1] for r in rows])
        for j, (en, sc) in sorted(amap.items()):
            align_log.append(f"{slug}\t{rows[j][0]}\t{rows[j][1]}\t{en}\t{sc:.2f}")

        def en_of(j):
            return amap[j][0] if j in amap else ""

        leader_he = rows[0][1] if rows else ""
        leader_en = en_of(0)
        for j, (pos, nm, code) in enumerate(rows):
            toks = norm_he(nm)
            en = EN_OVERRIDES.get((slug, pos)) or en_of(j)
            inc = (any(he_mk_match(mk, toks) for mk in he_mks) or bool(en and en.lower() in en_mks)) \
                and (slug, pos) not in NOT_INCUMBENT
            if withdrawn:  # Blue and White names are given-first
                inc = any(set(mk) <= set(toks) for mk in he_mks) or bool(en and en.lower() in en_mks)
            cand_rows.append({
                "party_en": party_en, "party_he": party_he, "ballot_letters": letters,
                "alliance_components": alliance,
                "component_party": COMPONENT_EN.get(comps.get(code, ""), comps.get(code, "")) if is_alliance and code else "",
                "list_position": pos, "name_en": en, "name_he": nm, "name_he_order": order,
                "is_party_leader": j == 0, "party_leader_en": leader_en, "party_leader_he": leader_he,
                "incumbent_mk_25": bool(inc), "gender": "", "list_status": status,
                "source_url": url, "as_of_date": AS_OF,
            })
        party_rows.append({
            "party_en": party_en, "party_he": party_he, "ballot_letters": letters,
            "leader_en": leader_en, "leader_he": leader_he, "alliance_components": alliance,
            "candidates_count_in_dataset": len(rows),
            "list_complete": not withdrawn,
            "list_status": status, "status_note": STATUS_NOTES.get(slug, ""),
            "cec_title": title, "submitted_by": next((h for h in p["head"] if "הוגשה" in h), ""),
            "en_names_available": len(amap), "source_url": url,
            "en_source_url": WIKI_EN_URL if en_names else "",
        })

    cdf = pd.DataFrame(cand_rows)
    cdf["list_position"] = cdf["list_position"].astype("Int64")
    cdf.to_csv(OUT / "candidates.csv", index=False, encoding="utf-8")
    pd.DataFrame(party_rows).to_csv(OUT / "parties.csv", index=False, encoding="utf-8")
    (RAW / "en_name_alignment.tsv").write_text(
        "slug\tlist_position\tname_he\tname_en\tsimilarity\n" + "\n".join(align_log) + "\n", encoding="utf-8")
    print(f"lists={len(party_rows)} candidates={len(cdf)} en_names={int((cdf.name_en != '').sum())} "
          f"incumbents={int(cdf.incumbent_mk_25.sum())}")


if __name__ == "__main__":
    main()
