Translate each Chinese equity-research claim into concise English, for
the sole purpose of keyword retrieval against an English corpus.

Rules:
- Keep ALL numbers, dates, percentages, currency amounts, fiscal periods
  (Q1/Q2/FY2025), and ticker symbols EXACTLY as written.
- Translate company/segment/metric terms to their standard English
  financial vocabulary (e.g. 民用飞机部门 -> commercial airplanes
  segment, 经营利润 -> operating profit, 召回 -> recall, 上调 ->
  upgrade, 一致预期 -> consensus estimate).
- Output a short English phrase, not a fluent sentence. No explanations.
- Items already in English: copy them unchanged.

# CLAIMS (JSON array)
{items}

Return JSON only:
{{"t": [{{"idx": 0, "en": "<english keywords>"}}, ...]}}
Every input index must appear exactly once.
