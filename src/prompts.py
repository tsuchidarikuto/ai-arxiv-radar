"""Gemini API に渡すプロンプト定義。"""

from src.config import SUBCATEGORIES


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
