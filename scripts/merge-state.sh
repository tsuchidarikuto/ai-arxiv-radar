#!/usr/bin/env bash
# data/state.json 用の git マージドライバ。
# 競合時に両側の seen_ids を union し、last_checked は新しい方を採用する。
# 状態ファイルの競合は本質的に無意味で、どちらかを捨てると捨てた側の id が
# 再通知される（Slack 重複）ため、union で解決する。
#
# 引数: %O(base) %A(current=出力先) %B(other)
set -euo pipefail

ours="$2"
theirs="$3"

merged=$(jq -s '{
  seen_ids: (.[0].seen_ids + .[1].seen_ids),
  last_checked: ([.[0].last_checked, .[1].last_checked] | map(select(. != null)) | max)
}' "$ours" "$theirs")

printf '%s\n' "$merged" > "$ours"
