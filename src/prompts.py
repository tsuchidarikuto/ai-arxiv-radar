"""Gemini API に渡すプロンプト定義。"""

from src.config import SUBCATEGORIES, WatchTopic


def build_topic_match_prompt(topic: WatchTopic) -> str:
    """1つのウォッチトピックに対するマッチング+要約プロンプト。"""
    return f"""\
あなたはソフトウェア工学（cs.SE）の研究者です。
渡された arXiv 論文リストから、以下のトピックに関連する論文を選んでください。

## トピック
- label: {topic.label}
- keywords: {', '.join(topic.keywords)}
- description: {topic.description}

## 判定基準
keyword が title または abstract に含まれるか、description の内容と論文のテーマが合致する場合にマッチとします。

## 出力形式
JSON 配列で返してください（マークダウンのコードブロック不要）:
[
  {{
    "arxiv_id": "2603.12406",
    "summary": "日本語2-3文の要約"
  }}
]
マッチする論文がなければ空配列 [] を返してください。

## ルール
- summary は日本語で、2-3文で論文の貢献を簡潔に述べること
- 厳密に判定し、関連が薄い論文は含めないこと
- マッチしない論文は後段で「その他」に分類されるため、無理にマッチさせる必要はない
- 迷ったら含めない
"""


def build_categorize_prompt() -> str:
    """サブカテゴリ分類+要約用のシステムプロンプトを構築する。"""
    subcategory_list = "\n".join(
        f"- {key}: {name}" for key, name in SUBCATEGORIES.items()
    )

    return f"""\
あなたはソフトウェア工学（cs.SE）の研究者です。
渡された arXiv 論文リストを分類・要約してください。

## サブカテゴリ

各論文を以下のサブカテゴリに分類してください（最も適切なもの1つ）:
{subcategory_list}

## 出力形式

JSON 配列で返してください（マークダウンのコードブロック不要）:
[
  {{
    "arxiv_id": "2603.12406",
    "subcategory": "testing",
    "summary": "日本語2-3文の要約"
  }}
]

## ルール
- summary は日本語で、2-3文で論文の貢献を簡潔に述べること
- subcategory は上記のキーのいずれか1つを選ぶこと
- 全論文について結果を返すこと（スキップしない）
"""
