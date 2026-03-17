"""Gemini API を使用した論文分類・要約モジュール。"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Literal

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel, Field

from src.arxiv import Paper
from src.config import SUBCATEGORIES, WatchTopic, load_watch_topics
from src.prompts import build_categorize_prompt, build_topic_match_prompt

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

_FALLBACK_MODEL = "gemini-3.1-flash-lite-preview"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5.0


# --- Pydantic schemas for structured output ---

SubcategoryKey = Literal[tuple(SUBCATEGORIES.keys())]  # type: ignore[valid-type]


class TopicMatchItem(BaseModel):
    arxiv_id: str = Field(description="arXiv ID of the matched paper.")
    summary: str = Field(description="日本語2-3文の要約。")


class TopicMatchResponse(BaseModel):
    matches: list[TopicMatchItem] = Field(
        description="マッチした論文のリスト。マッチする論文がなければ空配列。"
    )


class CategorizeItem(BaseModel):
    arxiv_id: str = Field(description="arXiv ID of the paper.")
    subcategory: SubcategoryKey = Field(description="サブカテゴリのキー。")  # type: ignore[valid-type]
    summary: str = Field(description="日本語2-3文の要約。")


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
    summary: str = ""
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
    return os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite-preview"


def _call_model[T: BaseModel](
    client: genai.Client,
    model_name: str,
    content: str,
    system_prompt: str,
    response_schema: type[T],
) -> T:
    """指定モデルで structured output を呼び出す。503 フォールバック + 429 リトライ付き。"""
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model_name,
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
            if e.code == 503 and model_name != _FALLBACK_MODEL:
                logger.warning(
                    "Model %s returned 503, falling back to %s",
                    model_name,
                    _FALLBACK_MODEL,
                )
                return _call_model(
                    client, _FALLBACK_MODEL, content, system_prompt, response_schema
                )
            raise
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


def categorize_papers(
    papers: list[Paper],
) -> tuple[list[CategorizedPaper], list[WatchTopic]]:
    """トピック別 → サブカテゴリ分類の順で論文を処理する。

    Returns:
        (分類済み論文リスト, ウォッチトピックリスト)
    """
    topics = load_watch_topics()

    if not papers:
        return [], topics

    client = _get_client()
    model = _get_model()

    paper_map = {p.arxiv_id: p for p in papers}
    placed: dict[str, CategorizedPaper] = {}
    remaining_papers = list(papers)

    # トピック別マッチング
    for topic in topics:
        if not remaining_papers:
            break

        system_prompt = build_topic_match_prompt(topic)
        content = _build_papers_content(remaining_papers)

        logger.info(
            "Matching topic '%s' against %d papers with %s",
            topic.label,
            len(remaining_papers),
            model,
        )
        result = _call_model(
            client, model, content, system_prompt, TopicMatchResponse
        )

        matched_ids: set[str] = set()
        for item in result.matches:
            if item.arxiv_id not in paper_map or item.arxiv_id in placed:
                continue
            p = paper_map[item.arxiv_id]
            placed[item.arxiv_id] = CategorizedPaper(
                arxiv_id=p.arxiv_id,
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                url=p.url,
                announce_type=p.announce_type,
                summary=item.summary,
                matched_topics=[topic.label],
            )
            matched_ids.add(item.arxiv_id)
        logger.info("Topic '%s': %d matched", topic.label, len(matched_ids))
        remaining_papers = [
            p for p in remaining_papers if p.arxiv_id not in matched_ids
        ]

    # 残り論文のサブカテゴリ分類
    if remaining_papers:
        system_prompt = build_categorize_prompt()
        content = _build_papers_content(remaining_papers)

        logger.info(
            "Categorizing %d remaining papers with %s",
            len(remaining_papers),
            model,
        )
        result = _call_model(
            client, model, content, system_prompt, CategorizeResponse
        )

        result_map: dict[str, CategorizeItem] = {}
        for item in result.papers:
            result_map[item.arxiv_id] = item

        for p in remaining_papers:
            item = result_map.get(p.arxiv_id)
            placed[p.arxiv_id] = CategorizedPaper(
                arxiv_id=p.arxiv_id,
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                url=p.url,
                announce_type=p.announce_type,
                subcategory=item.subcategory if item else "other",
                summary=item.summary if item else "",
            )

    # 元の論文順を保持
    categorized = [placed[p.arxiv_id] for p in papers if p.arxiv_id in placed]

    logger.info("Categorization complete: %d papers", len(categorized))
    return categorized, topics
