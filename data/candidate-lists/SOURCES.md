# Candidate lists, 26th Knesset election: sources and method

Verified **2026-10-22**. Rebuild with:

```bash
uv run --with pandas --with lxml python3 -I scripts/candidate-lists/build.py
```

The build reads only files under `raw/`. It re-fetches nothing except Wikipedia JSON
that is missing from `raw/wikipedia/`, and it pins that to fixed revision ids.

## Key facts (confirmed)

| Fact | Value | Source |
| --- | --- | --- |
| Election date | **Tuesday 27 October 2026** (16 Heshvan 5787) | CEC chair Justice Noam Sohlberg's ruling on the election date, cited by he-Wikipedia "הבחירות לכנסת העשרים ושש" (rev 44101734). en-Wikipedia "2026 Israeli legislative election" (rev 1381432323) agrees. |
| List submission window | 7–8 September 2026, with **8 September** as the deadline | he- and en-Wikipedia timetables. All CEC pages show a publication date of 07.09–09.09.2026. |
| Lists approved | 38 lists, approved by the CEC plenum on **27.9.2026** | CEC index page `https://www.gov.il/he/pages/candidates-lists-26` (last updated 22.10.2026): "כפי שאושרו על ידי מליאת ועדת הבחירות המרכזית לכנסת ה-26 ביום 27.9.2026" |
| Disqualification deadline | 14 September 2026 | he-Wikipedia timetable |
| Surplus-vote agreement deadline | 16 October 2026 | en-Wikipedia |
| Final results due | 4 November 2026 | he- and en-Wikipedia |

## Sources: what worked and what failed

1. **CEC (primary source; all Hebrew names, positions, ballot letters, component parties).**
   The CEC no longer uses `bechirot.gov.il`. Its pages are now under `www.gov.il/he/pages/<slug>`.
   - `curl https://bechirot.gov.il/` returns **301**, and `https://votes26.bechirot.gov.il/` returns **404**.
   - `curl` on any `www.gov.il/he/pages/...` page returns **HTTP 403** with a Cloudflare
     "Just a moment..." JS challenge. WebFetch gets the same **403**.
   - The content API the page itself calls,
     `openapi-gc.digital.gov.il/pub/cio/govil/rest/contentpage/v1/api/content-pages/<slug>?culture=he`,
     returns **HTTP 500** `{"code":"500","type":"General Error","message":"Global Error Message"}`.
     This happens both from curl and from a plain in-page `fetch()`. The page presumably sends
     extra client headers, which were not investigated.
   - **What worked:** a real Chrome session (Claude in Chrome on the agent desktop). Each
     list page was rendered, the candidate table was read, and the text was saved as
     `raw/cec/<slug>.txt`. A local POST sink was blocked by the page, so the text was
     carried out by agent transcription. To catch transcription errors, an FNV-1a hash of
     the `pos|name` lines was computed **inside the browser** for each list and saved as
     `raw/cec/_browser_fnv1a_hashes.txt`. `build.py` checks every list against these hashes
     and exits if any differ. All 36 lists with numbered rows matched byte for byte. The
     two lists not hashed are `shama`, which has one unnumbered name, and `kachol-lavan`,
     which has no rows and whose names come from the notes.
   - English CEC pages (`/en/pages/<slug>`) return the site's 404 page. The CEC publishes
     Hebrew only.
2. **en-Wikipedia "Party lists for the 2026 Israeli legislative election"** (rev 1380861115):
   the source of English names only. Fetched with the MediaWiki `action=parse` API using curl
   and urllib, with no blocking. There is no separate en "Candidate lists ..." article, and
   he-Wikipedia has no "רשימות המועמדים לכנסת העשרים ושש" article. The he election article
   carries the top slots in infoboxes, but it was not needed once the CEC data was in hand.
3. **Wikipedia 25th Knesset member lists** were used for `incumbent_mk_25`:
   he "הכנסת העשרים וחמש" (rev 44096838) and en "List of members of the twenty-fifth Knesset"
   (rev 1381139795).
4. **News** cross-check: Times of Israel, Ynet, Al Jazeera and JC (2026-10-19) report
   that Gantz pulled Blue and White out of the race. This is consistent with the CEC page.

## Column notes

- `name_he` is the name exactly as the CEC prints it: **surname first** (for example "נתניהו בנימין"),
  including middle names. `name_he_order` is `surname_first` for every list except
  Blue and White (see below).
- `name_en` holds en-Wikipedia names aligned to the CEC rows. Wikipedia's order lags the
  CEC: it misses renumbering after resignations and swaps adjacent slots, for example in
  Together at 22–25 and 29–34. For that reason names are matched by a consonant-skeleton
  similarity, not by index. Every pair is logged in `raw/en_name_alignment.tsv` with its
  score. The lowest accepted pairs, around 0.5, were all checked by hand and are correct.
  There is one manual override (Bible Bloc #3 חווא חנא = Hanna Hava). English names
  cover 507 of the 1,361 rows. The rest are blank because Wikipedia gives only the top
  4–40 names for most lists. The Democrats are fully covered.
- `component_party`: the party the CEC says the candidate was nominated by ("מטעם מפלגת ...").
  It is filled only for joint lists. English names are a curated mapping in `build.py`
  (`COMPONENT_EN`), and those marked "(translit.)" are transliterations. Note that the
  CEC credits only #6 Gaby Lasky to Meretz on the Democrats list. Wikipedia's "M"
  markers are not used.
- `is_party_leader` marks list position 1. Co-led lists are Reservists+Economic
  (Hendel #1, Zelekha #2) and RZP–Zehut (Smotrich #1, Feiglin #2 as Zehut leader).
- `incumbent_mk_25`: true when the candidate is a **sitting** member of the 25th Knesset on
  the Wikipedia per-faction member tables. A name matches when the Hebrew names agree,
  with the MK's surname first in the CEC name and the given names contained, or when the
  English names agree. One same-name collision was reviewed and excluded: UTJ #23
  כץ חיים מאיר, who is not Likud's Haim Katz. MKs who left the Knesset mid-term are not
  counted. Matching can still miss an MK whose CEC name differs from the Wikipedia form
  (inferred risk; 105 matches found).
- `gender` is **blank for every row**. The CEC does not publish it, and guessing from
  first names was ruled out as unreliable.
- `list_status`: `approved` for the 37 running lists. `withdrawn` for Blue and White,
  a value added to the requested set. No list is currently `disqualified`.
- `as_of_date` is 2026-10-22 for all rows. `source_url` is the CEC list page.
- `parties.csv` has extra columns: `status_note`, `cec_title`, `submitted_by` (CEC text
  naming the nominating parties), `en_names_available` and `en_source_url`.

## Status events per list (from the CEC pages)

- **Ra'am (עם)** and **Joint List (ודם)** were barred by the CEC on 24.9.2026 under s.7A.
  The Supreme Court reversed both on 2.10.2026, and both are running. Joint List candidate Ofer
  Cassif was also barred and then reinstated. Sami Abu Shehadeh (originally #3) resigned on 2.10.2026.
- **Blue and White (כן)**: every candidate resigned on 20–21.10.2026. The CEC index now
  reads "הרשימה אינה מתמודדת בבחירות לכנסת ה-26" ("the list is not contesting the
  election to the 26th Knesset"). The names survive only in the CEC resignation notes.
  Those notes give names in **given-first** order, and they are reproduced that way.
  Positions 1–25 come straight from the notes. Fifteen further names were assigned
  together to "26–41", which is 16 slots, so their positions are left **blank**. Slot 19
  appears in no note. One news report (2026-10-19) says the party's name stays on the
  ballot paper; this was not verified against the CEC.
- **Resignations and exclusions after submission** are recorded on each CEC page and kept in
  the `NOTE:` lines of `raw/cec/<slug>.txt`. The CEC **renumbers** lists after a
  resignation, and positions in this dataset are the current CEC numbering. For example,
  Together has 118 names because #69 and #118 resigned. Shas has 119 (#117 resigned), the
  Democrats 119 and Yashar 119. Candidates the CEC excluded before approval (s.63) are
  absent; they appear on RZP–Zehut, Ra'am, the Reservists, the Pirates and Mishpat Tzedek.

## Completeness

All 37 running lists are complete against the CEC as of 2026-10-22, from 1 to 120
candidates each. Blue and White (withdrawn) is not complete. English names are partial;
see `en_names_available` in `parties.csv`.

## Confirmed vs inferred

- **Confirmed** from the CEC pages: ballot letters, list titles, every Hebrew name and
  position, nominating parties, approval date and status events.
- **Confirmed** from Wikipedia and news: the election date and the timetable. The CEC
  timetable page `time--table-26` was not read because it is behind the same Cloudflare
  block.
- **Inferred:** English names, which are a Wikipedia transliteration aligned by
  similarity; the English party and component names, which are a curated mapping; and
  `incumbent_mk_25`, which is matched by name.
