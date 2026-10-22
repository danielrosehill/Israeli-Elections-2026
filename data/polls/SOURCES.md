# Seat-projection polls for the 2026 Knesset election: sources and method

Verified **2026-10-22**. The election is on **27 October 2026**. Israeli law bans publishing
new polls from 23:59 on Friday 23 October, so the newest poll in the data is dated 22 Oct 2026.

Rebuild with this command, run from the repo root:

```bash
uv run --with pandas --with lxml --with beautifulsoup4 python3 -I scripts/polls/build.py --refresh
```

Without `--refresh`, the script re-parses the cached API JSON in `--raw-dir`. The default is
the session scratchpad `.../scratchpad/polls-raw/`, which does not persist, so pass `--refresh`
or a new `--raw-dir` on a fresh machine. The script prints every sanity check below.

## Pages parsed (English Wikipedia, MediaWiki `action=parse&prop=text|revid`)

| Page | revid parsed | Rows contributed |
| --- | --- | --- |
| Opinion polling for the 2026 Israeli legislative election | 1381470344 | 2026 seat projections (276 standard + 15 alternative rows), plus every scenario poll (305 rows) |
| 2025 opinion polling for the 2026 Israeli legislative election | 1380861669 | 176 standard + 59 alternative |
| 2024 opinion polling for the 2026 Israeli legislative election | 1380862701 | 127 standard + 28 alternative |
| 2022–2023 opinion polling for the 2026 Israeli legislative election | 1380863281 | 115 standard + 8 alternative |

The main page's "2025", "2024" and "2022–2023" subsections contain only links to the
year sub-pages, so no data is duplicated across pages.

A table is used only if its first header cell is "Fieldwork date" or "Date" and its `h2`
section is **Seat projections** (scenario = `standard` or `alternative …`) or **Scenario polls**
(scenario = `hypothetical: <h4 title>`). The following sections are skipped on purpose:
Voting intention polls (percentages), Arab voters (percentages), Preferred prime minister,
Coalition polls and Other questions.

**Hebrew Wikipedia.** The page "סקרי דעת קהל לקראת הבחירות לכנסת העשרים ושש" does **not exist**
(API `missingtitle`, checked 2026-10-22). The "סקרים" section of "הבחירות לכנסת העשרים ושש"
(revid 44101734) is prose with no tables. Its checkable claims agree with the data:

- The Kan 11 poll of 16 June 2026 gave Likud 23, Yashar 21 and Together 17. The dataset matches exactly.
- In the final weeks, Yashar led most polls with 21–23 seats. In the dataset, standard polls released on or after 1 Oct give Yashar 19–26, Likud 18–32 and Together 7–15. The wider spread comes from Channel 14 and i24, which the Hebrew text itself calls outliers.

## Files

- `polls.csv` has one row per poll row in the source. A single poll can appear several times:
  as a standard row, as an alternative row, and in scenario tables. Rows of one Wikipedia
  rowspan group share a `scenario_group`.
- `poll_results.csv` has one row per poll × party. Columns marked "N/a" in the source (party not
  included in that poll or scenario) produce **no row**.
- `party_aliases.csv` maps each `party_as_listed` to a normalised `party`. `columns_spanned`
  lists the header leaf labels a cell covered, joined with a bare `+`.

## Conventions and pitfalls (how each was handled)

1. **Rowspan and colspan.** Every table is expanded into a full grid (`expand()`).
   - Header labels come from the top and leaf header cells of each column. Colour-swatch rows are ignored.
   - A multi-column header with no sub-labels is split on "-" into one name per column. Example: "RZP - Zehut" with colspan 2.
2. **Joint lists in a data cell.** A data cell spanning several party columns is one joint list.
   - If it covers exactly one grouped header, `party_as_listed` is that header: "RZP - Zehut", "Reserv. - NEP", "Joint List".
   - Otherwise it is the leaf labels joined with `+`, for example `Bennett 2026+Yesh Atid+Yashar`. These are mapped component by component.
3. **The Joint List changes meaning over time.**
   - Dec 2025 – Jun 2026 tables put Ra'am under the Joint List header. A cell spanning all three
     sub-columns becomes `Joint List (Ra'am + Hadash–Ta'al + Balad)`.
   - From Jul 2026 Ra'am has its own column and "Joint List" means `Joint List (Hadash–Ta'al + Balad)`.
   - Before that, Hadash–Ta'al and Balad are separate parties.
4. **Party renames and successors.** These are recorded in `party_aliases.csv` notes rather than merged into one name:
   - The Gantz party is "National Unity" until Aug 2025 and "Blue & White" afterwards.
   - "Bennett" and "Bennett party" (hypothetical) become "Bennett 2026".
   - "Hendel" and "Hendel party" become "The Reservists (Hendel)". "Reserv. - NEP" is the 2026 joint run.
   - Eisenkot's party is "Yashar (Eisenkot)".
   - Labor and Meretz stay separate until June 2024 and are "The Democrats (Labor + Meretz)" after the merger.
   - "Together" = Bennett 2026 + Yesh Atid (from April 2026). Yesh Atid alone appears until 2026-04-24.
5. **Below-threshold cells.** `cell_status` takes one of these values:
   - `(2.1%)` → `below_threshold_pct`: seats 0, `vote_share_pct` 2.1, below_threshold true. `(<1%)` and `(~2%)` are parsed the same way.
   - `(1)` → `below_threshold_no_threshold_seats`: seats 0, `seats_without_threshold` = 1.
   - `–` → `dash`: seats 0, below_threshold true. Wikipedia uses the dash for "no information *or* below threshold without detail", so the cell is ambiguous. Filter on `cell_status` if that matters.
   - `?` / `TBA` → `unknown`: seats empty. Seen in partial scenario rows.
   - `4 (3.5%)` → seats 4 plus vote_share 3.5.
   - `— N/a` (class `table-na`) → no row.
6. **Two rows in one rowspan group, standard tables.** The first row is `standard`. Later rows are
   `alternative k (same poll, second row): with X; without Y`. That description is *computed*
   by diffing which parties are present. It is not text from the source.
7. **Dates.**
   - Wikipedia lists **fieldwork** dates, or the publication date when fieldwork dates are unknown.
   - `fieldwork_end` comes from the cell's `data-sort-value` (ISO) when present. Otherwise it is parsed from the text, including 2-digit years like "10 Aug 23" in scenario tables.
   - `release_date` is the publication date of the cited article when it falls 0–10 days after fieldwork_end (`release_date_basis=citation_date`, 1037 rows). Otherwise it is `fieldwork_end` (56 rows).
   - Citation dates are read before any "Retrieved"/"Archived" text, so access dates are not used.
   - There are 3 rows where Wikipedia's `data-sort-value` has the wrong year: Kantar/Israel Hayom polls dated Jan–Feb 2025 inside the 2026 table. These are corrected from the citation date and logged in `date_note`.
   - There are 8 scenario rows with no year anywhere. Their year comes from the citation date (`date_note`).
8. **Event rows** (e.g. "Bennett and Lapid announce a joint run"), election-result rows and
   rows with no figures are skipped. The script prints the counts.
9. **Coalition.**
   - `coalition_seats` is Wikipedia's "Gov." column: the sum for the 37th-government parties (Likud, RZP or RZP-Zehut, Otzma, Shas, UTJ).
   - `opposition_seats` = 120 − coalition. This is *computed*; the source has no opposition column.
   - `coalition_seats_computed` recomputes the coalition from the party rows as a cross-check.
10. **Footnotes.** `[a]`-style markers are removed from values.
    - Explanatory notes on the date, pollster, publisher, sample or Others cells go into `notes`. These include the breakdown of "Others", e.g. "Noam at 0.6%, Ahi at 0.2%".
    - Notes on a party cell go into `cell_notes`.
    - The first citation with an external link on the publisher cell is `source_url`.
11. **Pollster abbreviations** are expanded using the page's "Pollsters and publishers" table.
    Examples: SF+ND = Shlomo Filber + NEXT DATA, LRI+P4A = Lazar Research Institute + Panel4All,
    MP+TM+SN+A = Midgam Project + The Madad + Stat-Net + Askaria, CF+MP+SN = Camil Fuchs + Midgam
    Project + Stat-Net. The raw string is kept in `pollster_as_listed`. One stray backtick in the
    source (`MP+TM+SN+A\``) is normalised. Publisher "–" maps to `(none listed)`.
12. **poll_id** = `{release_date}_{publisher}_{pollster_as_listed}[_alt|_scn-<scenario>]_{n}`. The
    `n` counter follows source order. IDs stay stable while the page rows don't change, but
    inserting a poll with the same date, publisher and pollster renumbers the later ones.

## Sanity checks (run of 2026-10-22)

- Poll rows: **1109** (694 standard, 110 alternative, 305 hypothetical). Party rows: about 15.1k.
- Release dates run from 2022-12-23 to 2026-10-22. No row is missing a date, and every fieldwork_end falls between 2022-11-01 and 2026-10-22.
  - The only poll between the 1 Nov 2022 election and 23 Dec 2022 on Wikipedia is that 23 Dec Maariv/Panels poll. The election-result row is excluded.
- Duplicate poll_ids: **0**.
- **Standard polls whose seats don't sum to 120: 14 of 694.**
  - 4 contain a `–` cell, which hides a figure (2025-01-23, 2025-05-25 and 2025-09-11 Midgam/Ch12; 2025-06-25 Lazar/Walla).
  - 10 are arithmetic in the source, with sums of 117–122. Examples: Direct Polls/i24 on 2026-09-02 sums to 122, and Midgam/Ch12 on 2026-04-23 (second poll that day) sums to 118.
  - Spot-checks against the raw HTML confirmed that the cell values are transcribed correctly. They were not checked against the original articles.
- Standard polls where Wikipedia's Gov. ≠ the recomputed coalition: 7. Most are off by 1. Maariv on 2026-03-13 has Gov. 57 against a party sum of 50, which looks like a Wikipedia typo. Gov. is kept as reported.
- Date order: 2 departures from reverse-chronological order within a table. Both are fine: same-day reordering on 12/13 May 2026, and the 2023 rows of the Likud-leadership scenario table.
- Unparsed cells: 0. Unmapped party, pollster and publisher labels: 0.

## Known gaps

- `margin_of_error` is always empty because Wikipedia does not carry it. `sample_size` is only
  in the 2026 tables (229 of 694 standard rows).
- `release_date` is inferred from citation metadata. Where the citation has no date, it falls back to the fieldwork date.
- Hypothetical-scenario rows often have `?` or N/a for parties the pollster didn't report. Don't sum them.
- Percentage-only polls (IDI/Viterbi, Arab-sector polls) are excluded because they are not seat projections.
- Party normalisation is a judgement call. Each one is written down in `party_aliases.csv`.
  The renames for Blue & White/National Unity and Bennett are taken from the page's
  "Guide to the table" and footnotes. The ideological descriptions in the notes are general knowledge and were not checked here.

## Confirmed vs inferred

- **Confirmed (read from source):** seat and percentage values, Gov. totals, sample sizes, fieldwork text, data-sort-value dates, citation URLs and dates, header labels, and the Hebrew-article cross-checks above.
- **Inferred:**
  - `release_date` when based on the citation date.
  - The descriptions of alternative scenarios.
  - `opposition_seats`.
  - Normalised party names.
  - Year corrections (`date_note`).
  - Treating `–` as below threshold.
