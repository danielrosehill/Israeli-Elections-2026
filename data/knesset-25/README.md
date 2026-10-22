---
license: cc-by-sa-4.0
language:
- en
- he
pretty_name: Israel 25th Knesset — Members and Factions
tags:
- politics
- israel
- knesset
- elections
size_categories:
- n<1K
configs:
- config_name: members
  data_files: members.csv
  default: true
- config_name: parties
  data_files: parties.csv
---

# Israel 25th Knesset: Members and Factions

This dataset covers the outgoing **25th Knesset**, elected on 1 November 2022, at the end of its term ahead of the 27 October 2026 election. It records everyone who held a seat and how the factions stood at the end.

| File | Rows | One row per |
|---|---|---|
| `members.csv` | 152 | Person who served at any point: the 120 original MKs plus 32 replacements |
| `parties.csv` | 16 | Knesset faction, including 3 that dissolved during the term (shown with 0 seats) |

Verified on 2026-10-22: `serving_at_end` is true for 120 members, `seats_at_end` sums to 120, and `seats_won_2022` sums to 120. The 2022 result was Likud 32, Yesh Atid 24, RZP 14, National Unity 12, Shas 11, UTJ 7, Yisrael Beiteinu 6, Ra'am 5, Hadash–Ta'al 5 and Labor 4.

## Key fields

**members.csv**
- `member_id`: the Knesset OData PersonID.
- `name_en` and `name_he`: the member's name in English and Hebrew.
- `list_elected_on` and `list_position_2022`: the electoral list the member was elected on, and their position on it.
- `faction_at_end`: the member's faction at the end of the term, or when they left. This reflects the splits: National Unity → New Hope, and RZP → RZP / Otzma Yehudit / Noam.
- `start_date` and `end_date`.
- `serving_at_end`.
- `reason_left`: for example resigned, the Norwegian law, or deceased.
- `replaced_by`.
- `gender`.

**parties.csv**
- `faction_en` and `faction_he`: the faction's name in English and Hebrew.
- `seats_won_2022` and `seats_at_end`.
- `leader_en` and `leader_he`: the faction leader's name in English and Hebrew.
- `bloc_at_end`: coalition or opposition.

## Sources

- **Knesset OData API** (`knesset.gov.il/Odata/ParliamentInfo.svc`): the authoritative source for IDs, terms, gender and factions.
- **Knesset website API:** Hebrew display names.
- **English and Hebrew Wikipedia:** 2022 list positions, English spellings, reasons for leaving, faction leaders and bloc.

`SOURCES.md` covers what was confirmed and what was inferred, where the sources disagree (for example the Otzma and RZP seat split), and known gaps.

## Related

- [Israel-Election-2026-Candidate-Lists](https://huggingface.co/datasets/danielrosehill/Israel-Election-2026-Candidate-Lists)
- [Israel-Election-2026-Polls](https://huggingface.co/datasets/danielrosehill/Israel-Election-2026-Polls)
- Build scripts and the forecasting experiment: [github.com/danielrosehill/Israeli-Elections-2026](https://github.com/danielrosehill/Israeli-Elections-2026)

Licence: CC BY-SA 4.0, because some fields derive from Wikipedia.
