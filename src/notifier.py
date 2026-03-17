"""Slack Incoming Webhook を使った通知モジュール。"""

import logging
import os
from collections import defaultdict

import requests

from src.categorizer import CategorizedPaper
from src.config import SUBCATEGORIES, SUBCATEGORY_ORDER, WatchTopic

logger = logging.getLogger(__name__)


def _split_by_topic(
    papers: list[CategorizedPaper],
) -> tuple[dict[str, list[CategorizedPaper]], set[str], list[CategorizedPaper]]:
    """トピック別バケットと、マッチしなかった論文を返す。"""
    topic_buckets: dict[str, list[CategorizedPaper]] = {}
    placed_ids: set[str] = set()
    for p in papers:
        if p.matched_topics:
            label = p.matched_topics[0]
            if p.arxiv_id not in placed_ids:
                topic_buckets.setdefault(label, []).append(p)
                placed_ids.add(p.arxiv_id)
    other_papers = [p for p in papers if p.arxiv_id not in placed_ids]
    return topic_buckets, placed_ids, other_papers


def _build_text(
    date_str: str,
    papers: list[CategorizedPaper],
    notion_url: str,
    topics: list[WatchTopic],
) -> str:
    """Slack メッセージテキストを構築する。"""
    new_count = sum(1 for p in papers if p.announce_type == "new")
    cross_count = sum(1 for p in papers if p.announce_type == "cross")
    parts: list[str] = [
        f"*cs.SE 新着論文 - {date_str}*",
        f"本日 {len(papers)} 件（new: {new_count}, cross: {cross_count}）",
    ]

    topic_buckets, _, other_papers = _split_by_topic(papers)

    # トピック別（登録順、0件も表示）
    for topic in topics:
        bucket = topic_buckets.get(topic.label, [])
        parts.append("")
        parts.append(f"*{topic.label}* ({len(bucket)}件)")
        for p in bucket:
            parts.append(f"- {p.title}")

    # その他（サブカテゴリ別件数）
    by_category: dict[str, int] = defaultdict(int)
    for p in other_papers:
        by_category[p.subcategory] += 1

    parts.append("")
    parts.append(f"*その他* ({len(other_papers)}件)")
    for key in SUBCATEGORY_ORDER:
        count = by_category.get(key, 0)
        if count == 0:
            continue
        cat_name = SUBCATEGORIES[key]
        parts.append(f"- {cat_name}: {count}件")

    # Notion リンク
    if notion_url:
        parts.append("")
        parts.append(f"<{notion_url}|詳細はこちら>")

    return "\n".join(parts)


def notify(
    date_str: str,
    papers: list[CategorizedPaper],
    notion_url: str,
    topics: list[WatchTopic],
) -> None:
    """Slack にサマリーを送信する。"""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("SLACK_WEBHOOK_URL environment variable is not set")

    text = _build_text(date_str, papers, notion_url, topics)
    payload = {
        "text": text,
        "unfurl_links": False,
        "unfurl_media": False,
    }

    response = requests.post(webhook_url, json=payload, timeout=30)
    response.raise_for_status()
    logger.info("Slack notification sent for %s", date_str)


def notify_no_articles(date_str: str) -> None:
    """新着論文がない場合の Slack 通知を送信する。"""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("SLACK_WEBHOOK_URL environment variable is not set")

    payload = {
        "text": f"本日（{date_str}）の cs.SE 新着論文はありませんでした。",
    }

    response = requests.post(webhook_url, json=payload, timeout=30)
    response.raise_for_status()
    logger.info("Slack notification sent: no papers for %s", date_str)


def format_dry_run(
    date_str: str,
    papers: list[CategorizedPaper],
    topics: list[WatchTopic],
) -> str:
    """dry-run 時の標準出力用テキストを生成する。"""
    lines = [f"=== cs.SE arXiv Radar - {date_str} ===", ""]

    if not papers:
        lines.append("No new papers found today.")
        return "\n".join(lines)

    new_count = sum(1 for p in papers if p.announce_type == "new")
    cross_count = sum(1 for p in papers if p.announce_type == "cross")
    lines.append(f"Total: {len(papers)} papers (new: {new_count}, cross: {cross_count})")
    lines.append("")

    topic_buckets, _, other_papers = _split_by_topic(papers)

    # トピック別（登録順、0件も表示）
    for topic in topics:
        bucket = topic_buckets.get(topic.label, [])
        lines.append(f"[{topic.label}] ({len(bucket)}件)")
        for p in bucket:
            lines.append(f"  - {p.title}")
            lines.append(f"    {p.summary}")
            lines.append(f"    {p.url}")
        lines.append("")

    # その他（サブカテゴリ別）
    by_category: dict[str, list[CategorizedPaper]] = defaultdict(list)
    for p in other_papers:
        by_category[p.subcategory].append(p)

    lines.append(f"[その他] ({len(other_papers)}件)")
    for key in SUBCATEGORY_ORDER:
        cat_papers = by_category.get(key, [])
        if not cat_papers:
            continue
        cat_name = SUBCATEGORIES[key]
        lines.append(f"  [{cat_name}] ({len(cat_papers)}件)")
        for p in cat_papers:
            lines.append(f"    - {p.title}")
            lines.append(f"      {p.summary}")
            lines.append(f"      {p.url}")
    lines.append("")

    return "\n".join(lines)
