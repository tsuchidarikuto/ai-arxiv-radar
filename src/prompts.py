"""Gemini API に渡すプロンプト定義。"""

from src.config import SUBCATEGORIES


def build_categorize_prompt(student_topics_section: str) -> str:
    """分類+要約+学生マッチ用のシステムプロンプトを構築する。"""
    subcategory_list = "\n".join(
        f"- {key}: {name}" for key, name in SUBCATEGORIES.items()
    )

    student_section = ""
    if student_topics_section:
        student_section = f"""
## 学生トピックマッチング

以下の学生の研究テーマと照合し、関連する論文があれば matched_students に学生名を列挙してください。
keyword が title または abstract に含まれるか、description の内容と論文のテーマが合致する場合にマッチとします。

{student_topics_section}

マッチしない場合は空配列にしてください。
"""

    return f"""\
あなたはソフトウェア工学（cs.SE）の研究者です。
渡された arXiv 論文リストを分類・要約してください。

## サブカテゴリ

各論文を以下のサブカテゴリに分類してください（最も適切なもの1つ）:
{subcategory_list}
{student_section}
## 出力形式

JSON 配列で返してください（マークダウンのコードブロック不要）:
[
  {{
    "arxiv_id": "2603.12406",
    "subcategory": "testing",
    "summary": "日本語2-3文の要約",
    "matched_students": ["山田太郎"]
  }}
]

## ルール
- summary は日本語で、2-3文で論文の貢献を簡潔に述べること
- subcategory は上記のキーのいずれか1つを選ぶこと
- 全論文について結果を返すこと（スキップしない）
- matched_students はマッチしなければ空配列
"""
