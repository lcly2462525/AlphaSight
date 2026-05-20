"""Run a full finance-KB A/B generation through GenerateAgent.

This script is meant to be copied to / run on the GPU node where the Qwen
vLLM endpoint is available. It avoids shell heredocs and verifies the main
GenerateAgent path directly, so fallback generation cannot hide failures.

Outputs:
  output_ab/finance_kb_main/no_kb.md
  output_ab/finance_kb_main/with_kb.md
  output_ab/finance_kb_main/diff.md
  output_ab/finance_kb_main/relevant_diff.md
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUBMISSION_DIR = ROOT / "reference_submission"
sys.path.insert(0, str(SUBMISSION_DIR))

from retrieval.finance_kb import FinanceKnowledgeBase  # noqa: E402
from submission import Submission  # noqa: E402


DEFAULT_TOPIC = (
    "NVDA FY2026 Q3 EPS surprise and beat/miss direction, "
    "de-cumulated single-quarter revenue versus YTD revenue, "
    "and 2025 price return."
)

KEY_LINE = re.compile(
    r"eps|surprise|beat|miss|revenue|ytd|year-to-date|single-quarter|"
    r"de-cumul|cumulative|price|close|return|earnings|consensus|estimate",
    re.IGNORECASE,
)


def set_default_env(args: argparse.Namespace) -> None:
    os.environ.setdefault("ALPHASIGHT_CORPUS_DIR", str(ROOT / "dataset/corpus"))
    os.environ.setdefault("ALPHASIGHT_PRICES_DIR", str(ROOT / "dataset/prices"))
    os.environ.setdefault(
        "ALPHASIGHT_PRICES_MINUTE_DIR", str(ROOT / "dataset/prices_minute")
    )
    os.environ.setdefault("ALPHASIGHT_CATALOG_PATH", str(ROOT / "dataset/catalog.jsonl"))
    os.environ.setdefault("ALPHASIGHT_LLM_BASE_URL", args.base_url)
    os.environ.setdefault("ALPHASIGHT_LLM_MODEL", args.model)
    os.environ.setdefault("OPENAI_API_KEY", "sk-none")
    os.environ.setdefault("ALPHASIGHT_LLM_RETRIES", "1")
    os.environ.setdefault("ALPHASIGHT_LLM_TIMEOUT", str(args.timeout))


def relevant_lines(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s and KEY_LINE.search(s):
            out.append(s)
    return out[:80]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_variant(agent, topic: str, *, disable_kb: bool) -> str:
    if disable_kb:
        os.environ["ALPHASIGHT_FINANCE_KB_DISABLE"] = "1"
    else:
        os.environ.pop("ALPHASIGHT_FINANCE_KB_DISABLE", None)
    return agent.run(topic)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--out-dir", default=str(ROOT / "output_ab/finance_kb_main"))
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--model", default="Qwen3-235B-A22B-Instruct-2507")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    set_default_env(args)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("===== CONFIG =====")
    print(f"ROOT={ROOT}")
    print(f"BASE_URL={os.environ.get('ALPHASIGHT_LLM_BASE_URL')}")
    print(f"MODEL={os.environ.get('ALPHASIGHT_LLM_MODEL')}")
    print(f"OUT_DIR={out_dir}")
    print()

    print("===== TOPIC =====")
    print(args.topic)
    print()

    kb = FinanceKnowledgeBase(max_entries=5, max_chars=1200)
    kb_block = kb.block_for(args.topic)
    print("===== KB_BLOCK_FOR_TOPIC_ONLY =====")
    print(kb_block or "(none)")
    print()

    print("===== INIT SUBMISSION =====", flush=True)
    sub = Submission()
    agent = sub._gen_agent
    print()

    try:
        print("===== RUN WITHOUT KB =====", flush=True)
        no_kb = run_variant(agent, args.topic, disable_kb=True)
        write_text(out_dir / "no_kb.md", no_kb)

        print("===== RUN WITH KB =====", flush=True)
        with_kb = run_variant(agent, args.topic, disable_kb=False)
        write_text(out_dir / "with_kb.md", with_kb)
    except Exception:
        traceback.print_exc()
        print()
        print("GenerateAgent main path failed. This script does not fallback.")
        return 1
    finally:
        os.environ.pop("ALPHASIGHT_FINANCE_KB_DISABLE", None)

    diff = "\n".join(
        difflib.unified_diff(
            no_kb.splitlines(),
            with_kb.splitlines(),
            fromfile="no_kb.md",
            tofile="with_kb.md",
            lineterm="",
        )
    )
    write_text(out_dir / "diff.md", diff + ("\n" if diff else ""))

    rel_no = relevant_lines(no_kb)
    rel_yes = relevant_lines(with_kb)
    rel_diff = "\n".join(
        difflib.unified_diff(
            rel_no,
            rel_yes,
            fromfile="no_kb_relevant",
            tofile="with_kb_relevant",
            lineterm="",
        )
    )
    write_text(out_dir / "relevant_diff.md", rel_diff + ("\n" if rel_diff else ""))

    print()
    print("===== OUTPUTS =====")
    print(out_dir / "no_kb.md")
    print(out_dir / "with_kb.md")
    print(out_dir / "diff.md")
    print(out_dir / "relevant_diff.md")
    print()
    print("===== RELEVANT DIFF PREVIEW =====")
    print(rel_diff[:5000] if rel_diff else "(no relevant-line diff)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
