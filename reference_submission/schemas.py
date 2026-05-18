"""Pydantic schemas for the two contestant tasks.

Task 1 — generate :  GenerateRequest  →  Report
Task 2 — review   :  ReviewRequest    →  list[ReviewIssue]
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """Generate 任务输入：一道研究题目。"""
    request_id: str
    topic: str


class Report(BaseModel):
    """Generate 任务输出：研究报告 Markdown 正文。"""
    request_id: str
    content: str


class ReviewRequest(BaseModel):
    """Review 任务输入：一份待审研报。

    `request_id` **必须**等于报告文件的 stem（不含 `.md` 后缀），
    例如报告 `report_01_AAPL.md` 对应 `request_id="report_01_AAPL"`。
    判分侧依此与 ground truth 对齐，命名不一致即视为漏检。
    """
    request_id: str
    report_markdown: str


class ReviewIssue(BaseModel):
    """Review 任务输出的一条问题。

    - `quote`：从报告原文逐字摘出的可疑片段
    - `reason`：一两句话说明错在哪 / 应该是什么
    """
    quote: str
    reason: str


class DocMeta(BaseModel):
    """`catalog.jsonl` 一行一条 —— corpus 里每个文件的元数据。"""
    path: str
    kind: Literal["filing", "news", "research", "social"]
    symbols: list[str] = Field(default_factory=list)
    timestamp: str
    form: str | None = None
    source_url: str | None = None
    extra: dict = Field(default_factory=dict)
