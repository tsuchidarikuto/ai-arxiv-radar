"""Slack Incoming Webhook を使った通知モジュール。"""

import logging
import os
from collections import defaultdict

import requests

from src.categorizer import CategorizedPaper
from src.config import SUBCATEGORIES, SUBCATEGORY_ORDER

logger = logging.getLogger(__name__)


def _build_text(
    date_str: str,
    papers: list[CategorizedPaper],
    notion_url: str,
) -> str:
    """Slack メッセージテキストを構築する。"""
    new_count = sum(1 for p in papers if p.announce_type == "new")
    cross_count = sum(1 for p in papers if p.announce_type == "cross")
    parts: list[str] = [
        f"*cs.SE 新着論文 - {date_str}*",
        f"本日 {len(papers)} 件（new: {new_count}, cross: {cross_count}）",
    ]

    # 学生関連
    student_papers = [p for p in papers if p.matched_students]
    if student_papers:
        parts.append("")
        parts.append("*学生関連*")
        for p in student_papers:
            students = ", ".join(f"@{s}" for s in p.matched_students)
            parts.append(f"- {students}: <{p.url}|{p.title}>")

    # カテゴリ別件数
    by_category: dict[str, int] = defaultdict(int)
    for p in papers:
        by_category[p.subcategory] += 1

    parts.append("")
    parts.append("*カテゴリ別*")
    for key in SUBCATEGORY_ORDER:
        count = by_category.get(key, 0)
        if count == 0:
            continue
        cat_name = SUBCATEGORIES[key]
        parts.append(f"- {cat_name}: {count}件")

    # Notion リンク
    if notion_url:
        parts.append("")
        parts.append(f"<{notion_url}|詳細を見る>")

    return "\n".join(parts)


def notify(
    date_str: str,
    papers: list[CategorizedPaper],
    notion_url: str,
) -> None:
    """Slack にサマリーを送信する。"""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("SLACK_WEBHOOK_URL environment variable is not set")

    text = _build_text(date_str, papers, notion_url)
    payload = {"text": text}

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
    date_str: str, papers: list[CategorizedPaper]
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

    # 学生関連
    student_papers = [p for p in papers if p.matched_students]
    if student_papers:
        lines.append("[Student Matches]")
        for p in student_papers:
            students = ", ".join(p.matched_students)
            lines.append(f"  {students}: {p.title}")
            lines.append(f"    {p.summary}")
            lines.append(f"    {p.url}")
        lines.append("")

    # カテゴリ別
    by_category: dict[str, list[CategorizedPaper]] = defaultdict(list)
    for p in papers:
        by_category[p.subcategory].append(p)

    for key in SUBCATEGORY_ORDER:
        cat_papers = by_category.get(key, [])
        if not cat_papers:
            continue
        cat_name = SUBCATEGORIES[key]
        lines.append(f"[{cat_name}] ({len(cat_papers)}件)")
        for p in cat_papers:
            lines.append(f"  - {p.title}")
            lines.append(f"    {p.summary}")
            lines.append(f"    {p.url}")
        lines.append("")

    return "\n".join(lines)
