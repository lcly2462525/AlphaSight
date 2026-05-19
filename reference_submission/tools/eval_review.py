"""LLM-judge eval for the Review agent against the train answer key.

Exact-substring matching of predicted vs gold quotes is far too strict
(a correct catch is often phrased differently), so an LLM judge aligns
predictions to ground truth by MEANING and we report precision / recall
/ F1 plus a competition-style score.

Usage
-----
    # 1. produce predictions
    python run.py review --requests problem/review_train.jsonl
    # 2. score them
    python tools/eval_review.py \
        --pred ../output/review.jsonl \
        --gt   problem/review_train_gt.jsonl

Judge model: ALPHASIGHT_EVAL_MODEL (default gpt-4.1). Uses the same
retry-wrapped llm.chat as the pipeline, so resource-pool 429/5xx are
handled automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF.parent))

from llm import LLMConfig, chat                       # noqa: E402
from agents._util import load_prompt, parse_json_obj  # noqa: E402


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        k, sep, v = line.partition("=")
        if sep and k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _rows(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        d = json.loads(ln)
        out[d["request_id"]] = d.get("issues", []) or []
    return out


def _fmt(issues: list[dict]) -> str:
    if not issues:
        return "(none)"
    return "\n".join(
        f'[{i}] quote: "{x.get("quote","")}"\n    reason: {x.get("reason","")}'
        for i, x in enumerate(issues))


def _judge(prompt_tpl: str, cfg: LLMConfig, model: str,
           gt: list[dict], pred: list[dict]) -> dict:
    if not gt and not pred:
        return {"matches": [], "unmatched_gt": [], "false_positives": []}
    msg = prompt_tpl.format(gt_block=_fmt(gt), pred_block=_fmt(pred))
    raw = chat([{"role": "user", "content": msg}], config=cfg,
               temperature=0.0, max_tokens=1200,
               response_format={"type": "json_object"})
    d = parse_json_obj(raw)
    d.setdefault("matches", [])
    d.setdefault("unmatched_gt", [])
    d.setdefault("false_positives", [])
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", type=Path, required=True,
                    help="review predictions JSONL (output/review.jsonl)")
    ap.add_argument("--gt", type=Path, required=True,
                    help="ground-truth JSONL (problem/review_train_gt.jsonl)")
    ap.add_argument("--model", default=None,
                    help="judge model (default: $ALPHASIGHT_EVAL_MODEL "
                         "or gpt-4.1)")
    args = ap.parse_args()

    _load_dotenv(_SELF.parent.parent / ".env")
    # The judge is DECOUPLED from the pipeline LLM: the pipeline runs on
    # the local vLLM, scoring runs on the external apicz gateway. Use
    # ALPHASIGHT_EVAL_* (fall back to the pipeline vars only if unset).
    model = (args.model or os.environ.get("ALPHASIGHT_EVAL_MODEL")
             or "gpt-4.1")
    cfg = LLMConfig(
        base_url=(os.environ.get("ALPHASIGHT_EVAL_BASE_URL")
                  or os.environ.get("ALPHASIGHT_LLM_BASE_URL")),
        model=model,
        api_key=(os.environ.get("ALPHASIGHT_EVAL_API_KEY")
                 or os.environ.get("OPENAI_API_KEY") or "sk-none"),
    )
    tpl = load_prompt("eval_match.md")

    preds = _rows(args.pred)
    gts = _rows(args.gt)

    tp = fp = fn = 0
    per_report = []
    for rid, gt in gts.items():
        pred = preds.get(rid, [])
        res = _judge(tpl, cfg, model, gt, pred)
        r_tp = len(res["matches"])
        r_fn = len(res["unmatched_gt"])
        r_fp = len(res["false_positives"])
        # guard against judge miscount
        r_tp = min(r_tp, len(gt), len(pred))
        r_fn = max(len(gt) - r_tp, 0)
        r_fp = max(len(pred) - r_tp, 0)
        tp += r_tp
        fn += r_fn
        fp += r_fp
        per_report.append((rid, len(gt), len(pred), r_tp, r_fp, r_fn))

    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

    print(f"\njudge model: {model}\n")
    print(f"{'report':16} {'GT':>3} {'pred':>4} {'TP':>3} "
          f"{'FP':>3} {'FN':>3}")
    print("-" * 40)
    for rid, ng, npd, t, f, m in per_report:
        print(f"{rid:16} {ng:3d} {npd:4d} {t:3d} {f:3d} {m:3d}")
    print("-" * 40)
    print(f"TOTAL  GT={tp + fn}  pred={tp + fp}  "
          f"TP={tp} FP={fp} FN={fn}")
    print(f"precision={prec:.3f}  recall={rec:.3f}  F1={f1:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
