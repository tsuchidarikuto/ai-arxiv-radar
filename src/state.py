"""処理済み arXiv ID の状態管理モジュール。"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "state.json")

_PURGE_DAYS = 30


def load_state() -> dict:
    """状態ファイルを読み込む。"""
    if not os.path.exists(STATE_FILE):
        return {"seen_ids": {}, "last_checked": None}

    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read state file: %s", e)
        return {"seen_ids": {}, "last_checked": None}

    state.setdefault("seen_ids", {})
    return state


def save_state(state: dict) -> None:
    """状態ファイルに保存する。"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    logger.info("State saved to %s", STATE_FILE)


def filter_new_papers(papers: list, state: dict) -> list:
    """処理済み ID を除外して新着論文のみを返す。"""
    seen = state.get("seen_ids", {})
    new_papers = [p for p in papers if p.arxiv_id not in seen]
    logger.info("Filtered: %d total -> %d new papers", len(papers), len(new_papers))
    return new_papers


def mark_processed(state: dict, papers: list) -> dict:
    """論文 ID を状態に記録し、古いエントリをパージする。"""
    seen = state.get("seen_ids", {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for p in papers:
        if p.arxiv_id not in seen:
            seen[p.arxiv_id] = today

    # 30日超をパージ
    purge_cutoff = (datetime.now(timezone.utc) - timedelta(days=_PURGE_DAYS)).strftime(
        "%Y-%m-%d"
    )
    seen = {aid: d for aid, d in seen.items() if d >= purge_cutoff}

    state["seen_ids"] = seen
    state["last_checked"] = datetime.now(timezone.utc).isoformat()
    return state
