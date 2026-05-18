"""Shared helpers: tolerant JSON extraction + prompt loading."""

from __future__ import annotations

import json
import re
from pathlib import Path

_TEMPLATES = Path(__file__).resolve().parent.parent / "prompt_templates"


def load_prompt(name: str) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8")


def parse_json_obj(raw: str) -> dict:
    """Best-effort parse of an LLM JSON reply (handles ```fences```)."""
    if not raw:
        return {}
    txt = raw.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```\w*\n?", "", txt).rstrip("`").rstrip()
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    try:
        data = json.loads(m.group(0) if m else txt)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}
