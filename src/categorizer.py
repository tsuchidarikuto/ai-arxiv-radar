"""Gemini API を使用した論文分類・要約モジュール。"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Literal

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel, Field

from src.arxiv import Paper
from src.config import SUBCATEGORIES, WatchTopic, load_watch_topics
from src.prompts import build_categorize_prompt

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

_FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-2.5-flash")
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5.0


# --- Pydantic schemas for structured output ---

SubcategoryKey = Literal[tuple(SUBCATEGORIES.keys())]  # type: ignore[valid-type]


class CategorizeItem(BaseModel):
    arxiv_id: str = Field(description="arXiv ID of the paper.")
    subcategory: SubcategoryKey = Field(description="サブカテゴリのキー。")  # type: ignore[valid-type]
    background: str = Field(
        description="課題・背景（1文、定型句禁止）。abstract に明記がなければ空文字。"
    )
    approach: str = Field(
        description="提案手法・アプローチの核（1文）。abstract に明記がなければ空文字。"
    )
    findings: str = Field(
        description="主要な結果・知見（1〜2文）。具体シグナルを優先。abstract に明記がなければ空文字。"
    )


class CategorizeResponse(BaseModel):
    papers: list[CategorizeItem] = Field(description="分類済み論文のリスト。")


# --- Data class ---


@dataclass
class CategorizedPaper:
    """分類・要約済みの論文。"""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    url: str
    announce_type: str
    subcategory: str = "other"
    background: str = ""
    approach: str = ""
    findings: str = ""
    matched_topics: list[str] = field(default_factory=list)


def _get_client() -> genai.Client:
    """Gemini クライアントを取得する（シングルトン）。"""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is not set")
        _client = genai.Client(api_key=api_key)
    return _client


def _get_model() -> str:
    return os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite"


def _call_model[T: BaseModel](
    client: genai.Client,
    model_name: str,
    content: str,
    system_prompt: str,
    response_schema: type[T],
) -> T:
    """指定モデルで structured output を呼び出す。5xx でモデル fallback + 429 リトライ付き。"""
    seen: set[str] = set()
    models_to_try: list[str] = []
    for m in (model_name, *_FALLBACK_MODELS):
        if m and m not in seen:
            seen.add(m)
            models_to_try.append(m)

    last_error: Exception | None = None
    for current_model in models_to_try:
        for attempt in range(_MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=current_model,
                    contents=content,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_json_schema=response_schema.model_json_schema(),
                    ),
                )
                text = response.text or ""
                return response_schema.model_validate_json(text)
            except ServerError as e:
                last_error = e
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "Model %s returned %s, retrying in %.1fs (%d/%d)",
                        current_model,
                        e.code,
                        delay,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    time.sleep(delay)
                    continue
                logger.warning(
                    "Model %s exhausted retries on %s, trying next fallback",
                    current_model,
                    e.code,
                )
                break
            except ClientError as e:
                if e.code == 429 and attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "Rate limited (429), retrying in %.1fs (%d/%d)",
                        delay,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    time.sleep(delay)
                    continue
                raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Max retries exceeded")


def _build_papers_content(papers: list[Paper]) -> str:
    """論文リストを Gemini に渡す JSON 文字列に変換する。"""
    items = []
    for p in papers:
        items.append({
            "arxiv_id": p.arxiv_id,
            "title": p.title,
            "abstract": p.abstract,
        })
    return json.dumps(items, ensure_ascii=False)


_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """大小文字・連続空白を畳んだ比較用文字列を返す。"""
    return _WS_RE.sub(" ", text.lower())


def _match_topic(paper: Paper, topic: WatchTopic) -> bool:
    """keyword のうち 1 つでも title / abstract に literal 含まれているか。"""
    if not topic.keywords:
        return False
    haystack = _normalize(f"{paper.title} {paper.abstract}")
    return any(_normalize(kw) in haystack for kw in topic.keywords if kw.strip())


def categorize_papers(
    papers: list[Paper],
) -> tuple[list[CategorizedPaper], list[WatchTopic]]:
    """キーワードベースでトピックを割り当て、Gemini でサブカテゴリ+要約を付与する。

    Returns:
        (分類済み論文リスト, ウォッチトピックリスト)
    """
    topics = load_watch_topics()

    if not papers:
        return [], topics

    client = _get_client()
    model = _get_model()

    # 全論文まとめてサブカテゴリ + 要約を Gemini に依頼
    system_prompt = build_categorize_prompt()
    content = _build_papers_content(papers)

    logger.info("Categorizing %d papers with %s", len(papers), model)
    result = _call_model(client, model, content, system_prompt, CategorizeResponse)

    result_map: dict[str, CategorizeItem] = {
        item.arxiv_id: item for item in result.papers
    }

    categorized: list[CategorizedPaper] = []
    topic_counts: dict[str, int] = {t.label: 0 for t in topics}

    for p in papers:
        item = result_map.get(p.arxiv_id)

        matched: list[str] = []
        for topic in topics:
            if _match_topic(p, topic):
                matched.append(topic.label)
                topic_counts[topic.label] += 1
                break  # Sheet 順で先勝ち

        categorized.append(
            CategorizedPaper(
                arxiv_id=p.arxiv_id,
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                url=p.url,
                announce_type=p.announce_type,
                subcategory=item.subcategory if item else "other",
                background=item.background if item else "",
                approach=item.approach if item else "",
                findings=item.findings if item else "",
                matched_topics=matched,
            )
        )

    for label, count in topic_counts.items():
        logger.info("Topic '%s': %d matched", label, count)
    logger.info("Categorization complete: %d papers", len(categorized))
    return categorized, topics
