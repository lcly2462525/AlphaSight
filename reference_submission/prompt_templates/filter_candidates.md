You are an independent fact-checker. Below are candidate issues flagged
in an equity-research report, plus the authoritative VERIFIED FACTS
(exact values from the structured corpus: earnings.json, financials,
prices, peers, filing catalog). These facts are correct.

Do NOT judge by the wording of the candidate's `reason`. Independently
check each candidate's `quote` against the VERIFIED FACTS yourself.

For each candidate, decide KEEP or DROP:

KEEP if:
- The number / date / direction in the `quote` clearly contradicts a
  specific VERIFIED FACT (a different value, a reversed beat/miss or
  up/down, a wrong filing/event date, a peer not in the list).
- The VERIFIED FACTS do not cover it, BUT the `reason` cites a specific
  source passage sentence giving a concrete contradicting value, date,
  or attributed source (e.g. wrong outlet, wrong filing). Source-
  attribution and timeline errors are often grounded this way — keep them.

DROP if:
- The `quote` is consistent with / matches the VERIFIED FACTS (the
  report is actually right — the candidate is logically backwards).
- The only basis is absence of evidence ("no VERIFIED FACT / no source
  passage provides ...") with no concrete contradicting value given.
- It is an opinion, forecast, valuation, price target, or soft narrative.
- The `quote` is not an assertive factual statement.
- The candidate disputes a precise calculation (EPS actual / consensus /
  surprise, a financial-statement dollar value, a daily price, a price
  return, a ratio, or a percentage derived from two reported figures)
  using only a news passage as evidence. Such claims must be checked
  against the structured VERIFIED FACTS; if the facts agree with the
  report (or are silent), DROP. News alone never overturns arithmetic.

When genuinely unsure, KEEP. Fail toward KEEP.

# AUDIT RUBRIC
{rubric}

# VERIFIED FACTS
{facts}

# CANDIDATES (JSON array)
{items}

Return JSON only:
{{"results": [{{"idx": 0, "action": "keep"}},
              {{"idx": 1, "action": "drop", "why": "<one-line reason>"}}]}}
Every candidate index must appear in results exactly once.
