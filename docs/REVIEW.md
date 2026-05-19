# Review Agent — Design & Processing

How `ReviewAgent` finds injected factual/logical errors in a third‑party
research report and emits `[{quote, reason}]`. This documents the
redesigned pipeline (`reference_submission/agents/review.py`), why each
piece exists, and the offline evidence behind it.

## 1. Task framing

The contest injects errors by taking a true statement from the corpus
and mutating one thing: a digit in an EPS figure, a filing date off by
a few days, a peer‑list member swapped, a return % miscomputed, a
rating change reversed, a source outlet swapped (CNBC→Bloomberg).

Consequences that drive the design:

- The corpus contains the ground truth for nearly every checkable
  claim → this is **claim grounding / fact verification**, not open
  reasoning.
- Error types form a **small closed set**, each with a single
  authoritative source (earnings.json, financials_reported.json,
  peers.json, prices CSV, filing catalog, or the report's own numbers).
- Scoring is issue‑level P/R/F1, ~0–3 errors per report (mean ≈1.4):
  **precision‑first, every miss and every false positive hurts.**

### What was wrong before

The previous pipeline used narrow regex gates that doubled as
detectors, plus one LLM adjudication over everything:

- Wrapped multi‑line claims failed the verbatim‑substring check and
  were dropped before any verifier saw them (the single biggest miss
  source — e.g. report_05/06).
- Table cells and prose lists were never parsed (report_07/08).
- The single LLM pass flipped *confirmed‑correct* deterministic facts
  into false issues (the main FP source in run `output_11_56`).

## 2. Pipeline

`Submission.review` → `ReviewAgent.run(report)`
(`agents/review.py:323`). On any exception it falls back to the
baseline `ExampleSubmission.review`, so `run.py` never crashes.

### 2.1 Anchor — `Anchored(report)` (`agents/anchor.py`)

Builds a whitespace‑collapsed view of the report plus an index map
back to the raw text. Verifiers run on the normalized view
(format‑agnostic); whatever they flag is re‑anchored via `find_raw()`
to the **original raw span**, so the emitted quote stays a verbatim
substring even though the report wraps sentences/bullets/table rows
across newlines. This is the keystone fix for the largest miss class.

### 2.2 Extract — `_extract(anc)` (`agents/review.py:399`)

Regex pass (bullet blocks, table rows `|…|`, sentences, paragraphs)
plus an LLM pass, de‑duplicated through `_good_quote` (whitespace‑
tolerant via `anc.contains`), priority‑sorted, capped at 40. Each
claim carries `quote` / `kind` / `claim_type`.

### 2.3 Subject lock — `_primary_ticker(report)` (`agents/review.py:261`)

Resolves the company the report is about from `(NYSE: XXX)` / `$TICKER`
/ title. Verifiers scope to it so a claim is never checked against the
wrong company's facts.

### 2.4 Typed verifiers

Each verifier pulls its authoritative source, does a structured
comparison, and tags a `tier`:

| Verifier | Authoritative source | Tier |
|---|---|---|
| `_numeric_candidates` EPS branch (`:528`) | research/T/earnings.json | **exact** if period fully pinned, else weak |
| `_numeric_candidates` revenue/net_income | financials_reported.json | **weak** |
| `_date_candidates` (`:598`) | filing catalog | **exact** |
| `_period_end_candidates` (`:633`) | financials_reported.json | **exact** |
| `_price_candidates` (`:664`) | prices/T.csv | **exact** |
| `_peer_candidates` (`:714`) | research/T/peers.json | **exact** |
| `_arithmetic_candidates` QoQ pair (`:770`) | report itself | **weak** |
| `_arithmetic_candidates` close‑to‑close return | report itself | **exact** |
| `_table_candidates` EPS row / nine‑month (`:928`) | earnings / financials | **exact** |

Key correctness fixes baked in:

- `_peer_candidates` scopes by the possessive/primary subject and only
  compares the **explicitly enumerated** list members — the old bug
  queried `peers()` with a *listed peer*, making every peer‑membership
  error invisible, and the loose form fired on correct lists.
- EPS number token requires a decimal and rejects `%`, quarter digits
  (`Q2`), and 4‑digit years; Chinese consensus must use the consensus
  noun (`一致预期`/`市场预期`), never bare `预期` (so `超预期` /
  beat‑verbs no longer parse as a stated estimate).
- `_eps_problems` is gated to real earnings‑result claims (an explicit
  figure or stated consensus) — prose merely containing "miss"/"beat"
  is not checkable.
- Nine‑month financial check has a plausibility band (FactStore concept
  selection is fuzzy for financial filers); it skips rather than emit a
  garbage deterministic issue.

### 2.5 Tiered emission — `run()` (`agents/review.py:323`)

- **exact‑tier → `_veto_exact` → emit directly.**
  `_veto_exact` (`:990`) is an **LLM single‑direction precision gate**:
  it may only *drop* a candidate whose claim was mis‑parsed (a
  price/volume/year taken as EPS, a forecast taken as a reported
  figure, a period/company mismatch). It cannot re‑derive, re‑judge,
  or add; the reason text stays the verifier's authoritative value.
  Any LLM failure, or a degenerate "drop everything" reply, keeps all
  candidates — so the offline (no‑LLM) path is unchanged and the
  precision win can never be wiped by one bad generation.
  Rationale: re‑running exact facts through a *judging* LLM is exactly
  what flipped correct facts into false issues before; a drop‑only
  veto filters mis‑parses without that risk.

- **weak‑tier + narrative → `_retrieval_candidates` → `_adjudicate`.**
  Claims with no deterministic ground truth (source attribution,
  causal/rating reversal, fragile parses) get retrieved evidence and a
  **contradiction‑only** LLM pass (`adjudicate.md`): default verdict is
  NOT an issue; flag only when a specific evidence span explicitly
  refutes the claim. Bounded by `_MAX_NARRATIVE`.

### 2.6 Output

exact (front) then bounded narrative, de‑duplicated by raw quote,
capped at `_MAX_ISSUES`, returned as `list[ReviewIssue(quote, reason)]`.
Every quote is re‑anchored to the original report substring;
`_reason_from` (`:388`) renders the verifier evidence into a
source‑citing reason matching the answer‑key style.

## 3. Prompts

- `prompt_templates/extract_claims.md` — liberal checkable‑claim
  extraction.
- `prompt_templates/adjudicate.md` — rewritten contradiction‑only;
  must cite the refuting span; soft/forecast statements are never
  issues.
- `prompt_templates/verify_exact.md` — drop‑only veto; explicitly
  forbids recompute/re‑judge/add; "when unsure, KEEP".

## 4. Offline results (deterministic, no LLM)

Harness builds `FactStore` + a stub retriever and runs the verifiers
against `problem/review_train*`:

- English report_01/02/03/05/06/07: exact‑tier hits the GT issue, one
  each, **zero false positives** (05/06/07 were previously total
  misses).
- Clean report_14 (GT=0): exact‑tier emits nothing.
- exact total 9 across 20 reports (GT total 28); the few residual
  Chinese‑narrative mis‑parses are demoted to weak or caught by the
  veto gate when an LLM is present.

Full P/R/F1 needs the LLM judge (`tools/eval_review.py`) on a box with
a vLLM endpoint:

```
python run.py review --requests problem/review_train.jsonl
python tools/eval_review.py --pred ../output/review.jsonl \
    --gt problem/review_train_gt.jsonl
```

## 5. Known limitations

- report_08 (nine‑month attributable net income) still missed:
  FactStore's concept selection is unreliable for financial‑sector
  filers; we accept the miss to avoid mass false positives (the
  plausibility band suppresses the FP, not the FN).
- Pure narrative errors (Chinese rating reversal / source swap,
  report_17 class) depend on retrieval surfacing the contradicting
  sentence and the contradiction‑only adjudicator — the hardest class,
  not yet fully solved.
- `dataset/prices_minute` is unused; daily prices suffice for current
  GT price errors. Intraday verification is a possible future
  enhancement to `_price_candidates`.

## 6. Ablation hooks (for the writeup / defense)

- veto gate on/off (exact direct‑emit vs LLM‑filtered).
- adjudicator relevance‑seeking vs contradiction‑only.
- table normalization on/off (report_07/08 class).
- anchoring on/off (multi‑line claim recall).
- deterministic‑only vs +retrieval‑narrative.
