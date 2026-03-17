"""サブカテゴリ定義と学生トピック読み込み。"""

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SUBCATEGORIES: dict[str, str] = {
    "testing": "Software Testing",
    "msr": "Mining Software Repositories",
    "llm4se": "LLM for SE / Code Generation",
    "maintenance": "Software Maintenance & Evolution",
    "analysis": "Program Analysis",
    "architecture": "Software Architecture",
    "requirements": "Requirements Engineering",
    "empirical": "Empirical Software Engineering",
    "other": "Other",
}

SUBCATEGORY_ORDER = list(SUBCATEGORIES.keys())


@dataclass(frozen=True)
class StudentTopic:
    """学生の研究トピック。"""

    name: str
    keywords: list[str]
    description: str


def load_student_topics() -> list[StudentTopic]:
    """環境変数 STUDENT_TOPICS_JSON から学生トピックを読み込む。"""
    raw = os.environ.get("STUDENT_TOPICS_JSON", "")
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse STUDENT_TOPICS_JSON")
        return []

    topics = []
    for item in data:
        topics.append(
            StudentTopic(
                name=item.get("name", ""),
                keywords=item.get("keywords", []),
                description=item.get("description", ""),
            )
        )
    return topics
