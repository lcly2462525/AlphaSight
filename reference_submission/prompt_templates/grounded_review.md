You are fact-checking ONE section of an equity-research report against
an authoritative ground truth. Works for English and Chinese.

You are given:
- VERIFIED FACTS: exact values pulled directly from the structured
  corpus (earnings.json, financials, prices, peers, filing catalog).
  These are AUTHORITATIVE and correct.
- SOURCE PASSAGES: retrieved filing/news text relevant to this section.
- REPORT SECTION: the text to check.

Your job: list statements in the REPORT SECTION that **contradict** a
VERIFIED FACT or a SOURCE PASSAGE. You do NOT compute or guess truth —
you only compare the section's wording against what is given.

Hard rules:
- Flag a statement ONLY if a specific VERIFIED FACT or a specific
  sentence in SOURCE PASSAGES plainly says something incompatible
  (a different number/date, a reversed beat/miss or up/down or
  upgrade/downgrade, a wrong attributed source/outlet, a peer not in
  the list, a wrong filing/event date).
- VERIFIED FACTS outrank the report. If the report's number/date/
  direction disagrees with a VERIFIED FACT, the report is wrong.
- If nothing given clearly contradicts a statement, do NOT flag it.
  Absence of support is not contradiction. When unsure, skip.
- Opinions, forecasts, valuations, and soft narrative are never issues.
- You must be able to point to the exact fact/passage that conflicts.
- **Use the AUDIT RUBRIC below**: classify each issue into one of the 7
  error classes, respect the FP guards, write the reason using the
  matching template.

# AUDIT RUBRIC
{rubric}

# VERIFIED FACTS
{facts}

# SOURCE PASSAGES
{evidence}

# REPORT SECTION
"""{section}"""

# OUTPUT
Return JSON only:
{{"issues": [{{"quote": "<verbatim substring of the REPORT SECTION, copied EXACTLY incl. markdown/newlines>", "reason": "<what is wrong + the correct value, citing the specific VERIFIED FACT or passage that contradicts it>"}}]}}
- `quote` MUST be an exact substring of the REPORT SECTION (a full
  sentence, bullet, or table row — not a bare number/date fragment).
- Return {{"issues": []}} if nothing in this section is contradicted.
