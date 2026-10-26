#!/usr/bin/env bash
# Claude Code statusLine
# stdin で session JSON を受け取り、1 行のステータスを ANSI カラーで出力する。
# 表示内容: model | cwd | branch | ctx% | cc 5h/7d limit(→リセット時刻) | cdx limit | cost
# rate_limits は Pro/Max で初回 API 呼び出し後に有効。欠落時は silent に skip。
#
# Claude Code は作業中ずっとこのスクリプトを呼び直す。macOS では外部コマンドを 1 つ起動するたびに
# syspolicyd・ESET・trustd が検査するので、起動するプロセスを jq / git / mv の 3 つに抑えている。
# 値の取り出しと時刻の整形は jq 1 回にまとめ、残りは bash の組み込みで済ませる。

IFS= read -r -d '' input || true

DUMP_DIR="${HOME}/.claude/cache"
DUMP_FILE="${DUMP_DIR}/rate-limit.json"
# Codex の値は codex CLI が最後に観測したもので、ライブではない。
# codex-rate-limit は rollout ログを読んで 5 個前後のプロセスを起動するので、60 秒キャッシュする。
CDX_CACHE="${DUMP_DIR}/codex-rate-limit.json"
CDX_TTL=60
[ -d "$DUMP_DIR" ] || mkdir -p "$DUMP_DIR"
cdx_cache=""
[ -f "$CDX_CACHE" ] && IFS= read -r -d '' cdx_cache < "$CDX_CACHE"

# 時刻の表示形式:
# - 今日中なら HH:MM、日を跨ぐなら M/D HH:MM（「20:00」だけだと今日か明日か紛らわしいため）
# - 7d は数日先が普通なので常に日付付き
# - BSD strftime は %-m 非対応なので %m/%d で出して leading zero を落とす
eval "$(printf '%s' "$input" | jq -rn --arg cdx "$cdx_cache" --argjson ttl "$CDX_TTL" '
  def int: if . == null or . == "" then null else tostring | split(".")[0] end;
  def ep: int | if . == null then null else tonumber end;
  def short($always):
    if . == null then ""
    elif ($always | not) and (strflocaltime("%Y%m%d") == (now | strflocaltime("%Y%m%d")))
      then strflocaltime("%H:%M")
    else strflocaltime("%m/%d %H:%M") | sub("^0"; "") | sub("/0"; "/")
    end;
  def iso: if . == null then null else strflocaltime("%Y-%m-%dT%H:%M:%S%z") end;
  def sh($k; $v): "\($k)=\($v // "" | tostring | @sh)";

  (try input catch null) // {} | (now | floor) as $now
  | ($cdx | try fromjson catch null) as $c
  | ($c.v // {}) as $x
  | (.rate_limits.five_hour.resets_at | ep) as $r5
  | (.rate_limits.seven_day.resets_at | ep) as $r7
  | {
      ctx_pct: (.context_window.used_percentage | int | if . then tonumber else null end),
      five_hour_pct: (.rate_limits.five_hour.used_percentage | int | if . then tonumber else null end),
      five_hour_resets_at: $r5,
      five_hour_resets_at_local: ($r5 | iso),
      seven_day_pct: (.rate_limits.seven_day.used_percentage | int | if . then tonumber else null end),
      seven_day_resets_at: $r7,
      seven_day_resets_at_local: ($r7 | iso),
      cost_usd: (.cost.total_cost_usd // null),
      updated_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ"))
    } as $dump
  | sh("MODEL"; .model.display_name),
    sh("CWD"; .workspace.current_dir),
    sh("CTX"; .context_window.used_percentage | int),
    sh("COST"; .cost.total_cost_usd),
    sh("RATE5"; .rate_limits.five_hour.used_percentage | int),
    sh("RATE7"; .rate_limits.seven_day.used_percentage | int),
    sh("R5_RESET"; $r5 | short(false)),
    sh("R7_RESET"; $r7 | short(true)),
    sh("CDXP5"; $x.five_hour_pct | int),
    sh("CDXP7"; $x.seven_day_pct | int),
    sh("CDX5_RESET"; $x.five_hour_resets_at | ep | short(false)),
    sh("CDX7_RESET"; $x.seven_day_resets_at | ep | short(true)),
    sh("CDX_REACHED"; $x.limit_reached),
    sh("NOW"; $now),
    sh("CDX_STALE"; if ($c.fetched_at // 0) + $ttl <= $now then "1" else "" end),
    sh("DUMP"; $dump | tojson)
' 2>/dev/null)"

# キャッシュが古ければ裏で取り直す。表示は待たせず、次の呼び出しから新しい値を使う。
if [ -n "$CDX_STALE" ]; then
  (
    v=$("${HOME}/.local/bin/codex-rate-limit" 2>/dev/null)
    [ -n "$v" ] || exit 0
    printf '{"fetched_at":%s,"v":%s}\n' "$NOW" "$v" > "$CDX_CACHE.$$" && mv "$CDX_CACHE.$$" "$CDX_CACHE"
  ) >/dev/null 2>&1 &
fi

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
[ -n "$RATE5"    ] && add "$(pct_col "$RATE5")cc 5h ${RATE5}%${R5_RESET:+→$R5_RESET}${R}"
[ -n "$RATE7"    ] && add "$(pct_col "$RATE7")cc 7d ${RATE7}%${R7_RESET:+→$R7_RESET}${R}"
[ -n "$CDX_REACHED" ] && add "${RED}cdx 上限${R}"
[ -n "$CDXP5"    ] && add "$(pct_col "$CDXP5")cdx 5h ${CDXP5}%${CDX5_RESET:+→$CDX5_RESET}${R}"
[ -n "$CDXP7"    ] && add "$(pct_col "$CDXP7")cdx 7d ${CDXP7}%${CDX7_RESET:+→$CDX7_RESET}${R}"
[ -n "$COST"     ] && add "${DIM}\$${COST}${R}"

printf '%s' "$out"

# 95% 自走停止判定用の機械可読 dump。
# Claude assistant が tool (Bash) で `~/.claude/cache/rate-limit.json` を
# 読んで `.five_hour_pct` / `.seven_day_pct` を見て判定し、
# `.five_hour_resets_at` / `.seven_day_resets_at`（epoch 秒。`*_local` は
# ローカル ISO 8601）で次回リミット明けを把握する。詳細は
# `~/.claude/CLAUDE.md`「Rate limit 自走停止」節。
[ -n "$DUMP" ] && { printf '%s\n' "$DUMP" > "$DUMP_FILE.tmp" && mv "$DUMP_FILE.tmp" "$DUMP_FILE"; } 2>/dev/null || true
