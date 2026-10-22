---
license: cc-by-sa-4.0
language:
- he
- en
pretty_name: Israel 2026 Knesset Election — Candidate Lists
tags:
- politics
- israel
- knesset
- elections
size_categories:
- 1K<n<10K
configs:
- config_name: candidates
  data_files: candidates.csv
  default: true
- config_name: parties
  data_files: parties.csv
---

# Israel 2026 Knesset Election: Candidate Lists

This dataset contains every candidate list for the election to the **26th Knesset**, held on **27 October 2026**. Each candidate appears with their list and position, and every row also names the list's leader.

| File | Rows | One row per |
|---|---|---|
| `candidates.csv` | 1,361 | Candidate per list, with `list_position` |
| `parties.csv` | 38 | List: ballot letters, leader, alliance components, status |

## Status as of 2026-10-22

- **Submission and approval:** lists were submitted on 7–8 September 2026, and the Central Elections Committee (CEC) approved all 38 on 27 September 2026.
- **Ra'am and the Joint List:** the CEC barred both on 24 September; the Supreme Court reversed that on 2 October, so both are running.
- **Blue and White:** the list withdrew on 20–21 October, when all its candidates resigned. It is kept with `list_status = withdrawn`.
- **Completeness:** all 37 running lists are complete against the CEC. Positions follow the CEC's current numbering, which closes the gaps left by resignations.

## Key fields

- **List:** `party_en`, `party_he`, `ballot_letters` (Hebrew ballot letters) and `alliance_components`.
- **Candidate:** `component_party`, `list_position`, `name_en`, `name_he` and `name_he_order`. Hebrew names are written surname first, except Blue and White, which is given name first.
- **Leader:** `is_party_leader`, `party_leader_en` and `party_leader_he`.
- **Other:** `incumbent_mk_25` (true if the candidate is a sitting 25th-Knesset member), `list_status` and `source_url`.

## Sources and caveats

- **Hebrew names, positions and ballot letters** come from the official CEC list pages on gov.il. A plain fetch of those pages is blocked by a Cloudflare challenge, so they were read in a real browser. Each list's text was checked against a fingerprint computed in the browser, and all 36 numbered lists match.
- **English names** cover 507 of 1,361 rows. They come from English Wikipedia, which usually names only the top of each list, and were matched to the CEC rows by how the names sound; the match log is in `raw/`.
- **`incumbent_mk_25`** is a name match against sitting 25th-Knesset members.
- **`gender`** is left empty, because the CEC doesn't publish it and it wasn't guessed from first names.

See `SOURCES.md` for full details.

## Related

- [Israel-Knesset-25-Members](https://huggingface.co/datasets/danielrosehill/Israel-Knesset-25-Members)
- [Israel-Election-2026-Polls](https://huggingface.co/datasets/danielrosehill/Israel-Election-2026-Polls)
- Build scripts and the forecasting experiment: [github.com/danielrosehill/Israeli-Elections-2026](https://github.com/danielrosehill/Israeli-Elections-2026)

Licence: CC BY-SA 4.0, because some fields derive from Wikipedia.
