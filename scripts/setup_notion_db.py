"""Notion DB を親ページ配下に作成するセットアップスクリプト。

使い方:
    NOTION_API_KEY=... NOTION_PARENT_PAGE_ID=... uv run python scripts/setup_notion_db.py
"""

import os
import sys

from dotenv import load_dotenv
from notion_client import Client

load_dotenv()


def main() -> None:
    api_key = os.environ.get("NOTION_API_KEY")
    parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID", "32435508b68a80839dcdd846abfead36")

    if not api_key:
        print("Error: NOTION_API_KEY is required")
        sys.exit(1)

    client = Client(auth=api_key)

    db = client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "arXiv Radar"}}],
        properties={
            "Name": {"title": {}},
            "Date": {"date": {}},
        },
    )

    print(f"Database created: {db['id']}")
    print(f"Set NOTION_DATABASE_ID={db['id']} in your .env file")


if __name__ == "__main__":
    main()
