#!/usr/bin/env bash
# Claude Code statusLine
# stdin で session JSON を受け取り、1 行のステータスを ANSI カラーで出力する。
# 表示内容: model | cwd | branch | ctx% | 5h limit | 7d limit | cost
# rate_limits は Pro/Max で初回 API 呼び出し後に有効。欠落時は silent に skip。

input=$(cat)
j() { echo "$input" | jq -r "$1 // empty" 2>/dev/null; }

MODEL=$(j '.model.display_name')
CWD=$(j '.workspace.current_dir')
CTX=$(j '.context_window.used_percentage' | cut -d. -f1)
COST=$(j '.cost.total_cost_usd')
RATE5=$(j '.rate_limits.five_hour.used_percentage' | cut -d. -f1)
RATE7=$(j '.rate_limits.seven_day.used_percentage' | cut -d. -f1)

# HOME を ~ に短縮、長ければ末尾 39 文字に省略
# NOTE: ${var/#$HOME/~} は bash が replacement の ~ を tilde expand するので no-op になる
CWD_DISP="$CWD"
[[ "$CWD_DISP" == "$HOME"* ]] && CWD_DISP="~${CWD_DISP#$HOME}"
[ ${#CWD_DISP} -gt 40 ] && CWD_DISP="…${CWD_DISP: -39}"

# git branch (cwd 基準)
BRANCH=""
if [ -n "$CWD" ]; then
  BRANCH=$(git -C "$CWD" branch --show-current 2>/dev/null || true)
fi

# ANSI
R=$'\033[0m'; DIM=$'\033[2m'
MAGENTA=$'\033[35m'; BLUE=$'\033[34m'; CYAN=$'\033[36m'
GREEN=$'\033[32m'; YEL=$'\033[33m'; RED=$'\033[31m'

# % しきい値で色決定: 90+赤 / 70+黄 / それ未満緑 / 欠落 dim
pct_col() {
  local v=$1
  [ -z "$v" ] && { printf '%s' "$DIM"; return; }
  if   [ "$v" -ge 90 ]; then printf '%s' "$RED"
  elif [ "$v" -ge 70 ]; then printf '%s' "$YEL"
  else                        printf '%s' "$GREEN"
  fi
}

out=""
sep=" ${DIM}│${R} "
add() { [ -n "$out" ] && out+="$sep"; out+="$1"; }

[ -n "$MODEL"    ] && add "${MAGENTA}${MODEL}${R}"
[ -n "$CWD_DISP" ] && add "${BLUE}${CWD_DISP}${R}"
[ -n "$BRANCH"   ] && add "${CYAN}⎇ ${BRANCH}${R}"
[ -n "$CTX"      ] && add "$(pct_col "$CTX")ctx ${CTX}%${R}"
[ -n "$RATE5"    ] && add "$(pct_col "$RATE5")5h ${RATE5}%${R}"
[ -n "$RATE7"    ] && add "$(pct_col "$RATE7")7d ${RATE7}%${R}"
[ -n "$COST"     ] && add "${DIM}\$${COST}${R}"

printf '%s' "$out"

# 95% 自走停止判定用の機械可読 dump。
# Claude assistant が tool (Bash) で `~/.claude/cache/rate-limit.json` を
# 読んで `.five_hour_pct` / `.seven_day_pct` を見て判定する。詳細は
# `~/.claude/CLAUDE.md`「Rate limit 自走停止」節。
DUMP_DIR="${HOME}/.claude/cache"
DUMP_FILE="${DUMP_DIR}/rate-limit.json"
mkdir -p "$DUMP_DIR"
nz() { if [ -z "$1" ]; then printf null; else printf '%s' "$1"; fi; }
{
  printf '{'
  printf '"ctx_pct":%s,' "$(nz "$CTX")"
  printf '"five_hour_pct":%s,' "$(nz "$RATE5")"
  printf '"seven_day_pct":%s,' "$(nz "$RATE7")"
  printf '"cost_usd":%s,' "$(nz "$COST")"
  printf '"updated_at":"%s"' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '}\n'
} > "$DUMP_FILE.tmp" && mv "$DUMP_FILE.tmp" "$DUMP_FILE" 2>/dev/null || true
