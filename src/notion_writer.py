"""Notion DB へのページ作成モジュール。"""

import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

from notion_client import Client

from src.categorizer import CategorizedPaper
from src.config import SUBCATEGORIES, SUBCATEGORY_ORDER, WatchTopic

logger = logging.getLogger(__name__)


def _get_client() -> Client:
    """Notion クライアントを取得する。"""
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        raise RuntimeError("NOTION_API_KEY environment variable is not set")
    return Client(auth=api_key)


def _heading2(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _bulleted_link(title: str, url: str, suffix: str = "") -> dict:
    rich_text = [{"type": "text", "text": {"content": title, "link": {"url": url}}}]
    if suffix:
        rich_text.append({"type": "text", "text": {"content": f"\n{suffix}"}})
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text},
    }


def _build_page_children(
    papers: list[CategorizedPaper],
    topics: list[WatchTopic],
) -> list[dict]:
    """ページ本文ブロックを構築する。

    構造:
      ## トピックA (N件)     -- ウォッチトピック別 H2（0件も表示）
      ## サブカテゴリ (K件) -- 非マッチ論文のサブカテゴリを H2 にフラット化
    """
    children: list[dict] = []

    # トピック別に振り分け
    topic_buckets: dict[str, list[CategorizedPaper]] = {}
    placed_ids: set[str] = set()
    for p in papers:
        if p.matched_topics:
            label = p.matched_topics[0]
            if p.arxiv_id not in placed_ids:
                topic_buckets.setdefault(label, []).append(p)
                placed_ids.add(p.arxiv_id)

    # トピック別 H2（topics の登録順、0件も表示）
    for topic in topics:
        bucket = topic_buckets.get(topic.label, [])
        children.append(_heading2(f"{topic.label} ({len(bucket)}件)"))
        for p in bucket:
            children.append(_bulleted_link(p.title, p.url, p.summary))

    # 非マッチ論文をサブカテゴリ別 H2 でフラットに並べる
    other_papers = [p for p in papers if p.arxiv_id not in placed_ids]
    by_category: dict[str, list[CategorizedPaper]] = defaultdict(list)
    for p in other_papers:
        by_category[p.subcategory].append(p)

    for key in SUBCATEGORY_ORDER:
        cat_papers = by_category.get(key, [])
        if not cat_papers:
            continue
        cat_name = SUBCATEGORIES[key]
        children.append(_heading2(f"{cat_name} ({len(cat_papers)}件)"))
        for p in cat_papers:
            children.append(_bulleted_link(p.title, p.url, p.summary))

    return children


_NOTION_BLOCK_LIMIT = 100


def create_paper_page(
    papers: list[CategorizedPaper],
    topics: list[WatchTopic],
) -> str:
    """Notion DB に論文ページを作成する。

    Returns:
        作成されたページの URL。
    """
    database_id = os.environ.get("NOTION_DATABASE_ID")
    if not database_id:
        raise RuntimeError("NOTION_DATABASE_ID environment variable is not set")

    client = _get_client()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"cs.SE 新着論文 - {today}"

    all_children = _build_page_children(papers, topics)
    first_batch = all_children[:_NOTION_BLOCK_LIMIT]
    remaining = all_children[_NOTION_BLOCK_LIMIT:]

    page = client.pages.create(
        parent={"database_id": database_id},
        properties={
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": today}},
        },
        children=first_batch,
    )

    page_id = page["id"]

    # 100ブロック超はバッチで追加
    while remaining:
        batch = remaining[:_NOTION_BLOCK_LIMIT]
        remaining = remaining[_NOTION_BLOCK_LIMIT:]
        client.blocks.children.append(block_id=page_id, children=batch)

    # 公開 URL を構築（スラッグ付き）
    workspace = os.environ.get("NOTION_WORKSPACE")
    if workspace:
        clean_id = page_id.replace("-", "")
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-")
        page_url = f"https://{workspace}.notion.site/{slug}-{clean_id}"
    else:
        page_url = page.get("url", "")

    logger.info("Created Notion page: %s", page_url)
    return page_url
