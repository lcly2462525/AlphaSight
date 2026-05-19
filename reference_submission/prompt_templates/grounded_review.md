You are generating CANDIDATE issues for ONE section of an equity-
research report. Works for English and Chinese. A separate strict
verifier will confirm or drop each candidate afterwards, so here you
should favor RECALL — surface anything that plausibly conflicts.

You are given:
- VERIFIED FACTS: exact values pulled directly from the structured
  corpus (earnings.json, financials, prices, peers, filing catalog).
  These are AUTHORITATIVE and correct.
- SOURCE PASSAGES: retrieved filing/news text relevant to this section.
- REPORT SECTION: the text to check.

Your job: list every statement in the REPORT SECTION that **may
contradict** a VERIFIED FACT, a SOURCE PASSAGE, or another statement in
the same section. Compare wording; do not compute new truths.

Guidance:
- Include a candidate when a number / date / EPS beat-or-miss /
  up-or-down / upgrade-or-downgrade / attributed source / peer
  membership / filing or event date / quoted figure looks different
  from a VERIFIED FACT or passage, OR when two statements in the
  section contradict each other.
- VERIFIED FACTS outrank the report.
- Err toward INCLUDING a plausible candidate — the next step verifies
  it. But still skip pure opinions, forecasts, valuations, and soft
  narrative ("we believe", "story stock"); those are never issues.
- Prefer quoting the full sentence / bullet / table row that carries
  the suspect figure.

# VERIFIED FACTS
{facts}

# SOURCE PASSAGES
{evidence}

# REPORT SECTION
"""{section}"""

# OUTPUT
Return JSON only:
{{"issues": [{{"quote": "<verbatim substring of the REPORT SECTION, copied EXACTLY incl. markdown/newlines>", "reason": "<what looks wrong + the fact/passage/other statement it seems to conflict with>"}}]}}
- `quote` MUST be an exact substring of the REPORT SECTION (a full
  sentence, bullet, or table row — not a bare number/date fragment).
- Return {{"issues": []}} only if nothing in this section looks off.
