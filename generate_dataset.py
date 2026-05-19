import os
import re
import json
import time
import random
import argparse
import base64
import mimetypes
import difflib
from pathlib import Path
from html import unescape
from html.parser import HTMLParser
from typing import List, Dict, Any, Tuple

from openai import OpenAI


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TEXT_EXTS = {".txt", ".md", ".csv", ".jsonl"}
HTML_EXTS = {".htm", ".html"}
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGES_PER_SAMPLE = 4
DATA_IMAGE_RE = re.compile(
    r"data:(image/(?:png|jpeg|jpg|gif|webp));base64,([A-Za-z0-9+/=\s]+)",
    flags=re.I,
)


class HTMLTextExtractor(HTMLParser):
    """Small stdlib HTML-to-text extractor that also records image refs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.image_refs: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag in {"p", "div", "tr", "br", "li", "section", "article", "table"}:
            self.parts.append("\n")
        if tag in {"td", "th"}:
            self.parts.append(" | ")
        if tag == "img":
            src = attrs.get("src") or attrs.get("data-src") or ""
            alt = attrs.get("alt") or attrs.get("title") or ""
            if src:
                self.image_refs.append(unescape(src.strip()))
            if alt:
                self.parts.append(f" [IMAGE ALT: {alt.strip()}] ")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() in {"p", "div", "tr", "li", "table"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth and data:
            self.parts.append(data)

    def text(self) -> str:
        return normalize_text(" ".join(self.parts))


def normalize_text(text: str) -> str:
    text = unescape(text)
    text = text.replace("\ufeff", "").replace("\ufffd", "").replace("\x00", "")
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def flatten_json(value: Any, max_chars: int) -> str:
    """Convert nested JSON into compact, readable evidence text."""
    if isinstance(value, dict):
        priority = [
            "title",
            "published_at",
            "date",
            "provider",
            "source",
            "url",
            "symbols",
            "summary",
            "content",
            "body",
            "text",
            "data",
            "_meta",
        ]
        items = []
        seen = set()
        for key in priority:
            if key in value:
                items.append(f"{key}: {flatten_json(value[key], max_chars // 2)}")
                seen.add(key)
        for key, val in value.items():
            if key not in seen:
                items.append(f"{key}: {flatten_json(val, max_chars // 3)}")
        return normalize_text("\n".join(items))[:max_chars]
    if isinstance(value, list):
        rendered = []
        for item in value[:40]:
            rendered.append(flatten_json(item, max(800, max_chars // 20)))
            if sum(len(x) for x in rendered) >= max_chars:
                break
        return normalize_text("\n---\n".join(rendered))[:max_chars]
    return normalize_text(str(value))[:max_chars]


def csv_preview(path: Path, max_chars: int) -> str:
    try:
        import pandas as pd

        df = pd.read_csv(path)
        lines = [f"rows={len(df)} columns={list(df.columns)}"]
        numeric_cols = df.select_dtypes(include="number").columns[:12]
        if len(numeric_cols):
            lines.append("numeric_summary:")
            lines.append(df[numeric_cols].describe().round(4).to_string())
        lines.append("head:")
        lines.append(df.head(12).to_csv(index=False))
        lines.append("tail:")
        lines.append(df.tail(12).to_csv(index=False))
        return normalize_text("\n".join(lines))[:max_chars]
    except Exception as exc:
        return f"[csv read failed: {exc}]"


def parquet_preview(path: Path, max_chars: int) -> str:
    try:
        import pandas as pd

        df = pd.read_parquet(path)
        lines = [f"rows={len(df)} columns={list(df.columns)}"]
        numeric_cols = df.select_dtypes(include="number").columns[:12]
        if len(numeric_cols):
            lines.append("numeric_summary:")
            lines.append(df[numeric_cols].describe().round(4).to_string())
        lines.append("head:")
        lines.append(df.head(12).to_csv(index=False))
        lines.append("tail:")
        lines.append(df.tail(12).to_csv(index=False))
        return normalize_text("\n".join(lines))[:max_chars]
    except Exception as exc:
        return f"[parquet read failed: {exc}]"


def image_payload_from_bytes(raw: bytes, mime_type: str, source: str) -> Dict[str, Any] | None:
    raw = raw[:MAX_IMAGE_BYTES]
    if not raw:
        return None
    data = base64.b64encode(raw).decode("ascii")
    return {
        "source": source,
        "mime_type": mime_type,
        "data_url": f"data:{mime_type};base64,{data}",
    }


def extract_html(path: Path, max_chars: int) -> Tuple[str, List[Dict[str, Any]]]:
    raw = path.read_bytes()
    html = raw.decode("utf-8", errors="ignore")
    images: List[Dict[str, Any]] = []

    def keep_data_image(match):
        if len(images) >= MAX_IMAGES_PER_SAMPLE:
            return "[embedded image omitted]"
        mime_type = match.group(1).lower().replace("jpg", "jpeg")
        b64 = re.sub(r"\s+", "", match.group(2))
        try:
            payload = image_payload_from_bytes(
                base64.b64decode(b64, validate=False),
                mime_type,
                f"{path}#embedded_image_{len(images) + 1}",
            )
            if payload:
                images.append(payload)
                return f"[embedded image {len(images)} extracted for VLM]"
        except Exception:
            pass
        return "[embedded image unreadable]"

    html_without_data = DATA_IMAGE_RE.sub(keep_data_image, html)
    extractor = HTMLTextExtractor()
    extractor.feed(html_without_data)

    for ref in extractor.image_refs:
        if len(images) >= MAX_IMAGES_PER_SAMPLE:
            break
        if ref.lower().startswith(("http://", "https://", "data:")):
            continue
        candidate = (path.parent / ref).resolve()
        try:
            candidate.relative_to(path.parent.resolve())
        except Exception:
            continue
        if candidate.exists() and candidate.suffix.lower() in IMAGE_EXTS:
            mime_type = mimetypes.guess_type(candidate.name)[0] or "image/png"
            payload = image_payload_from_bytes(
                candidate.read_bytes(),
                mime_type,
                str(candidate),
            )
            if payload:
                images.append(payload)

    return extractor.text()[:max_chars], images


def safe_read(path: Path, max_chars: int = 6000) -> Tuple[str, List[Dict[str, Any]]]:
    """Return clean text plus optional image payloads; never pass binary garbage to LLMs."""
    try:
        suffix = path.suffix.lower()
        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            return flatten_json(data, max_chars), []
        if suffix in HTML_EXTS:
            return extract_html(path, max_chars)
        if suffix == ".csv":
            return csv_preview(path, max_chars), []
        if suffix == ".parquet":
            return parquet_preview(path, max_chars), []
        if suffix in IMAGE_EXTS:
            mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
            payload = image_payload_from_bytes(path.read_bytes(), mime_type, str(path))
            return "[image file extracted for VLM]", [payload] if payload else []
        if suffix in TEXT_EXTS or path.stat().st_size < 2_000_000:
            raw_bytes = path.read_bytes()
            if raw_bytes.startswith(b"\xef\xbb\xbf"):
                raw_bytes = raw_bytes[3:]
            return normalize_text(raw_bytes.decode("utf-8", errors="ignore"))[:max_chars], []
        return f"[binary file skipped: {path.name}, {path.stat().st_size} bytes]", []
    except Exception as exc:
        return f"[read failed: {path}: {exc}]", []


def dataset_bucket(path: Path, dataset_root: Path) -> str:
    rel = path.relative_to(dataset_root)
    parts = rel.parts
    if parts[0] == "corpus" and len(parts) > 1:
        return f"corpus/{parts[1]}"
    if parts[0] in {"prices", "prices_minute"}:
        return parts[0]
    return parts[0]


def collect_files(dataset_root: Path) -> List[Dict[str, Any]]:
    """Recursively collect usable data files from the entire dataset, not only filings/news."""
    all_files: List[Dict[str, Any]] = []
    for path in dataset_root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if len(path.relative_to(dataset_root).parts) == 1:
            continue
        suffix = path.suffix.lower()
        if suffix not in {".json", ".jsonl", ".htm", ".html", ".csv", ".parquet", ".md", ".txt", *IMAGE_EXTS}:
            continue
        if path.stat().st_size <= 16:
            continue
        all_files.append({"path": path, "bucket": dataset_bucket(path, dataset_root)})
    return all_files


def infer_ticker(path: Path) -> str:
    parts = path.parts
    for i, x in enumerate(parts):
        if x in {"filings", "news", "social", "research", "prices", "prices_minute"} and i + 1 < len(parts):
            return parts[i + 1]
    return "UNKNOWN"


def infer_kind(path: Path) -> str:
    parts = path.parts
    for x in ("filings", "news", "social", "research", "prices", "prices_minute"):
        if x in parts:
            return x
    return "dataset"


def infer_bucket(path: Path) -> str:
    parts = path.parts
    if "corpus" in parts:
        idx = parts.index("corpus")
        if idx + 1 < len(parts):
            return f"corpus/{parts[idx + 1]}"
    if "prices_minute" in parts:
        return "prices_minute"
    if "prices" in parts:
        return "prices"
    return infer_kind(path)


def sample_four_files(all_files: List[Dict[str, Any]]) -> List[Path]:
    """Stratified random sample so every dataset area can appear over many samples."""
    by_bucket: Dict[str, List[Path]] = {}
    for item in all_files:
        by_bucket.setdefault(item["bucket"], []).append(item["path"])
    buckets = list(by_bucket)
    random.shuffle(buckets)
    selected: List[Path] = []
    for bucket in buckets[:4]:
        selected.append(random.choice(by_bucket[bucket]))
    if len(selected) < 4:
        remaining = [item["path"] for item in all_files if item["path"] not in selected]
        selected.extend(random.sample(remaining, min(4 - len(selected), len(remaining))))
    random.shuffle(selected)
    return selected[:4]


def build_context(all_files: List[Dict[str, Any]], max_context_chars: int):
    """Randomly select 4 files and build text plus VLM image inputs."""
    selected = sample_four_files(all_files)

    chunks = []
    used_files = []
    source_records: List[Dict[str, Any]] = []
    images: List[Dict[str, Any]] = []
    for p in selected:
        txt, file_images = safe_read(p, max_chars=max(2000, max_context_chars // 4))
        if not txt or len(txt) < 20:
            continue
        ticker = infer_ticker(p)
        kind = infer_kind(p)
        bucket = infer_bucket(p)
        used_files.append(str(p))
        source_records.append(
            {
                "path": str(p),
                "ticker": ticker,
                "kind": kind,
                "bucket": bucket,
                "text_chars": len(txt),
                "image_count": len(file_images),
            }
        )
        chunks.append(
            f"\n\n===== SOURCE FILE: {p} =====\n"
            f"TICKER: {ticker}\n"
            f"KIND: {kind}\n"
            f"DATASET_BUCKET: {bucket}\n"
            f"CONTENT:\n{txt}\n"
        )
        for image in file_images:
            if image and len(images) < MAX_IMAGES_PER_SAMPLE:
                images.append(image)

    context = "\n".join(chunks)
    return context[:max_context_chars], used_files, images, source_records


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


def attach_images(messages: List[Dict[str, Any]], images: List[Dict[str, Any]] | None):
    if not images:
        return messages
    patched = [dict(m) for m in messages]
    for idx in range(len(patched) - 1, -1, -1):
        if patched[idx].get("role") != "user":
            continue
        content = patched[idx].get("content", "")
        if isinstance(content, str):
            content_items: List[Dict[str, Any]] = [{"type": "text", "text": content}]
        else:
            content_items = list(content)
        for image in images:
            content_items.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image["data_url"],
                        "detail": "high",
                    },
                }
            )
        patched[idx]["content"] = content_items
        return patched
    return patched


def call_llm(
    client,
    model,
    messages,
    temperature=0.5,
    max_tokens=2500,
    json_mode=False,
    retry=3,
    images: List[Dict[str, Any]] | None = None,
):
    last_err = None

    for _ in range(retry):
        try:
            kwargs = dict(
                model=model,
                messages=attach_images(messages, images),
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
If images are attached, treat them as part of the evidence and use the visible text,
tables, charts, logos, and SEC filing screenshots only when they are legible.

Style: {style}

Important requirements:
- The report should look realistic and detailed.
- Include summary, key findings, risks, and forward view.
- Use concrete dates, financial figures, product names, regulatory events, market cap, EPS, revenue, guidance, or acquisition details when possible.
- Do not cite source filenames.
- Include a few realistic analyst mistakes so the downstream review task is meaningful.
  These should look like normal human oversights, not obvious fabrications:
  overlooking an important caveat or clue in the evidence, conflating similar
  products/segments/companies, mixing up GAAP vs non-GAAP or quarterly vs annual
  figures, misreading small text in a table/chart, confusing dates or fiscal
  periods, transposing digits, decimal points, percentages, or units, or drawing
  an overconfident conclusion from incomplete evidence.
- Keep the mistakes subtle and embedded naturally in an otherwise professional
  brief. Do not explain that you are making mistakes.
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
If images are attached, use them as ground-truth visual evidence too. Do not report
image-derived contradictions unless the visible text/table/chart is clear.

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


def report_quote_units(report: str) -> List[str]:
    units: List[str] = []
    for raw_line in report.splitlines():
        line = normalize_text(raw_line)
        if not line:
            continue
        units.append(line)
        if len(line) > 220 and "|" not in line:
            for sent in re.split(r"(?<=[.!?。！？])\s+", line):
                sent = normalize_text(sent)
                if len(sent) >= 30:
                    units.append(sent)
    seen = set()
    deduped = []
    for unit in units:
        if unit not in seen:
            seen.add(unit)
            deduped.append(unit)
    return deduped


def align_quote_to_report(quote: str, report: str) -> str | None:
    quote = normalize_text(quote)
    if not quote:
        return None
    if quote in report:
        return quote

    units = report_quote_units(report)
    if not units:
        return None

    best_unit = None
    best_score = 0.0
    quote_tokens = set(re.findall(r"[A-Za-z0-9.$%+-]+", quote.lower()))
    for unit in units:
        ratio = difflib.SequenceMatcher(None, quote.lower(), unit.lower()).ratio()
        unit_tokens = set(re.findall(r"[A-Za-z0-9.$%+-]+", unit.lower()))
        overlap = len(quote_tokens & unit_tokens) / max(1, len(quote_tokens))
        score = max(ratio, overlap)
        if score > best_score:
            best_score = score
            best_unit = unit

    if best_unit and best_score >= 0.58:
        return best_unit
    return None


def sanitize_issues(report: str, issues: Any) -> List[Dict[str, str]]:
    clean: List[Dict[str, str]] = []
    seen = set()
    if not isinstance(issues, list):
        return clean
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        aligned = align_quote_to_report(str(issue.get("quote", "")), report)
        reason = normalize_text(str(issue.get("reason", "")))
        if not aligned or not reason:
            continue
        key = (aligned, reason)
        if key in seen:
            continue
        seen.add(key)
        clean.append({"quote": aligned, "reason": reason})
    return clean


def review_has_exact_quotes(report_path: Path, review_path: Path) -> bool:
    try:
        report = report_path.read_text(encoding="utf-8")
        review = json.loads(review_path.read_text(encoding="utf-8"))
        issues = review.get("issues", [])
        if not isinstance(issues, list):
            return False
        return all(isinstance(i, dict) and str(i.get("quote", "")) in report for i in issues)
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--num_samples", type=int, default=2000)
    parser.add_argument("--max_context_chars", type=int, default=18000)
    parser.add_argument("--writer_models", type=str, required=True)
    parser.add_argument("--reviewer_models", type=str, required=True)
    parser.add_argument("--judge_model", type=str, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true", help="regenerate samples even if outputs already exist")
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

    all_files = collect_files(dataset_root)
    print(f"[info] total data files collected: {len(all_files)}")

    metadata = []

    for idx in range(args.num_samples):
        rid = f"report_{idx:04d}"

        report_path = report_dir / f"{rid}.md"
        context_path = context_dir / f"{rid}_context.txt"
        source_manifest_path = context_dir / f"{rid}_sources.json"
        raw_review_path = raw_review_dir / f"{rid}.json"
        final_review_path = final_review_dir / f"{rid}.jsonl"

        if final_review_path.exists() and not args.force and review_has_exact_quotes(report_path, final_review_path):
            print(f"[skip] {rid}")
            continue
        if final_review_path.exists() and not args.force:
            print(f"[rebuild] {rid} existing review has non-exact quotes or invalid JSON")

        context, used_files, images, source_records = build_context(
            all_files=all_files,
            max_context_chars=args.max_context_chars,
        )

        # 上下文至少聚合来自 4 文件，总长度>1000，且没乱码
        if len(used_files) < 4 or len(context) < 1000:
            print(f"[warn] context for {rid} not enough files/content, skip")
            continue

        writer_model = random.choice(writer_models)
        style = random.choice(REPORT_STYLES)

        image_sources = [img["source"] for img in images]

        print(f"[report] {rid} writer={writer_model} style={style} files={len(used_files)} images={len(images)}")

        report = call_llm(
            client,
            writer_model,
            messages=[
                {"role": "user", "content": build_report_prompt(context, style)}
            ],
            temperature=random.uniform(0.7, 1.1),
            max_tokens=3200,
            json_mode=False,
            images=images,
        )

        report_path.write_text(report, encoding="utf-8")
        context_path.write_text(context, encoding="utf-8")
        source_manifest_path.write_text(
            json.dumps(source_records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
                images=images,
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
            images=images,
        )

        merged = parse_json_object(merged_text)

        if "request_id" not in merged:
            merged["request_id"] = rid
        merged["issues"] = sanitize_issues(report, merged.get("issues", []))

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
            "source_records": source_records,
            "image_sources": image_sources,
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
