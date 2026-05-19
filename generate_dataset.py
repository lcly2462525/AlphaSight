import os
import re
import json
import time
import random
import argparse
from pathlib import Path
from typing import List, Dict, Any

from openai import OpenAI


def safe_read(path: Path, max_chars: int = 6000) -> str:
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(errors="ignore"))
            if isinstance(data, dict):
                text = "\n".join(
                    str(data.get(k, ""))
                    for k in ["title", "date", "source", "summary", "content", "body", "text"]
                    if data.get(k)
                )
            else:
                text = json.dumps(data, ensure_ascii=False)
        else:
            text = path.read_text(errors="ignore")

        text = re.sub(r"\s+", " ", text)
        return text[:max_chars]
    except Exception:
        return ""


def collect_files(dataset_root: Path):
    filings = list((dataset_root / "corpus" / "filings").rglob("*"))
    news = list((dataset_root / "corpus" / "news").rglob("*.json"))

    filings = [p for p in filings if p.is_file()]
    news = [p for p in news if p.is_file()]

    return filings, news


def infer_ticker(path: Path) -> str:
    parts = path.parts
    for i, x in enumerate(parts):
        if x in {"filings", "news"} and i + 1 < len(parts):
            return parts[i + 1]
    return "UNKNOWN"


def build_context(filings, news, max_context_chars: int):
    selected = []

    if filings:
        selected += random.sample(filings, min(random.randint(1, 3), len(filings)))
    if news:
        selected += random.sample(news, min(random.randint(3, 8), len(news)))

    chunks = []
    used_files = []

    for p in selected:
        txt = safe_read(p, max_chars=5000)
        if not txt:
            continue

        ticker = infer_ticker(p)
        used_files.append(str(p))

        chunks.append(
            f"\n\n===== SOURCE FILE: {p} =====\n"
            f"TICKER: {ticker}\n"
            f"CONTENT:\n{txt}\n"
        )

    context = "\n".join(chunks)
    return context[:max_context_chars], used_files


REPORT_STYLES = [
    "hedge fund long memo",
    "sell-side equity research note",
    "event-driven catalyst brief",
    "risk-focused short report",
    "earnings reaction memo",
    "valuation-driven investment brief",
    "pipeline and regulatory risk memo",
    "Chinese-English mixed analyst brief",
]


def call_llm(client, model, messages, temperature=0.5, max_tokens=2500, json_mode=False, retry=3):
    last_err = None

    for _ in range(retry):
        try:
            kwargs = dict(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content

        except Exception as e:
            last_err = e
            time.sleep(3)

    raise RuntimeError(f"LLM call failed: {last_err}")


def build_report_prompt(context: str, style: str):
    return f"""
You are generating synthetic training data for financial factuality review.

Write a professional investment research brief based only on the provided evidence.

Style: {style}

Important requirements:
- The report should look realistic and detailed.
- Include summary, key findings, risks, and forward view.
- Use concrete dates, financial figures, product names, regulatory events, market cap, EPS, revenue, guidance, or acquisition details when possible.
- Do not cite source filenames.
- It is acceptable to include some subtle factual mistakes, unsupported extrapolations, or overconfident claims.
- Make the brief 800-1600 words.
- Do not say this is synthetic data.

EVIDENCE:
{context}
"""


def build_review_prompt(context: str, report: str):
    return f"""
You are a strict financial factuality reviewer.

Your task:
Find factual problems in the REPORT by comparing it against the GROUND TRUTH evidence.

Look for:
- wrong dates
- wrong fiscal quarter endings
- unsupported market cap claims
- unsupported acquisition values
- wrong EPS/revenue/guidance numbers
- fabricated product approvals
- fake regulatory milestones
- unsupported CAGR / valuation / dividend claims
- claims that are plausible but not supported by the evidence

Output JSON only in this format:

{{
  "issues": [
    {{
      "quote": "exact problematic quote from report",
      "reason": "why this is wrong or unsupported based on the evidence"
    }}
  ]
}}

If no issue is found, output:
{{"issues":[]}}

GROUND TRUTH:
{context}

REPORT:
{report}
"""


def build_merge_prompt(report_id: str, report: str, context: str, reviews: List[Dict[str, Any]]):
    return f"""
You are the final judge for financial factuality review.

Merge duplicate issues from several reviewers.
Keep only high-quality, evidence-grounded issues.
Remove vague, repetitive, or unsupported criticisms.

Output JSON only:

{{
  "request_id": "{report_id}",
  "issues": [
    {{
      "quote": "exact problematic quote from report",
      "reason": "clear factual reason"
    }}
  ]
}}

GROUND TRUTH:
{context}

REPORT:
{report}

RAW REVIEWS:
{json.dumps(reviews, ensure_ascii=False)}
"""


def parse_json_object(text: str):
    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    return {"issues": []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--num_samples", type=int, default=2000)
    parser.add_argument("--max_context_chars", type=int, default=18000)
    parser.add_argument("--writer_models", type=str, required=True)
    parser.add_argument("--reviewer_models", type=str, required=True)
    parser.add_argument("--judge_model", type=str, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    root = Path(args.root)
    dataset_root = root / "dataset"
    out_root = root / "generatedataset"

    report_dir = out_root / "reports"
    context_dir = out_root / "contexts"
    raw_review_dir = out_root / "raw_reviews"
    final_review_dir = out_root / "reviews"

    for d in [report_dir, context_dir, raw_review_dir, final_review_dir]:
        d.mkdir(parents=True, exist_ok=True)

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
    )

    writer_models = [x.strip() for x in args.writer_models.split(",") if x.strip()]
    reviewer_models = [x.strip() for x in args.reviewer_models.split(",") if x.strip()]

    filings, news = collect_files(dataset_root)

    print(f"[info] filings: {len(filings)}")
    print(f"[info] news: {len(news)}")

    metadata = []

    for idx in range(args.num_samples):
        rid = f"report_{idx:04d}"

        report_path = report_dir / f"{rid}.md"
        context_path = context_dir / f"{rid}_context.txt"
        raw_review_path = raw_review_dir / f"{rid}.json"
        final_review_path = final_review_dir / f"{rid}.jsonl"

        if final_review_path.exists():
            print(f"[skip] {rid}")
            continue

        context, used_files = build_context(
            filings=filings,
            news=news,
            max_context_chars=args.max_context_chars,
        )

        if len(context) < 1000:
            print(f"[warn] empty context for {rid}, skip")
            continue

        writer_model = random.choice(writer_models)
        style = random.choice(REPORT_STYLES)

        print(f"[report] {rid} writer={writer_model} style={style}")

        report = call_llm(
            client,
            writer_model,
            messages=[
                {"role": "user", "content": build_report_prompt(context, style)}
            ],
            temperature=random.uniform(0.7, 1.1),
            max_tokens=3200,
            json_mode=False,
        )

        report_path.write_text(report, encoding="utf-8")
        context_path.write_text(context, encoding="utf-8")

        raw_reviews = []

        for reviewer_model in reviewer_models:
            print(f"[review] {rid} reviewer={reviewer_model}")

            review_text = call_llm(
                client,
                reviewer_model,
                messages=[
                    {"role": "user", "content": build_review_prompt(context, report)}
                ],
                temperature=0.2,
                max_tokens=2200,
                json_mode=True,
            )

            review_json = parse_json_object(review_text)

            raw_reviews.append({
                "model": reviewer_model,
                "review": review_json,
            })

        raw_review_path.write_text(
            json.dumps(raw_reviews, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"[merge] {rid} judge={args.judge_model}")

        merged_text = call_llm(
            client,
            args.judge_model,
            messages=[
                {
                    "role": "user",
                    "content": build_merge_prompt(rid, report, context, raw_reviews),
                }
            ],
            temperature=0.1,
            max_tokens=2500,
            json_mode=True,
        )

        merged = parse_json_object(merged_text)

        if "request_id" not in merged:
            merged["request_id"] = rid
        if "issues" not in merged:
            merged["issues"] = []

        final_review_path.write_text(
            json.dumps(merged, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        metadata.append({
            "request_id": rid,
            "writer_model": writer_model,
            "reviewer_models": reviewer_models,
            "judge_model": args.judge_model,
            "style": style,
            "used_files": used_files,
            "num_issues": len(merged.get("issues", [])),
        })

        (out_root / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"[done] {rid}, issues={len(merged.get('issues', []))}")

    print("[all done]")


if __name__ == "__main__":
    main()