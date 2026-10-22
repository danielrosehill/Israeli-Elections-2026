"""Build the question bank for the decision-model panel.

Run from the repo root:
    python3 -I experiment/questions.py

Writes experiment/questions.json. Each question carries:
- the System One fields sent to the model: type, instructions, criteria;
- resolution: how it is scored (fixed before the election, never edited after);
- resolves_by: the date the answer is expected to be known;
- mirrors: market outcomes it can be compared against, as "source:market_or_event".

Seat questions use one option per feasible seat count (0, then 4..N),
because a list below the 3.25% threshold wins nothing and one above it wins at
least 4. Every Kalshi "Above N" ladder and the Polymarket Likud bins can then be
derived exactly from one distribution. List names are party_en from
data/candidate-lists/parties.csv.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "questions.json"
FINAL = "2026-11-05"  # final CEC results are due about 8 days after polling day
GOVT = "2027-02-28"   # outer limit for the first government formation attempt, all mandates included

NETANYAHU_BLOC = ["Likud", "Shas", "United Torah Judaism", "Otzma Yehudit",
                  "Religious Zionist Party – Zehut", "Noam"]
OPPOSITION_ZIONIST = ["Yashar", "Together (B'Yachad)", "The Democrats", "Yisrael Beiteinu",
                      "The Reservists and the Economic Party", "Amcha Yisrael"]
ARAB_LISTS = ["Joint List", "United Arab List (Ra'am)"]

SEAT_LISTS = {  # list -> top of its seat range
    "Likud": 40, "Yashar": 40, "Together (B'Yachad)": 25, "The Democrats": 20,
    "Shas": 16, "United Torah Judaism": 14, "Otzma Yehudit": 16, "Yisrael Beiteinu": 16,
    "Religious Zionist Party – Zehut": 14, "Joint List": 14, "United Arab List (Ra'am)": 12,
    "The Reservists and the Economic Party": 12, "Amcha Yisrael": 12,
}
KALSHI_COUNT = {
    "Likud": "KXLIKUDCOUNT-26OCT27", "Yashar": "KXYASHARCOUNT-26OCT27",
    "Together (B'Yachad)": "KXTOGETHERCOUNT-26OCT27", "The Democrats": "KXISRDEMCOUNT-26OCT27",
    "Shas": "KXSHASCOUNT-26OCT27", "Yisrael Beiteinu": "KXBEITEINUCOUNT-26OCT27",
}
THRESHOLD_LISTS = [  # lists whose entry is in doubt, plus the next-nearest fringe lists
    "The Reservists and the Economic Party", "Amcha Yisrael", "Religious Zionist Party – Zehut",
    "United Arab List (Ra'am)", "Yisrael Beiteinu", "Joint List", "Noam", "Israel First", "Haredi Public",
]
PM_OPTIONS = {
    "netanyahu": "Benjamin Netanyahu (Likud)", "eisenkot": "Gadi Eisenkot (Yashar)",
    "bennett": "Naftali Bennett (Together)", "lieberman": "Avigdor Lieberman (Yisrael Beiteinu)",
    "other": "Someone else",
}

def slug(name):
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_").replace("__", "_")


questions = {}


def q(qid, group, qtype, instructions, resolution, resolves_by, criteria=None, mirrors=()):
    assert qid not in questions, qid
    questions[qid] = {
        "group": group, "type": qtype, "instructions": instructions,
        **({"criteria": criteria} if criteria is not None else {}),
        "resolution": resolution, "resolves_by": resolves_by, "mirrors": list(mirrors),
    }


# 1. Headline result -----------------------------------------------------------
top3 = {"likud": "Likud", "yashar": "Yashar", "together": "Together (B'Yachad)", "other": "Any other list"}
q("largest_list", "result", "choice", "Which list will win the most seats in the 26th Knesset?",
  "List with the most seats in the final CEC results. A tie is broken by valid votes.", FINAL, top3,
  ["kalshi:KXISRAELKNESSET-26", "polymarket:israeli-legislative-election-winner"])
q("yashar_largest", "result", "noul", "Will Yashar win more seats than any other list?",
  "Same resolution as largest_list. Consistency pair with largest_list.", FINAL)
q("second_list", "result", "choice", "Which list will come second in seats?",
  "Second-largest list by seats, ties broken by valid votes.", FINAL, top3, ["kalshi:KXISRAEL2ND-26OCT27-2"])
q("third_list", "result", "choice", "Which list will come third in seats?",
  "Third-largest list by seats, ties broken by valid votes.", FINAL,
  {"together": "Together (B'Yachad)", "democrats": "The Democrats", "shas": "Shas",
   "otzma": "Otzma Yehudit", "likud_or_yashar": "Likud or Yashar", "other": "Any other list"},
  ["kalshi:KXISRAEL3RD-26OCT27-3"])
q("likud_below_32", "result", "noul", "Will Likud win fewer than 32 seats, its 2022 total?",
  "Likud seats in the final CEC results are 31 or fewer. Consistency pair with seats_likud.", FINAL,
  mirrors=["polymarket:israel-election-will-likud-lose-seats"])

# 2. Blocs ---------------------------------------------------------------------
bloc_txt = ", ".join(NETANYAHU_BLOC)
opp_txt = ", ".join(OPPOSITION_ZIONIST)
q("netanyahu_bloc_61", "blocs", "noul",
  f"Will the Netanyahu bloc ({bloc_txt}) win 61 or more seats combined?",
  f"Sum of seats for {bloc_txt} in the final CEC results is at least 61.", FINAL,
  mirrors=["kalshi:KXISRAELBLOCMAJ-26OCT27"])
q("opposition_zionist_61", "blocs", "noul",
  f"Will the Zionist opposition lists ({opp_txt}) win 61 or more seats combined, without the Arab lists?",
  f"Sum of seats for {opp_txt} is at least 61.", FINAL, mirrors=["kalshi:KXISRAELBLOCMAJ-26OCT27"])
q("no_bloc_majority", "blocs", "noul",
  "Will neither the Netanyahu bloc nor the Zionist opposition reach 61 seats on its own?",
  "Both netanyahu_bloc_61 and opposition_zionist_61 resolve false.", FINAL,
  mirrors=["kalshi:KXISRAELBLOCMAJ-26OCT27", "polymarket:israeli-election-results-in-a-hung-parliament"])
q("bloc_most_seats", "blocs", "choice", "Which bloc will win more seats?",
  "Compare the Netanyahu bloc's seats with the Zionist opposition's seats, as defined above.", FINAL,
  {"netanyahu": f"Netanyahu bloc ({bloc_txt})", "opposition": f"Zionist opposition ({opp_txt})"},
  ["kalshi:KXISRAELBLOCMOST-26OCT27"])
bloc_bins = ["50 or fewer", "51-54", "55-57", "58-60", "61-63", "64 or more"]
q("netanyahu_bloc_seats", "blocs", "score", f"How many seats will the Netanyahu bloc ({bloc_txt}) win combined?",
  "Sum of the bloc's seats, binned. Consistency check against the per-list seat questions.", FINAL, bloc_bins)

# 3. Seats per list ------------------------------------------------------------
for name, top in SEAT_LISTS.items():
    # choice, not score: System One caps score questions at 10 options (HTTP 422 from Jev, 2026-10-22),
    # while choice accepted 38. Option keys are seat counts; the top key means "top or more".
    opts = {"0": "0 seats (below the threshold)", **{str(n): f"{n} seats" for n in range(4, top)},
            str(top): f"{top} or more seats"}
    q(f"seats_{slug(name)}", "seats", "choice", f"How many seats will {name} win?",
      f"Seats for {name} in the final CEC results. The option key is the seat count; key {top} means {top} or more.",
      FINAL, opts,
      ([f"kalshi:{KALSHI_COUNT[name]}"] if name in KALSHI_COUNT else [])
      + (["polymarket:israel-election-likud-of-seats"] if name == "Likud" else []))

# 4. Threshold -----------------------------------------------------------------
for name in THRESHOLD_LISTS:
    q(f"passes_{slug(name)}", "threshold", "noul",
      f"Will {name} pass the 3.25% electoral threshold and win seats?",
      f"{name} wins at least one seat in the final CEC results.", FINAL,
      mirrors=["kalshi:KXISRAELANYSEAT-26OCT27"])
q("lists_passing", "threshold", "score", "How many lists will pass the electoral threshold?",
  "Number of lists with at least one seat in the final CEC results.", FINAL,
  ["9 or fewer", "10", "11", "12", "13", "14 or more"])
q("reservists_and_amcha_both_fail", "threshold", "noul",
  "Will both The Reservists and the Economic Party and Amcha Yisrael fail to pass the threshold?",
  "Both lists win 0 seats. Consistency check against their passes_ questions.", FINAL)

# 5. Turnout -------------------------------------------------------------------
q("turnout_below_2022", "turnout", "noul",
  "Will turnout be lower than in the 2022 election (70.6% of eligible voters)?",
  "Official CEC turnout percentage is below 70.63.", FINAL)
q("votes_cast", "turnout", "score", "How many votes will be cast in total?",
  "Total votes cast (CEC), binned.", FINAL,
  ["under 4.9 million", "4.9-5.1 million", "5.1-5.2 million", "5.2-5.3 million",
   "5.3-5.4 million", "5.4-5.5 million", "5.5 million or more"], ["kalshi:KXISRAELTURNOUT-26OCT27"])

# 6. Prime minister ------------------------------------------------------
q("next_pm", "government", "choice",
  "Who will be prime minister of the first government sworn in after this election?",
  f"Prime minister of the first government that wins a Knesset confidence vote after 27 Oct 2026. Resolves 'other' if none by {GOVT}.",
  GOVT, PM_OPTIONS, ["kalshi:KXISRAELPM-26OCT27", "polymarket:who-will-be-the-next-prime-minister-of-israel-after-the-next-election"])
q("netanyahu_remains_pm", "government", "noul",
  "Will Benjamin Netanyahu be prime minister of the first government formed after this election?",
  "Same resolution as next_pm == netanyahu. Consistency pair with next_pm.", GOVT)
q("eisenkot_pm", "government", "noul",
  "Will Gadi Eisenkot be prime minister of the first government formed after this election?",
  "Same resolution as next_pm == eisenkot. Consistency pair with next_pm.", GOVT)

bank = {
    "version": 2,  # v2 2026-10-22: election-only scope; coalition and repercussion questions dropped
    "frozen": None,  # set to the UTC timestamp when the forecast run uses this bank
    "definitions": {
        "netanyahu_bloc": NETANYAHU_BLOC, "opposition_zionist": OPPOSITION_ZIONIST, "arab_lists": ARAB_LISTS,
        "final_results": "Final CEC results for the 26th Knesset (votes26), as certified.",
    },
    "questions": questions,
}
OUT.write_text(json.dumps(bank, indent=2, ensure_ascii=False))
groups = {}
for v in questions.values():
    groups[v["group"]] = groups.get(v["group"], 0) + 1
print(f"{len(questions)} questions -> {OUT}: {groups}")
