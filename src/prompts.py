"""Gemini API に渡すプロンプト定義。"""

from src.config import SUBCATEGORIES, WatchTopic


def build_daily_summary_prompt() -> str:
    """日次サマリー+ピックアップ生成用プロンプト。"""
    return """\
あなたはソフトウェア工学（cs.SE）の研究者です。
本日の arXiv 新着論文リスト（タイトルと要約）を読み、以下を生成してください。

## summary
本日の論文全体の傾向を日本語3行でまとめてください。

## picks
特にインパクトのある論文を1件選び、その arXiv ID と日本語1文の要約を返してください。
"""


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

## ルール
- summary は日本語で、2-3文で論文の貢献を簡潔に述べること
- subcategory は上記のキーのいずれか1つを選ぶこと
- 全論文について結果を返すこと（スキップしない）
"""
