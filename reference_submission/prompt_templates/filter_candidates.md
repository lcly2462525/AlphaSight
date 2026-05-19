You are reviewing a list of candidate issues flagged in an equity-research
report. For each candidate, decide: does the reason actually describe a
REAL factual error in the report?

DROP a candidate if the reason clearly says one of:
1. The value is "correct", "correctly stated", "matches", "aligns with",
   "consistent with", "is acceptable" — the issue is logically backwards
   (the LLM verified the claim as right but still flagged it as an issue)
2. Only "no source passage / no VERIFIED FACT / not provided" with no
   specific contradicting number, date, or direction given — absence of
   evidence is not a contradiction
3. The claim is an opinion, forecast, valuation, price target, or soft
   narrative — these are never factual errors
4. The quote is not an assertive factual statement (it is a question,
   disclaimer, hedge, or forward-looking statement)

KEEP everything else. When unsure, KEEP.
Fail toward KEEP — you need a clear reason to drop.

Candidates (JSON array):
{items}

Return JSON only:
{{"results": [{{"idx": 0, "action": "keep"}},
              {{"idx": 1, "action": "drop", "why": "<one-line reason>"}}]}}
Every candidate index must appear in results exactly once.
