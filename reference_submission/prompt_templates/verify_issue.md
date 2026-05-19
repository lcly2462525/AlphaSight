You are the VETO check in a two-stage review. Stage 1 already proposed
this candidate as a likely factual/logical error in an equity-research
report. Your job is NOT to re-prove it from scratch — it is only to
DROP it when it is clearly NOT a real error. Default is KEEP.

You are given, focused on THIS one candidate:
- CANDIDATE QUOTE: the exact report statement under suspicion.
- WHY PROPOSED: the first-stage reason it was flagged.
- CLAIM PARSE: a structured reading of the claim (ticker/period/metric/
  value/direction) — use it to find the right VERIFIED FACT.
- VERIFIED FACTS: authoritative exact values from the structured corpus
  (earnings.json / financials / prices / peers / filing catalog).
- SOURCE PASSAGES: retrieved filing/news text.

DROP (verdict "drop") ONLY if one of these clearly holds:
- a VERIFIED FACT or SOURCE PASSAGE actually CONFIRMS the quote (the
  reported number / date / direction matches the authoritative value);
- the discrepancy is only rounding (≤1% or a few cents), fiscal-year
  vs calendar-year labeling, single-quarter vs cumulative phrasing, or
  a restatement — not a real error;
- the quote is a pure opinion, forecast, valuation, or soft narrative
  with no checkable fact;
- the first-stage reason is plainly a mis-parse (e.g. it treated a
  stock price / share count / year as EPS, or the wrong company/
  period), and nothing else makes the quote wrong.

Otherwise KEEP it. In particular, KEEP when a VERIFIED FACT or passage
contradicts the quote, when the quote is internally inconsistent with a
figure it itself cites, or when you are simply unsure — do NOT drop a
plausible error just because evidence is thin. Recall matters here;
this is only a veto for the obviously-not-an-error cases.

# CANDIDATE QUOTE
"""{quote}"""

# WHY PROPOSED
{hint}

# CLAIM PARSE (structured reading; MAY be wrong — use to locate the
# exact VERIFIED FACT to compare against)
{parse}

# VERIFIED FACTS
{facts}

# SOURCE PASSAGES
{evidence}

# OUTPUT
Return JSON only:
{{"verdict": "keep" | "drop", "reason": "<if keep: what is wrong + the correct value, citing the VERIFIED FACT / passage / self-contradiction (refine the first-stage reason). if drop: one brief phrase why it is not an error>"}}
