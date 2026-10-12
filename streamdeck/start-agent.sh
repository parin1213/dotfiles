#!/bin/bash
# herdr で Claude Code か Codex を起動する（Mac の Stream Deck の Claude Code / Codex キーから呼ぶ）。
#   例: start-agent.sh codex
#   Ghostty が前面のとき: herdr で今見ているペインが何も動いていないシェルならそこで起動する。
#                         Claude / Codex などが動いているペインには触らず、同じ Space に同じディレクトリでタブを開いて起動する。
#   それ以外のとき      : ホームディレクトリに新しい Space を作って起動し、Ghostty を前面に出す。
# 引数: $1 = claude | codex（既定 claude）、$2 = 新しい Space の作業ディレクトリ（既定 $HOME）
set -euo pipefail
kind=${1:-claude}
cwd=${2:-$HOME}
case $kind in claude | codex) ;; *) echo "kind は claude か codex: $kind" >&2; exit 2 ;; esac

# Stream Deck から起動されたプロセスは PATH が素の状態なので、mise と Homebrew の置き場所を足す
export PATH="$HOME/.local/share/mise/shims:/opt/homebrew/bin:$PATH"
# 画面なしで動くので、失敗したときに追えるよう直近 1 回分の記録を残す
exec > "${TMPDIR:-/tmp}/start-$kind.log" 2>&1

herdr=$(command -v herdr || ls -d "$HOME"/.local/share/mise/installs/aqua-herdrdev-herdr/*/herdr 2>/dev/null | sort -V | tail -1)
[ -x "$herdr" ] || { echo 'herdr が見つからない'; exit 1; }

# エージェントを起動する。名前は herdr 全体で重複できず、小文字・数字・- _ だけなので、ペイン ID から作る
start_agent() {
  local name out
  name="$kind-$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_-' '-')"
  out=$("$herdr" agent start "$name" --kind "$kind" --pane "$1" --timeout 30000 2>&1) || true
  echo "$out"
  ! grep -qE 'not at|not_at_prompt|pane_busy' <<<"$out"
}

front=$(lsappinfo info -only name "$(lsappinfo front)" | sed -E 's/.*="(.*)"/\1/')
# server 以外の herdr（画面を出しているクライアント）が動いているか
# pgrep -f は複数行のコマンドラインにも当たってしまうので、実行ファイル名が herdr のものだけを見る
client=$(ps -axo args= | awk '$1 ~ /(^|\/)herdr$/ && $2 != "server"')

if [ "$front" = Ghostty ] && [ -n "$client" ]; then
  snap=$("$herdr" api snapshot)
  pane=$(jq -r '.result.snapshot.focused_pane_id' <<<"$snap")
  agent=$(jq -r --arg p "$pane" '.result.snapshot.panes[] | select(.pane_id == $p) | .agent // empty' <<<"$snap")
  # 今のペインを使うのは、前面で動いているのがシェルだけのときに限る。
  # Claude / Codex やエディタが動いているペインに打ち込むと、その作業を壊すため
  others=$("$herdr" pane process-info --pane "$pane" |
    jq '[.result.process_info.foreground_processes[].name | ltrimstr("-") | select(. != "zsh" and . != "bash" and . != "fish" and . != "sh")] | length')
  if [ -z "$agent" ] && [ "$others" = 0 ] && start_agent "$pane"; then exit 0; fi
  # エージェントやほかのプログラムが動いているペインなら、触らずに隣にタブを開く
  ws=$(jq -r --arg p "$pane" '.result.snapshot.panes[] | select(.pane_id == $p) | .workspace_id' <<<"$snap")
  dir=$(jq -r --arg p "$pane" '.result.snapshot.panes[] | select(.pane_id == $p) | .cwd' <<<"$snap")
  tab=$("$herdr" tab create --workspace "$ws" --cwd "$dir" --focus)
  start_agent "$(jq -r '.result.root_pane.pane_id' <<<"$tab")" || true
  exit 0
fi

created=$("$herdr" workspace create --cwd "$cwd" --focus)
start_agent "$(jq -r '.result.root_pane.pane_id' <<<"$created")" || true
# Ghostty は起動時に herdr を開く設定なので、起動していなくても前面化だけで herdr の画面になる
open -a Ghostty
