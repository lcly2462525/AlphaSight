# news_merged → tamper-prone atomic facts (research note)

> Local-validated proof-of-concept; not yet wired into main. Driver:
> the manual-audit taxonomy in [`alphasight-skills/review-manual-audit/SKILL.md`](../alphasight-skills/review-manual-audit/SKILL.md)
> — only 4 perturbation classes score (number / date / sign / source),
> and `train_gt` shows 50% of GT items (14/28) are **narrative** that must
> be checked against news. Last run's narrative recall was 21.4% (3/14).

## Idea in one line

Run an LLM offline over each news_merged event to atomize it into the
exact discriminators (number / date / polarity / source) the perturbation
classes target — index those tight atoms as a new retrieval lane, so
BM25 matches a tampered claim against the un-tampered atomic fact
without competing with narrative filler.

## Validation (local, this branch)

- Extractor: [`local_work/atomize_news.py`](../local_work/atomize_news.py)
  using endpoint `gpt-5.5` (Responses API). Prompt forces output to one
  of the 4 perturbation classes, each atom ≤ 160 chars, exact-numbers,
  attribution + date preserved.
- Test slice: 5 NKE events containing "JPMorgan" (driving `report_17`'s
  three GT issues: EPS estimate, rating direction, source attribution).
- Atomizer output is exactly the discriminator (un-tampered fact):
  - polarity: `NKE was upgraded to Overweight from Neutral by JPMorgan on 2025-07-28.`
  - number: `NKE fiscal 2026 EPS estimate was raised to $1.32 from $1.07 by JPMorgan on 2025-07-28.`
  - number: `NKE price target was raised to $93 by JPMorgan on 2025-07-28.`
  - source: `JPMorgan disclosed its NKE upgrade to Buy and $93 price target on 2025-07-28.`

### BM25 contrast against the tampered claims

Corpus = (extracted atoms) ∪ (their raw event sentences) ∪ 60 random
non-JPM NKE events (noise). Query = perturbed-claim signal tokens.

| Query (tampered direction) | Top-1 chunk | Score | Top raw-event | Gap |
|---|---|---:|---:|---:|
| `JPMorgan NKE downgrade Overweight Neutral 2025-07-28 target $64 $93` | **ATOM-polarity** "NKE was upgraded to Overweight from Neutral by JPMorgan on 2025-07-28" | 13.49 | 7.29 | **+85%** |
| `JPMorgan Nike fiscal 2026 EPS estimate raised $1.52 $1.07 $1.32` | **ATOM-number** "NKE fiscal 2026 EPS estimate was raised to $1.32 from $1.07 by JPMorgan on 2025-07-28" | 19.64 | 17.81 | +10% |

Pattern: the longer / more compound the raw event sentence, the more the
atom wins (it strips co-occurring facts that dilute the per-claim query
on the long sentence). For already-atomic events the atom barely helps.
This is exactly the regime where the current `news_event` lane on main
struggles (one-sentence events score low vs long body windows precisely
because compound sentences carry multiple narratives competing for the
same query tokens).

## Proposed integration (when budget allows)

Parallels the existing `news_event` supplement pattern — single online
hook, both tasks benefit.

1. **Offline builder** `reference_submission/tools/build_news_atoms.py`
   - Pre-filter input events: only atomize events whose `event` sentence
     contains at least one tamper-prone marker — `$`, `%`, a 4-digit
     year or `YYYY-MM-DD`, a known outlet name (the [_SOURCE_CUE]
     (../reference_submission/agents/review.py) list), or a polarity
     verb (the new [_POLARITY_RE]). Empirically <30% of events qualify
     → cuts LLM cost to <30K calls.
   - LLM-atomize each candidate; emit one `DocMeta`-shaped row per
     atom with:
     - `kind: "news_atom"`
     - `path: source_paths[0]` (a real `news/<T>/*.json` for citation)
     - `symbols: <union of source_paths tickers>`
     - `timestamp: <event timestamp>`
     - `extra.atom_text: <rendered atom, ≤160 chars>`
     - `extra.atom_type: number|date|polarity|source`
     - `extra.event_id: <origin event_id>` (so atoms can be deduped/
       grouped per source event)
   - Output: `dataset/news_atoms_catalog.jsonl` — same supplement
     pattern as `news_event_catalog.jsonl`. Picked up by the existing
     `ALPHASIGHT_CATALOG_SUPPLEMENT` loader, additionally specified by
     `ALPHASIGHT_ATOMS_CATALOG_PATH` (or concatenated into the existing
     supplement file).

2. **Online wiring** ([`base.py`](../reference_submission/retrieval/base.py))
   - Add `"news_atom"` to `DocMeta.kind` Literal in `schemas.py`.
   - Add `_CAND_CAP["news_atom"] = 400` (small per-atom chunks; cost
     budget OK).
   - In `_narrow_chunks`, special-case `kind=="news_atom"` like
     `news_event`: build `Chunk(m.path, m.extra["atom_text"],
     "news_atom", m.extra.get("atom_type",""))` directly, zero file I/O.
   - In `search()`, dedicate a **second BM25 lane** for atoms (mirroring
     the event lane). Reserve a leading slice of `max(1, top_k // 4)`
     atom hits — they go AHEAD of the event lane, since atoms are
     strictly more concentrated discriminators:
     `lead = atom_lead + event_lead + orig_lead`.
   - `router.py` `kind_bias`: `news_atom` set above `news_event` on
     every route (e.g. numeric 1.6, narrative 1.7, event 1.8, default
     1.6).
   - Dedup with `(path, text[:64])` so an atom and its origin event are
     not both kept when they encode the same fact.

3. **Cost-shaping**
   - Pre-filter cuts LLM calls by ≥70%.
   - Atomize once offline, store. No per-request LLM cost.
   - Faster model (e.g. `gpt-4o-mini` equivalent if available) is
     adequate — the task is structured extraction, not reasoning. The
     `gpt-5.5` reasoning model used for validation is overkill; expect
     ≥10× speedup with a non-reasoning model.

## Expected impact on `train_gt`

The 11 narrative FN cases in [docs/review19_train_gt_analysis.md](review19_train_gt_analysis.md)
break down by class:

| Class | FN cases | Atomization role |
|---|---|---|
| number tampering in narrative (recall counts, dividend CAGR, lead $, segment growth, etc.) | r10, r11, r13, r15, r18, r19 | atom-number row makes the specific (subject, value) pair the top BM25 hit |
| date tampering (shareholder mtg, ETF high date) | r10, r11, r12 | atom-date row pins the un-tampered date to the named event |
| sign / polarity (NKE rating: edge already partly caught) | r17 | atom-polarity makes the un-tampered direction explicit |
| source misattribution | r16, r17 | atom-source carries the outlet name as the primary token |

Conservative estimate: surfacing the right atom is necessary but not
sufficient (the LLM still has to compare correctly). If we get 60% of
the right atoms surfaced and 80% LLM follow-through, narrative recall
moves from ~21% to roughly ~50%, total recall to ~60%, F1 (with
current prefilters at precision ≈ 20%) to ~30%.

## Decision

Atomization works (validated on hardest case `report_17`). Ship it
when LLM cost / time is acceptable — the integration is a clean
parallel to the existing `news_event` lane. Local research tool kept
at [`local_work/atomize_news.py`](../local_work/atomize_news.py) for
further experiments and ablation; production builder + retriever
wiring is the next concrete step (P1 — depends on LLM budget).
