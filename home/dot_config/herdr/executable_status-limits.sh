#!/usr/bin/env bash
# herdr の tab_bar_right に出す 1 行。Claude Code と Codex の rate limit をまとめる。
# 出力例: used cc 5h4% 7d6% · cdx 7d100%!!→9/20 11:04
#
# 数字はどちらも「使用率」で軸を揃えてある（Codex の payload.rate_limits.used_percent は
# 同じ窓の中で単調増加することを実データで確認済み。残量ではない）。
#
# herdr は status entry の制御文字を落とすので色は付けられない。警戒度は ! / !! で出す。
# 値は各 CLI が最後に観測したもの。30 分以上更新がない側には ~ を付ける。

set -u

CC_CACHE="${HOME}/.claude/cache/rate-limit.json"
CODEX_READER="${HOME}/.local/bin/codex-rate-limit"
STALE_SEC=1800
WARN_PCT=70
CRIT_PCT=90

now=$(date +%s)

reset_short() {
  local e=$1 s
  { [ -z "$e" ] || [ "$e" = null ]; } && return
  if [ "$(date -r "$e" +%Y%m%d 2>/dev/null)" = "$(date +%Y%m%d)" ]; then
    date -r "$e" +%H:%M 2>/dev/null
  else
    s=$(date -r "$e" '+%m/%d %H:%M' 2>/dev/null); s=${s#0}; s=${s/\/0/\/}
    printf '%s' "$s"
  fi
}

# "5h" 4 1789719000 → "5h4%" / 80% 以上なら "5h84%!→17:10"
win() {
  local label=$1 pct=$2 at=$3 out
  { [ -z "$pct" ] || [ "$pct" = null ]; } && return
  pct=${pct%%.*}
  out="${label}${pct}%"
  if [ "$pct" -ge "$CRIT_PCT" ]; then out="${out}!!"
  elif [ "$pct" -ge "$WARN_PCT" ]; then out="${out}!"
  fi
  if [ "$pct" -ge "$WARN_PCT" ]; then
    local r; r=$(reset_short "$at")
    [ -n "$r" ] && out="${out}→${r}"
  fi
  printf '%s' "$out"
}

# tool 名 + 5h/7d の pct と resets_at + 観測時刻 → "cc 5h4% 7d6%"
render() {
  local name=$1 p5=$2 r5=$3 p7=$4 r7=$5 observed=$6 v out
  local parts=()
  v=$(win 5h "$p5" "$r5"); [ -n "$v" ] && parts+=("$v")
  v=$(win 7d "$p7" "$r7"); [ -n "$v" ] && parts+=("$v")
  [ ${#parts[@]} -eq 0 ] && return
  out=""
  { [ -n "$observed" ] && [ "$observed" != null ] && [ $(( now - observed )) -gt "$STALE_SEC" ]; } && out="~"
  printf '%s%s %s' "$out" "$name" "${parts[*]}"
}

cc=""
if [ -r "$CC_CACHE" ]; then
  cc=$(jq -r '[.five_hour_pct, .five_hour_resets_at, .seven_day_pct, .seven_day_resets_at,
               (.updated_at | if . then (sub("\\.[0-9]+Z$";"Z") | fromdateiso8601) else null end)]
              | map(. // "") | join("|")' \
        "$CC_CACHE" 2>/dev/null | { IFS='|' read -r a b c d e && render cc "$a" "$b" "$c" "$d" "$e"; })
fi

cdx=""
if [ -x "$CODEX_READER" ]; then
  cdx=$("$CODEX_READER" | jq -r '[.five_hour_pct, .five_hour_resets_at, .seven_day_pct, .seven_day_resets_at, .observed_at]
                  | map(. // "") | join("|")' 2>/dev/null \
        | { IFS='|' read -r a b c d e && render cdx "$a" "$b" "$c" "$d" "$e"; })
fi

if [ -n "$cc" ] && [ -n "$cdx" ]; then
  printf 'used %s · %s\n' "$cc" "$cdx"
elif [ -n "$cc$cdx" ]; then
  printf 'used %s%s\n' "$cc" "$cdx"
fi
