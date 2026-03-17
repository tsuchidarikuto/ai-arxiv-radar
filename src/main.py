"""AI arXiv Radar のメインエントリーポイント。"""

import argparse
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from src.arxiv import fetch_papers
from src.categorizer import categorize_papers
from src.notion_writer import create_paper_page
from src.notifier import format_dry_run, notify, notify_no_articles
from src.state import filter_new_papers, load_state, mark_processed, save_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI arXiv Radar")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Slack 送信・Notion 書込み・state 更新なし、stdout に結果表示",
    )
    args = parser.parse_args()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. arXiv RSS から論文を取得
    all_papers = fetch_papers()

    # 2. 処理済み ID を除外
    state = load_state()
    new_papers = filter_new_papers(all_papers, state)

    if not new_papers:
        logger.info("No new papers found")
        if not args.dry_run:
            notify_no_articles(today)
        else:
            print("No new papers found today.")
        return

    logger.info("Processing %d new paper(s)", len(new_papers))

    # 3. Gemini で分類・要約・学生マッチ（1回の呼び出し）
    categorized = categorize_papers(new_papers)

    if args.dry_run:
        print(format_dry_run(today, categorized))
        return

    # 4. Notion にページを作成
    notion_url = create_paper_page(categorized)

    # 5. Slack に通知
    notify(today, categorized, notion_url)

    # 6. state を更新・保存
    state = mark_processed(state, new_papers)
    save_state(state)

    logger.info("Done")


if __name__ == "__main__":
    main()
