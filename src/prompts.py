"""Gemini API に渡すプロンプト定義。"""

from src.config import SUBCATEGORIES


def build_categorize_prompt(watch_topics_section: str) -> str:
    """分類+要約+ウォッチトピックマッチ用のシステムプロンプトを構築する。"""
    subcategory_list = "\n".join(
        f"- {key}: {name}" for key, name in SUBCATEGORIES.items()
    )

    topics_section = ""
    if watch_topics_section:
        topics_section = f"""
## ウォッチトピックマッチング

以下のウォッチトピックと照合し、関連する論文があれば matched_topics にトピックの label を列挙してください。
keyword が title または abstract に含まれるか、description の内容と論文のテーマが合致する場合にマッチとします。

{watch_topics_section}

マッチしない場合は空配列にしてください。
"""

    return f"""\
あなたはソフトウェア工学（cs.SE）の研究者です。
渡された arXiv 論文リストを分類・要約してください。

## サブカテゴリ

各論文を以下のサブカテゴリに分類してください（最も適切なもの1つ）:
{subcategory_list}
{topics_section}
## 出力形式

JSON 配列で返してください（マークダウンのコードブロック不要）:
[
  {{
    "arxiv_id": "2603.12406",
    "subcategory": "testing",
    "summary": "日本語2-3文の要約",
    "matched_topics": ["Flaky test"]
  }}
]

## ルール
- summary は日本語で、2-3文で論文の貢献を簡潔に述べること
- subcategory は上記のキーのいずれか1つを選ぶこと
- 全論文について結果を返すこと（スキップしない）
- matched_topics はマッチしなければ空配列
"""
