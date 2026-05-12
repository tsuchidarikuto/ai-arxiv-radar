# ai-arxiv-radar

cs.SE (Software Engineering) の arXiv 新着論文を日次で収集し、Gemini で分類・要約して Notion に記録、Slack に通知する。

## 実行

```bash
uv run python -m src.main --dry-run  # テスト実行
uv run python -m src.main            # 本番実行
```

## 環境変数

`.env` に設定（`.env.example` 参照）。`GEMINI_API_KEY`, `NOTION_API_KEY`, `NOTION_DATABASE_ID`, `SLACK_WEBHOOK_URL` が必須。

## Gemini モデル

デフォルトモデルは `gemini-3.1-flash-lite` を使用する。環境変数 `GEMINI_MODEL` で上書き可能。

## 構成

- `src/config.py` -- サブカテゴリ定義、ウォッチトピック読み込み（Google Sheets 優先、環境変数フォールバック）
- `src/arxiv.py` -- arXiv RSS 取得・パース
- `src/categorizer.py` -- Gemini トピック別マッチング + サブカテゴリ分類（トピック数 + 1 回の呼び出し）
- `src/prompts.py` -- Gemini プロンプト
- `src/notion_writer.py` -- Notion DB 書き込み
- `src/notifier.py` -- Slack 通知
- `src/state.py` -- 重複排除（`data/state.json`）

## Bash

Python は uv 経由で実行する。pip は使わない。
