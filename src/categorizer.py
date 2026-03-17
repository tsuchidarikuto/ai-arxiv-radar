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
from src.prompts import build_categorize_prompt

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

_FALLBACK_MODEL = "gemini-2.5-flash-lite"
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
    return os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"


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


def _build_watch_topics_section(topics: list[WatchTopic]) -> str:
    """ウォッチトピックをプロンプト用テキストに変換する。"""
    if not topics:
        return ""
    lines = []
    for t in topics:
        keywords = ", ".join(t.keywords)
        lines.append(f"- {t.label}: keywords=[{keywords}], description=\"{t.description}\"")
    return "\n".join(lines)


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


def categorize_papers(papers: list[Paper]) -> list[CategorizedPaper]:
    """全論文を1回の Gemini 呼び出しで分類・要約・学生マッチングする。"""
    if not papers:
        return []

    client = _get_client()
    model = _get_model()

    # ウォッチトピック読み込み
    topics = load_watch_topics()
    topics_section = _build_watch_topics_section(topics)
    system_prompt = build_categorize_prompt(topics_section)

    content = _build_papers_content(papers)

    logger.info("Categorizing %d papers with %s", len(papers), model)
    raw = _call_model(client, model, content, system_prompt)
    results = _parse_json(raw)

    # 結果を Paper と結合
    result_map: dict[str, dict] = {}
    if results and isinstance(results, list):
        for r in results:
            aid = r.get("arxiv_id", "")
            result_map[aid] = r

    categorized: list[CategorizedPaper] = []
    for p in papers:
        r = result_map.get(p.arxiv_id, {})
        categorized.append(
            CategorizedPaper(
                arxiv_id=p.arxiv_id,
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                url=p.url,
                announce_type=p.announce_type,
                subcategory=r.get("subcategory", "other"),
                summary=r.get("summary", ""),
                matched_topics=r.get("matched_topics", []),
            )
        )

    logger.info("Categorization complete: %d papers", len(categorized))
    return categorized
