---
license: cc-by-sa-4.0
language:
- en
pretty_name: Israel 2026 Knesset Election — Opinion Polls
tags:
- politics
- israel
- knesset
- elections
- polling
- forecasting
size_categories:
- 10K<n<100K
configs:
- config_name: polls
  data_files: polls.csv
  default: true
- config_name: poll_results
  data_files: poll_results.csv
- config_name: party_aliases
  data_files: party_aliases.csv
---

# Israel 2026 Knesset Election: Opinion Polls

This dataset contains every published seat-projection poll for the 27 October 2026 Knesset election, from 23 December 2022 to 22 October 2026. A publication ban starts at 23:59 on 23 October, so no later polls can be published.

| File | Rows | One row per |
|---|---|---|
| `polls.csv` | 1,109 | Poll: 694 standard, 110 alternative versions of a standard poll, 305 hypothetical scenarios |
| `poll_results.csv` | 15,319 | Poll × party, in long format |
| `party_aliases.csv` | 89 | Party column header as it appears in the source → normalised party name |

## Key fields

**polls.csv**
- `poll_id`: a stable identifier.
- `release_date`, `fieldwork_start` and `fieldwork_end`.
- `pollster` (the polling company) and `publisher` (the media outlet).
- `sample_size`: populated only for the 2026 polls.
- `scenario`: `standard`, or a description of the hypothetical scenario.
- `coalition_seats`: as Wikipedia reports it.
- `coalition_seats_computed`: recomputed from the party figures.
- `opposition_seats`: 120 minus `coalition_seats`.
- `seat_sum` and `seat_sum_ok`.

**poll_results.csv**
- `party`: the normalised name, consistent across mergers and splits.
- `party_as_listed`: the name as it appeared in the source.
- `seats`.
- `vote_share_pct`: for parties below the threshold, where the poll gives one.
- `below_threshold`.
- `cell_status`: `seats`, `dash` and so on. Wikipedia uses "–" both for "no figure given" and for "below threshold".

## Caveats

- **Source:** the data is extracted programmatically from English Wikipedia's *Opinion polling for the 2026 Israeli legislative election* page and its sub-pages for 2022–23, 2024 and 2025. The page revision IDs are recorded.
- **Release dates:** Wikipedia gives fieldwork dates. `release_date` is the cited article's date when it falls 0–10 days after fieldwork (1,037 rows); otherwise it is the end of fieldwork.
- **Seat totals:** 14 of the 694 standard polls don't sum to 120 in the source. They are flagged, not corrected.
- **`margin_of_error`** is empty, because Wikipedia doesn't carry it.

See `SOURCES.md` for the parsing pitfalls and what was confirmed versus inferred.

## Related

- [Israel-Knesset-25-Members](https://huggingface.co/datasets/danielrosehill/Israel-Knesset-25-Members)
- [Israel-Election-2026-Candidate-Lists](https://huggingface.co/datasets/danielrosehill/Israel-Election-2026-Candidate-Lists)
- Build scripts and the forecasting experiment: [github.com/danielrosehill/Israeli-Elections-2026](https://github.com/danielrosehill/Israeli-Elections-2026)

Licence: CC BY-SA 4.0, because the data derives from Wikipedia.
