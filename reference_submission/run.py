"""Contestant-facing runner.

Two subcommands; only `--requests` is task-specific. Prompts are
internal to Submission (load whatever you want from prompt_templates/
or elsewhere — the harness doesn't pass anything in).

    python run.py generate --requests problem/generate_free.jsonl
    python run.py review   --requests problem/review_sample.jsonl

`--submission` defaults to the dir this script lives in (so a team
copying `reference_submission/` to their own dir runs their own code
with `python my_submission/run.py`).

Produces:
  - generate → output/generate/<request_id>.md  (raw markdown content)
  - review   → output/review.jsonl              (one line per request)

Scoring happens organizer-side; local output is graded later.

Required env (set yourself or via .env):
    ALPHASIGHT_CORPUS_DIR    ALPHASIGHT_PRICES_DIR    ALPHASIGHT_PRICES_MINUTE_DIR
    ALPHASIGHT_CATALOG_PATH
    ALPHASIGHT_LLM_BASE_URL  ALPHASIGHT_LLM_MODEL
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

_SELF = Path(__file__).resolve().parent
sys.path.insert(0, str(_SELF))
ROOT = _SELF.parent

from schemas import ReviewRequest, Report, GenerateRequest, ReviewIssue  # noqa: E402


def _load_submission_class(bundle: Path, *, class_name: str = "Submission"):
    spec = importlib.util.spec_from_file_location(
        f"submission_{bundle.name}", bundle / "submission.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {bundle / 'submission.py'}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, val = line.partition("=")
        key = key.strip()
        if not sep or not key or key in os.environ:
            continue
        os.environ[key] = val.strip().strip('"').strip("'")


def _wire_env(args) -> None:
    os.environ["ALPHASIGHT_CORPUS_DIR"] = str(args.corpus)
    os.environ["ALPHASIGHT_PRICES_DIR"] = str(args.prices)
    os.environ["ALPHASIGHT_PRICES_MINUTE_DIR"] = str(args.prices_minute)
    os.environ["ALPHASIGHT_CATALOG_PATH"] = str(args.catalog)
    os.environ.setdefault("ALPHASIGHT_OUTPUT_DIR", str(args.out))


def _setup_submission(args):
    if not (args.submission / "submission.py").exists():
        print(f"error: {args.submission}/submission.py not found", file=sys.stderr)
        sys.exit(2)
    _load_dotenv(ROOT / ".env")
    _wire_env(args)
    args.out.mkdir(parents=True, exist_ok=True)
    class_name = "ExampleSubmission" if args.example else "Submission"
    print(f"using {class_name} from {args.submission}/submission.py")
    return _load_submission_class(args.submission, class_name=class_name)()


def cmd_generate(args) -> int:
    sub = _setup_submission(args)
    out_dir = args.out / "generate"
    out_dir.mkdir(exist_ok=True)
    n_ok = n_fail = 0
    for req_path in args.requests:
        if not req_path.exists():
            print(f"[gen] WARN  request file not found: {req_path}", file=sys.stderr)
            continue
        for row in _load_jsonl(req_path):
            req = GenerateRequest.model_validate(row)
            out_file = out_dir / f"{req.request_id}.md"
            if out_file.exists():
                out_file.unlink()
            t0 = time.time()
            try:
                rep = sub.generate(req)
            except Exception as e:
                print(f"[gen] {req.request_id}  FAILED: {type(e).__name__}: {e}")
                n_fail += 1
                continue
            elapsed = time.time() - t0
            if not isinstance(rep, Report):
                print(f"[gen] {req.request_id}  FAILED: returned {type(rep).__name__}, "
                      f"expected Report")
                n_fail += 1
                continue
            out_file.write_text(rep.content, encoding="utf-8")
            print(f"[gen] {req.request_id}  ({elapsed:.1f}s)")
            n_ok += 1
    print(f"\ndone: {n_ok} generate, {n_fail} fail. output → {out_dir}/")
    return 0 if n_fail == 0 else 1


def cmd_review(args) -> int:
    sub = _setup_submission(args)
    n_ok = n_fail = 0
    out_path = args.out / "review.jsonl"
    if not args.requests.exists():
        print(f"error: {args.requests} not found", file=sys.stderr)
        return 2
    with out_path.open("w", encoding="utf-8") as out_fh:
        for row in _load_jsonl(args.requests):
            req = ReviewRequest.model_validate(row)
            t0 = time.time()
            try:
                issues = sub.review(req)
            except Exception as e:
                print(f"[rev] {req.request_id}  FAILED: {type(e).__name__}: {e}")
                n_fail += 1
                continue
            elapsed = time.time() - t0
            if not isinstance(issues, list) or not all(
                isinstance(i, ReviewIssue) for i in issues
            ):
                print(f"[rev] {req.request_id}  FAILED: returned {type(issues).__name__}, "
                      f"expected list[ReviewIssue]")
                n_fail += 1
                continue
            line = {
                "request_id": req.request_id,
                "issues": [i.model_dump() for i in issues],
            }
            out_fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            print(f"[rev] {req.request_id}  ({elapsed:.1f}s, {len(issues)} issues)")
            n_ok += 1
    print(f"\ndone: {n_ok} review, {n_fail} fail. output → {out_path}")
    return 0 if n_fail == 0 else 1


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--submission", type=Path, default=_SELF,
                   help="Bundle dir (default: this script's parent).")
    p.add_argument("--example", action="store_true",
                   help="Use ExampleSubmission instead of Submission "
                        "(smoke-test the pipeline without filling in your own).")
    p.add_argument("--out", type=Path, default=ROOT / "output",
                   help="Output dir (default: %(default)s).")
    p.add_argument("--corpus", type=Path, default=ROOT / "dataset/corpus")
    p.add_argument("--prices", type=Path, default=ROOT / "dataset/prices")
    p.add_argument("--prices-minute", type=Path, default=ROOT / "dataset/prices_minute")
    p.add_argument("--catalog", type=Path, default=ROOT / "dataset/catalog.jsonl")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate", help="Run Submission.generate over a request set.")
    _add_common(p_gen)
    p_gen.add_argument(
        "--requests", type=Path, nargs="+", required=True,
        help="One or more JSONL files of GenerateRequest rows.",
    )

    p_rev = sub.add_parser("review", help="Run Submission.review over a request set.")
    _add_common(p_rev)
    p_rev.add_argument(
        "--requests", type=Path, required=True,
        help="One JSONL file of ReviewRequest rows.",
    )

    args = ap.parse_args(argv)
    if args.cmd == "generate":
        return cmd_generate(args)
    if args.cmd == "review":
        return cmd_review(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
