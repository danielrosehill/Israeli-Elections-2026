# 25th Knesset dataset: sources and provenance

This is the outgoing Knesset, elected 2022-11-01 and sworn in 2022-11-15. All sources were
fetched and verified on **2026-10-22**. Rebuild the dataset with this command:

```bash
uv run --with lxml python3 -I scripts/knesset-25/build.py --raw <empty_dir> --fetch
```

Without `--fetch`, the script rebuilds from an existing raw directory. On every run it prints
the sanity checks and lists any fuzzy name matches.

## Files

| File | Rows | Grain |
| --- | --- | --- |
| `members.csv` | 152 | One row per person who held a seat at any point: 120 original MKs and 32 who entered later. A person who left and came back under the Norwegian law is one row, and the `notes` column lists each term. |
| `parties.csv` | 16 | One row per Knesset faction (KNS_Faction, KnessetNum 25), including factions that no longer exist. |

Sanity checks, as of the 2026-10-22 build:

- `serving_at_end` = true: **120**.
- Sum of `seats_at_end`: **120**.
- Sum of `seats_won_2022`: **120**. The breakdown is Likud 32, Yesh Atid 24, Religious Zionism 14, National Unity 12, Shas 11, UTJ 7, Yisrael Beiteinu 6, Ra'am 5, Hadash-Ta'al 5 and Labor 4.
- Each list's original MKs hold positions 1..seats_won, and no list position is duplicated.

## Sources that worked

1. **Knesset OData** at `https://knesset.gov.il/Odata/ParliamentInfo.svc/`. This is the authoritative source. It needs no auth and returns JSON with `$format=json`. The server pages results at 100 rows, so follow `odata.nextLink`.
   - `KNS_PersonToPosition?$filter=KnessetNum eq 25` returned 556 rows. PositionID 43 (male MK) and 61 (female MK) give MK terms. **These rows carry no FactionID.** Faction membership comes from PositionID 54 (faction member), which has `FactionID`.
   - `KNS_Faction?$filter=KnessetNum eq 25` returned 16 factions and gives the Hebrew faction names.
   - `KNS_Person` supplies the Hebrew first and last names (sometimes with middle names) and `GenderDesc`.
   - `KNS_MkSiteCode` maps `KnsID` (= OData PersonID) to `SiteId`. SiteId is the ID the Knesset website uses, and it is also the value of Wikidata **P9770**. It is **not** the same as PersonID. For example, Netanyahu has PersonID 965 and SiteId 90.
   - The data is current. The newest `LastUpdatedDate` is 2026-09-09, the date Roni Malkai was sworn in.
2. **Knesset website API**: `https://knesset.gov.il/WebSiteApi/knessetapi/MKs/GetMkdetailsHeader?mkId=<SiteId>&languageKey=en|he`. This is undocumented; it is the API behind the main.knesset.gov.il MK pages. It returns `Name`, `Faction`, `Gender` and `IsCurrentMk`. The script uses it for the Hebrew display name (`name_he`) and records the official English spelling in `notes`. `GetMksList` returned HTTP 400 because it requires an id.
3. **en.wikipedia "Party lists for the 2022 Israeli legislative election"** (revid 1374592799). The candidate lists are in `div.div-col > li` elements in list order. This page supplies `list_position_2022` and the common English spelling used as `name_en`.
4. **he.wikipedia "הכנסת העשרים וחמש"** (revid 44096838). The table headed `חבר הכנסת היוצא` lists every replacement with its date, the outgoing MK, the reason and the incoming MK. It uses rowspans, which `grid()` expands. This page supplies `reason_left` and `replaced_by`. It is more complete than the English page: for example, it includes Boaz Toporovsky → Oz Haim on 2026-06-07, which en.wikipedia omits.
5. **en.wikipedia "List of members of the twenty-fifth Knesset"** (revid 1381139795). Its first wikitable supplies `leader_en` and `bloc_at_end`.
6. **Wikidata SPARQL** for P9770, run at `query.wikidata.org/sparql`. It returned 1073 items, used as a fallback for English labels and en/he wiki titles. **Coverage is incomplete:** many MKs who entered in 2022 or later have no P9770 claim. For that reason, names are matched by fuzzy similarity rather than by ID.

## Sources that failed or were not usable

- he.wikipedia `חברי הכנסת העשרים וחמש` returned `{"error":{"code":"missingtitle"}}` because the page does not exist. The script uses `הכנסת העשרים וחמש` instead.
- Wikidata P9770 cannot serve as the join key on its own (see source 6 above).
- The Knesset site endpoint `GetMksList?languageKey=en` returned HTTP 400 with the message "parameters dictionary contains a null entry for parameter 'id'".

## Field provenance

These fields are **confirmed from OData**:

- `member_id`
- `start_date` (the first MK term start)
- `end_date` (the last term finish; blank if a term is still open)
- `serving_at_end`
- `gender`
- `faction_at_end` (the person's last faction-membership row)
- `faction_he`
- `seats_at_end`, counted from serving MKs by their final faction

These fields come from **Wikipedia, joined by fuzzy name matching**:

- `list_position_2022`, `name_en`. Matches scoring below 0.95 are printed at build time; every one was checked by eye on 2026-10-22. One manual override exists: PersonID 30847 = Yitzhak Wasserlauf, whose name the Knesset site transliterates as "Issac Shimon".
- `reason_left`, `replaced_by`. These come from he.wikipedia, mapped from the Hebrew reason text to English categories through `REASONS` in `build.py`.
- `leader_en`, `leader_he`, `bloc_at_end`.

These fields are **inferred** or editorial:

- `list_elected_on` is the 2022 list the person was matched to. Replacement MKs entered from the same list.
- The English faction names and the faction `notes` come from the `FACTIONS` map in the script.
- `seats_won_2022` is assigned to the original faction of each list: the joint Religious Zionism faction carries 14 and the original National Unity faction carries 12. The successor factions have it blank, so the column sums to 120.

## Known gaps and caveats

- **Norwegian law.** Ministers who resigned their seat and later returned have several terms, all listed in `notes`. Their `end_date` is blank, and `reason_left` is blank because they are serving at the end. MKs who entered as Norwegian-law replacements and were pushed out when the minister returned have `reason_left` = "Norwegian law (minister returned to Knesset)". Examples are Eliyahu Baruchi, Moshe Roth and Semion Moshiashvili. Erez Malul has a zero-length OData term on 2025-07-20, which is real data: he left, came back and left again on the same day.
- **Rowspans in the he.wikipedia reason column.** For 2026-07-28 to 2026-09-09, the reason cells are shared across rows. As a result, Dan Illouz and Elazar Stern inherit "resigned (joined another party)" from the Segalovitz row. en.wikipedia confirms party moves for all three: Illouz to Yisrael Beiteinu, Stern to Yashar, and Segalovitz to Ra'am (as en.wikipedia lists him). Treat these as inferred.
- **Mismatches between en.wikipedia and OData.** The en.wikipedia composition table gives Otzma Yehudit 7 and RZP 6. OData (and he.wikipedia) give RZP 7 and Otzma 6, because Almog Cohen (Otzma) was replaced by Zvi Sukkot (RZP) on 2025-04-06. OData is used. en.wikipedia says Almog Cohen moved to Likud, but OData still has him in Otzma when he left. Sharren Haskel (en.wikipedia says "Israel First") and Yuli Edelstein are still in their original factions in OData.
- **`bloc_at_end` is taken from en.wikipedia's status column.** It shows Shas as coalition even though its ministers resigned in July 2025, UTJ as opposition and Noam as unaffiliated. This is a political judgment, not an official Knesset field.
- **`leader_en` for Labor** is Efrat Rayten, the Knesset faction leader. Merav Michaeli is recorded as an earlier leader. The Democrats, the merged Labor–Meretz party led by Yair Golan, is not a Knesset faction.
- **`name_he`** is the Knesset site display name, which sometimes includes a middle name (for example, אריה מכלוף דרעי). OData full names are in the raw data.
- **No deaths** were recorded in the 25th Knesset.
