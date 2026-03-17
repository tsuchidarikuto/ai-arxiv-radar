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


def load_watch_topics() -> list[WatchTopic]:
    """Google Sheets（CSV エクスポート）からウォッチトピックを読み込む。"""
    sheet_id = os.environ["WATCH_TOPICS_SHEET_ID"]
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    reader = csv.reader(io.StringIO(resp.text))
    next(reader)  # ヘッダーをスキップ

    topics: list[WatchTopic] = []
    for row in reader:
        if len(row) < 3 or not row[1].strip():
            continue
        label = row[1].strip()
        keywords = [k.strip() for k in re.split(r"[,，、]", row[2]) if k.strip()]
        description = row[3].strip() if len(row) > 3 else ""
        topics.append(WatchTopic(label=label, keywords=keywords, description=description))

    logger.info("Loaded %d watch topics from Google Sheets", len(topics))
    return topics
