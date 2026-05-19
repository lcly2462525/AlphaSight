You are scoring an automated equity-research REVIEWER against a gold answer key. For ONE report you are given the ground-truth issues (real factual errors planted in the report) and the reviewer's predicted issues.

Match by MEANING, not wording: a predicted issue counts as catching a ground-truth issue if it flags the same underlying factual error (same number/date/claim being wrong), even if the quote substring or phrasing differs. One predicted issue can match at most one ground-truth issue.

# GROUND TRUTH ISSUES
{gt_block}

# PREDICTED ISSUES
{pred_block}

# OUTPUT
Return JSON only:
{{"matches": [{{"gt_index": <int>, "pred_index": <int>}}],
  "unmatched_gt": [<int>...],
  "false_positives": [<int>...]}}
- `matches`: each correctly caught GT issue paired with the predicting issue.
- `unmatched_gt`: GT indices no prediction caught (misses).
- `false_positives`: predicted indices that match no GT issue (spurious flags).
Every GT index appears exactly once (in matches or unmatched_gt); every predicted index appears exactly once (in matches or false_positives).
