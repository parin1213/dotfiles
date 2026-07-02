#!/usr/bin/env bash
# skills/setup.sh — manifest.toml を読んでエージェントスキルを導入。
# 通常は chezmoi apply の run_onchange_after_skills-setup（manifest/本ファイルのハッシュ変化時のみ）
# が呼ぶため手動実行は不要。単発で回したいときだけ直接叩く。
#
# 配置先（Agent Skills 仕様準拠の 2 ターゲット）:
#   - Claude   : ~/.claude/skills      （gh skill の --agent claude-code）
#   - 共有     : ~/.agents/skills       （--dir 指定。Codex / Cursor / Gemini CLI 等が読む標準 dir）
#   ※ gh skill の --agent codex は ~/.codex/skills へ入れるが、Codex の標準読み取りは
#     ~/.agents/skills なので、Codex 向けは --dir で .agents/skills に固定する。
#
# 前提: gh(>=2.90・要認証), yq(mise) が PATH 上（同一 apply 内で mise-install が先行する）。
#   type=tool は対応ツールが mise 導入済みのこと。不在なら fail（次の apply が自動リトライ）。
# 手動実行: ./skills/setup.sh
#
# 注: bash 用（WSL / raspi / mac）。Windows ネイティブは PowerShell から同等処理を行う。

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
REPO_ROOT="$(cd "$HERE/.." && pwd -P)"
MAN="$HERE/manifest.toml"
SHARED_DIR="$HOME/.agents/skills"

command -v yq >/dev/null 2>&1 || { echo "ERROR: yq が無い（mise install 後に実行）" >&2; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "ERROR: gh が無い" >&2; exit 1; }
mkdir -p "$SHARED_DIR"

# Claude(~/.claude/skills) と 共有(~/.agents/skills) の両方へ install。
# $1=repo or src, $2=skill name, 残り=共通追加フラグ（--from-local / --pin <v> 等）
install_both() {
  local target="$1" name="$2"; shift 2
  gh skill install "$target" "$name" "$@" --agent claude-code --scope user -f
  gh skill install "$target" "$name" "$@" --dir "$SHARED_DIR" -f
}

n="$(yq -p toml -o yaml '.skill | length' "$MAN")"
for i in $(seq 0 $((n - 1))); do
  name="$(yq -p toml -o yaml ".skill[$i].name" "$MAN")"
  type="$(yq -p toml -o yaml ".skill[$i].type" "$MAN")"

  # requires: 指定バイナリが無い環境では skip（例: playwright skill は playwright-cli が無い raspi では不要）
  req="$(yq -p toml -o yaml ".skill[$i].requires" "$MAN")"
  if [ "$req" != "null" ] && [ -n "$req" ] && ! command -v "$req" >/dev/null 2>&1; then
    echo "==> [$name] requires '$req' 未導入のため skip"
    continue
  fi

  case "$type" in
    tool)
      # ② コマンド付属: ツールの install コマンドが多エージェント配置を担う。未導入なら skip。
      cmd="$(yq -p toml -o yaml ".skill[$i].install" "$MAN")"; bin="${cmd%% *}"
      if ! command -v "$bin" >/dev/null 2>&1; then echo "==> [$name] tool: '$bin' 未導入のため skip"; continue; fi
      echo "==> [$name] tool: $cmd"; eval "$cmd"
      ;;
    ghskill)
      # ③ 信頼 org の repo から pin。Claude＋共有の両方へ。
      repo="$(yq -p toml -o yaml ".skill[$i].repo" "$MAN")"
      skill="$(yq -p toml -o yaml ".skill[$i].skill" "$MAN")"; [ "$skill" = "null" ] && skill="$name"
      pin="$(yq -p toml -o yaml ".skill[$i].pin" "$MAN")"
      echo "==> [$name] ghskill: $repo $skill ${pin:+(pin $pin)}"
      if [ "$pin" != "null" ] && [ -n "$pin" ]; then install_both "$repo" "$skill" --pin "$pin"; else install_both "$repo" "$skill"; fi
      ;;
    own)
      # ① 自作 / ④ 採用 / コマンド同梱の軽量配置: 既定はこのリポ。from でローカルパス指定可（shell 評価）。
      src="$REPO_ROOT"
      fromexpr="$(yq -p toml -o yaml ".skill[$i].from" "$MAN")"
      if [ "$fromexpr" != "null" ] && [ -n "$fromexpr" ]; then
        src="$(eval "echo $fromexpr")"
        [ -d "$src" ] || { echo "==> [$name] own: source '$src' が無いため skip（ツール未導入等）"; continue; }
      fi
      echo "==> [$name] own (from-local: $src)"
      install_both "$src" "$name" --from-local
      ;;
    *) echo "ERROR: unknown type '$type' for skill '$name'" >&2; exit 1;;
  esac
done
echo "==> skills setup done"
