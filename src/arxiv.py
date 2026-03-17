"""arXiv RSS フェッチ・パースモジュール。"""

import logging
import re
from dataclasses import dataclass, field

import feedparser

logger = logging.getLogger(__name__)

ARXIV_RSS_URL = "http://rss.arxiv.org/rss/cs.SE"


@dataclass
class Paper:
    """arXiv 論文のデータ。"""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    url: str
    categories: list[str] = field(default_factory=list)
    announce_type: str = "new"


def _extract_arxiv_id(link: str) -> str:
    """URL から arXiv ID を抽出する。"""
    # http://arxiv.org/abs/2603.12406v1 -> 2603.12406
    match = re.search(r"(\d{4}\.\d{4,5})", link)
    return match.group(1) if match else link


def _clean_abstract(description: str) -> str:
    """RSS description から abstract を抽出する。

    arXiv RSS の description は以下の形式:
    <p>Abstract: ...</p>
    またはメタデータプレフィックス付きの場合もある。
    """
    # HTML タグを除去
    text = re.sub(r"<[^>]+>", "", description)
    # メタデータプレフィックスを除去
    # 形式: "arXiv:2603.12406v1 Announce Type: new \nAbstract: ..."
    text = re.sub(r"^arXiv:\d{4}\.\d{4,5}v\d+\s+Announce Type:\s*\w+\s*", "", text.strip())
    text = re.sub(r"^Abstract:\s*", "", text.strip())
    # 改行を整理
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_announce_type(entry: dict) -> str:
    """RSS エントリから announce_type を抽出する。

    arXiv RSS 2.0 では arxiv:announce_type タグで new/cross/replace を区別する。
    """
    # feedparser は namespace タグを arxiv_announce_type として格納する
    announce_type = getattr(entry, "arxiv_announce_type", None)
    if announce_type:
        return announce_type.strip()

    # description 内に記載される場合
    desc = entry.get("description", "") or entry.get("summary", "")
    match = re.search(r"arXiv:\d{4}\.\d{4,5}.*?\((\w+)\)", desc)
    if match:
        return match.group(1)

    return "new"


def _extract_authors(entry: dict) -> list[str]:
    """RSS エントリから著者リストを抽出する。"""
    # feedparser は author を文字列で返す
    author = entry.get("author", "")
    if not author:
        # dc:creator が使われている場合
        authors_detail = entry.get("authors", [])
        if authors_detail:
            return [a.get("name", "") for a in authors_detail if a.get("name")]
        return []

    # カンマ区切りの著者リスト
    return [a.strip() for a in author.split(",") if a.strip()]


def _extract_categories(entry: dict) -> list[str]:
    """RSS エントリからカテゴリリストを抽出する。"""
    tags = entry.get("tags", [])
    return [t.get("term", "") for t in tags if t.get("term")]


def fetch_papers() -> list[Paper]:
    """arXiv cs.SE の RSS フィードから論文を取得する。

    announce_type が new または cross のみ対象（replace は除外）。
    """
    logger.info("Fetching arXiv RSS: %s", ARXIV_RSS_URL)
    feed = feedparser.parse(ARXIV_RSS_URL)

    if feed.bozo:
        logger.warning("Feed parse warning: %s", feed.bozo_exception)

    papers: list[Paper] = []
    for entry in feed.entries:
        announce_type = _extract_announce_type(entry)

        # replace / replace-cross は除外
        if "replace" in announce_type:
            continue

        link = entry.get("link", "")
        arxiv_id = _extract_arxiv_id(link)
        title = entry.get("title", "").strip()
        # タイトルから arXiv ID プレフィックスを除去
        title = re.sub(r"^arXiv:\d{4}\.\d{4,5}\s*", "", title).strip()
        # タイトルから announce_type サフィックスを除去
        title = re.sub(r"\s*\(\w+\)\s*$", "", title).strip()

        abstract = _clean_abstract(entry.get("description", "") or entry.get("summary", ""))
        authors = _extract_authors(entry)
        categories = _extract_categories(entry)

        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=title,
                authors=authors,
                abstract=abstract,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                categories=categories,
                announce_type=announce_type,
            )
        )

    logger.info("Fetched %d papers (new/cross)", len(papers))
    return papers
