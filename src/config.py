"""サブカテゴリ定義とウォッチトピック読み込み。"""

import csv
import io
import logging
import os
import re
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

SUBCATEGORIES: dict[str, str] = {
    "testing": "Software Testing",
    "llm4se": "LLM/AI for SE",
    "security": "Software Security",
    "repair": "Program Repair & Debugging",
    "maintenance": "Software Maintenance & Evolution",
    "analysis": "Program Analysis & Verification",
    "devops": "DevOps & Cloud Engineering",
    "requirements": "Requirements & Design",
    "empirical": "Empirical Software Engineering",
    "other": "Other",
}

SUBCATEGORY_ORDER = list(SUBCATEGORIES.keys())


@dataclass(frozen=True)
class WatchTopic:
    """ウォッチトピック。"""

    label: str
    keywords: list[str]
    description: str
    slack_user_id: str = ""


_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "label": ("トピック", "トピック名", "label"),
    "keywords": ("キーワード", "keywords"),
    "description": ("説明", "description"),
    "slack_user_id": ("Slack メンバーID", "Slack ユーザーID", "slack_user_id"),
}

_FALLBACK_INDEX: dict[str, int] = {
    "label": 1,
    "keywords": 2,
    "description": 3,
    "slack_user_id": 4,
}


def _resolve_columns(header: list[str]) -> dict[str, int]:
    normalized = [h.strip() for h in header]
    resolved: dict[str, int] = {}
    for field, aliases in _HEADER_ALIASES.items():
        idx = -1
        for alias in aliases:
            if alias in normalized:
                idx = normalized.index(alias)
                break
        if idx == -1:
            idx = _FALLBACK_INDEX[field]
        resolved[field] = idx
    return resolved


def _cell(row: list[str], idx: int) -> str:
    if 0 <= idx < len(row):
        return row[idx].strip()
    return ""


def load_watch_topics() -> list[WatchTopic]:
    """Google Sheets（CSV エクスポート）からウォッチトピックを読み込む。"""
    sheet_id = os.environ["WATCH_TOPICS_SHEET_ID"]
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    reader = csv.reader(io.StringIO(resp.text))
    header = next(reader, [])
    cols = _resolve_columns(header)

    topics: list[WatchTopic] = []
    for row in reader:
        label = _cell(row, cols["label"])
        if not label:
            continue
        keywords_raw = _cell(row, cols["keywords"])
        keywords = [k.strip() for k in re.split(r"[,，、]", keywords_raw) if k.strip()]
        description = _cell(row, cols["description"])
        slack_user_id = _cell(row, cols["slack_user_id"])
        topics.append(
            WatchTopic(
                label=label,
                keywords=keywords,
                description=description,
                slack_user_id=slack_user_id,
            )
        )

    logger.info("Loaded %d watch topics from Google Sheets", len(topics))
    return topics
