"""Gemini API を使用した論文分類・要約モジュール。"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from src.arxiv import Paper
from src.config import WatchTopic, load_watch_topics
from src.prompts import build_categorize_prompt, build_topic_match_prompt

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

_FALLBACK_MODEL = "gemini-3.1-flash-lite-preview"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5.0


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


def _call_model(
    client: genai.Client, model_name: str, content: str, system_prompt: str
) -> str:
    """指定モデルで generate_content を呼び出す。503 フォールバック + 429 リトライ付き。"""
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=content,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                ),
            )
            return response.text.strip()
        except ServerError as e:
            if e.code == 503 and model_name != _FALLBACK_MODEL:
                logger.warning(
                    "Model %s returned 503, falling back to %s",
                    model_name,
                    _FALLBACK_MODEL,
                )
                return _call_model(client, _FALLBACK_MODEL, content, system_prompt)
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


def _parse_json(raw_text: str) -> Any:
    """Gemini のレスポンスから JSON をパースする。"""
    text = raw_text
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # JSON 文字列内の生改行をエスケープしてリトライ
    try:
        fixed = re.sub(
            r'(?<=": ")(.*?)(?="[,}])',
            lambda m: m.group(0).replace("\n", "\\n"),
            text,
            flags=re.DOTALL,
        )
        return json.loads(fixed)
    except (json.JSONDecodeError, Exception):
        logger.error("Failed to parse JSON: %s", raw_text[:500])
        return None


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
        raw = _call_model(client, model, content, system_prompt)
        results = _parse_json(raw)

        if results and isinstance(results, list):
            matched_ids: set[str] = set()
            for r in results:
                aid = r.get("arxiv_id", "")
                if aid not in paper_map or aid in placed:
                    continue
                p = paper_map[aid]
                placed[aid] = CategorizedPaper(
                    arxiv_id=p.arxiv_id,
                    title=p.title,
                    authors=p.authors,
                    abstract=p.abstract,
                    url=p.url,
                    announce_type=p.announce_type,
                    summary=r.get("summary", ""),
                    matched_topics=[topic.label],
                )
                matched_ids.add(aid)
            logger.info(
                "Topic '%s': %d matched", topic.label, len(matched_ids)
            )
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
        raw = _call_model(client, model, content, system_prompt)
        results = _parse_json(raw)

        result_map: dict[str, dict] = {}
        if results and isinstance(results, list):
            for r in results:
                result_map[r.get("arxiv_id", "")] = r

        for p in remaining_papers:
            r = result_map.get(p.arxiv_id, {})
            placed[p.arxiv_id] = CategorizedPaper(
                arxiv_id=p.arxiv_id,
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                url=p.url,
                announce_type=p.announce_type,
                subcategory=r.get("subcategory", "other"),
                summary=r.get("summary", ""),
            )

    # 元の論文順を保持
    categorized = [placed[p.arxiv_id] for p in papers if p.arxiv_id in placed]

    logger.info("Categorization complete: %d papers", len(categorized))
    return categorized, topics
