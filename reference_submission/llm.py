"""Thin OpenAI-compatible LLM client.

Reads `ALPHASIGHT_LLM_BASE_URL` + `ALPHASIGHT_LLM_MODEL` (+ optional
`OPENAI_API_KEY` for endpoints that actually require auth).

`chat()` exposes the union of OpenAI Chat Completions fields and the
popular vLLM extras (top_k / repetition_penalty / min_p / guided
decoding / etc.) forwarded via `extra_body`. Anything not covered
explicitly can still go through `extra_body`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMConfig:
    base_url: str | None
    model: str
    api_key: str

    @classmethod
    def from_env(cls) -> "LLMConfig":
        base_url = (
            os.environ.get("ALPHASIGHT_LLM_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
            or os.environ.get("OPENAI_BASE_URL")
        )
        model = os.environ.get("ALPHASIGHT_LLM_MODEL") or "inference-model"
        # 本地 vLLM 默认不校验 api_key；外部端点请设 OPENAI_API_KEY。
        api_key = os.environ.get("OPENAI_API_KEY") or "sk-none"
        return cls(base_url=base_url, model=model, api_key=api_key)


# Fields forwarded to vLLM via `extra_body` (ignored by stock OpenAI).
_VLLM_EXTRA_FIELDS = (
    "top_k",
    "repetition_penalty",
    "min_p",
    "length_penalty",
    "best_of",
    "min_tokens",
    "ignore_eos",
    "stop_token_ids",
    "skip_special_tokens",
    "include_stop_str_in_output",
    "use_beam_search",
    "early_stopping",
    "truncate_prompt_tokens",
    "prompt_logprobs",
    "guided_json",
    "guided_regex",
    "guided_choice",
    "guided_grammar",
)


def chat(
    messages: list[dict],
    *,
    config: LLMConfig | None = None,
    # ---- OpenAI standard sampling ----
    temperature: float = 0.0,
    top_p: float | None = None,
    max_tokens: int = 2048,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
    stop: list[str] | None = None,
    seed: int | None = None,
    n: int | None = None,
    # ---- Structured / JSON output ----
    response_format: dict | None = None,
    # ---- Function calling ----
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
    parallel_tool_calls: bool | None = None,
    # ---- Logprobs / debugging ----
    logprobs: bool | None = None,
    top_logprobs: int | None = None,
    logit_bias: dict[str, float] | None = None,
    user: str | None = None,
    # ---- vLLM extras (forwarded via extra_body) ----
    top_k: int | None = None,
    repetition_penalty: float | None = None,
    min_p: float | None = None,
    length_penalty: float | None = None,
    best_of: int | None = None,
    min_tokens: int | None = None,
    ignore_eos: bool | None = None,
    stop_token_ids: list[int] | None = None,
    skip_special_tokens: bool | None = None,
    include_stop_str_in_output: bool | None = None,
    use_beam_search: bool | None = None,
    early_stopping: bool | str | None = None,
    truncate_prompt_tokens: int | None = None,
    prompt_logprobs: int | None = None,
    guided_json: dict | str | None = None,
    guided_regex: str | None = None,
    guided_choice: list[str] | None = None,
    guided_grammar: str | None = None,
    # ---- Escape hatch + return shape ----
    extra_body: dict | None = None,
    extra_headers: dict | None = None,
    timeout: float | None = None,
    return_full: bool = False,
) -> str | Any:
    """Single-turn chat completion against an OpenAI-compatible endpoint.

    Default returns `choices[0].message.content` (str). Pass
    `return_full=True` to get the raw ChatCompletion back — useful when
    `n>1`, when reading `logprobs`, or when `message.tool_calls` matters.
    """
    cfg = config or LLMConfig.from_env()
    from openai import OpenAI

    client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=timeout)

    kwargs: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for key, val in (
        ("top_p", top_p),
        ("presence_penalty", presence_penalty),
        ("frequency_penalty", frequency_penalty),
        ("stop", stop),
        ("seed", seed),
        ("n", n),
        ("response_format", response_format),
        ("tools", tools),
        ("tool_choice", tool_choice),
        ("parallel_tool_calls", parallel_tool_calls),
        ("logprobs", logprobs),
        ("top_logprobs", top_logprobs),
        ("logit_bias", logit_bias),
        ("user", user),
    ):
        if val is not None:
            kwargs[key] = val

    body = dict(extra_body or {})
    locals_map = locals()
    for fname in _VLLM_EXTRA_FIELDS:
        v = locals_map.get(fname)
        if v is not None:
            body[fname] = v
    if body:
        kwargs["extra_body"] = body
    if extra_headers:
        kwargs["extra_headers"] = extra_headers

    resp = _create_with_retry(client, kwargs)
    if return_full:
        return resp
    return resp.choices[0].message.content or ""


def _create_with_retry(client, kwargs: dict):
    """Resource-pooled endpoints emit sporadic 429/5xx. The provider
    explicitly requires a retry loop: default 5 attempts, 30s apart
    (override via ALPHASIGHT_LLM_RETRIES / ALPHASIGHT_LLM_RETRY_INTERVAL).
    """
    import sys
    import time

    tries = int(os.environ.get("ALPHASIGHT_LLM_RETRIES", "5"))
    interval = float(os.environ.get("ALPHASIGHT_LLM_RETRY_INTERVAL", "30"))
    last: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            status = getattr(e, "status_code", None)
            retryable = (
                status in (408, 409, 429, 500, 502, 503, 504, 529)
                or status is None  # connection/timeout: no status
            )
            last = e
            if attempt >= tries or not retryable:
                raise
            print(f"[llm] attempt {attempt}/{tries} failed "
                  f"(status={status}: {type(e).__name__}); retrying in "
                  f"{interval:.0f}s", file=sys.stderr, flush=True)
            time.sleep(interval)
    raise last  # pragma: no cover
