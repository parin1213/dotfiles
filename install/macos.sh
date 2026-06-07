#!/usr/bin/env bash
# install/macos.sh — macOS 向け初期セットアップ（provision フェーズ）
#
# 役割: mise で入らない OS ネイティブ層だけを入れる。
#   - Homebrew（無ければ公式インストーラ）
#   - Brewfile（mise / starship / ghostty / フォント / ビルド依存）
#   - mise（Brewfile 同梱）と chezmoi（mise 経由）
#   - chezmoi.toml を生成
# CLI/ランタイムの大半は mise が見るので、設定復元（chezmoi apply）時の
# `mise install`（run_onchange）でまとめて入る。ここでは扱わない。
#
# 使い方:
#   cd ~/src/dotfiles && ./install/macos.sh   # または bootstrap（dispatcher 経由）
#   chezmoi diff && chezmoi apply

set -euo pipefail

# このスクリプトの位置（install/）と リポジトリルート（その親）。sourceDir / Brewfile 解決に使う。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

# -----------------------------------------------------------------------------
# 1. Homebrew（無ければ入れる）
# -----------------------------------------------------------------------------
if ! command -v brew >/dev/null 2>&1; then
  echo "==> Homebrew インストール"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # 当該セッションの PATH に brew を載せる（Apple Silicon / Intel 両対応）
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$p" ] && eval "$("$p" shellenv)" && break
  done
fi

# -----------------------------------------------------------------------------
# 2. Brewfile（OS ネイティブ層: mise/starship/ghostty/font/ビルド依存）
# -----------------------------------------------------------------------------
echo "==> brew bundle (install/packages/Brewfile)"
brew bundle --file="$SCRIPT_DIR/packages/Brewfile"

# -----------------------------------------------------------------------------
# 3. mise / chezmoi（鶏卵回避: mise を確実にしてから chezmoi を載せる）
# -----------------------------------------------------------------------------
if ! command -v mise >/dev/null 2>&1; then
  echo "ERROR: mise が見つからない（Brewfile の brew \"mise\" が失敗した?）" >&2
  exit 1
fi
echo "==> mise use -g chezmoi"
mise use -g chezmoi

# -----------------------------------------------------------------------------
# 4. chezmoi sourceDir（このリポジトリの実体位置に自動追従）
# -----------------------------------------------------------------------------
# chezmoi.toml の sourceDir を REPO_ROOT に常に合わせる:
#   一致 → 何も出さない / ズレ・未設定 → sourceDir 行だけ自動書換（他設定は保持）/ 無 → 生成
mkdir -p ~/.config/chezmoi
_toml="$HOME/.config/chezmoi/chezmoi.toml"
_norm() { if [ -d "$1" ]; then (cd "$1" && pwd -P); else printf '%s' "$1"; fi; }
if [ ! -f "$_toml" ]; then
  printf 'sourceDir = "%s"\n' "$REPO_ROOT" > "$_toml"
  echo "==> ~/.config/chezmoi/chezmoi.toml を生成: sourceDir = $REPO_ROOT"
else
  _cur="$(sed -n 's/^[[:space:]]*sourceDir[[:space:]]*=[[:space:]]*"\(.*\)".*/\1/p' "$_toml" | head -n1)"
  if [ "$(_norm "$_cur")" = "$(_norm "$REPO_ROOT")" ]; then
    :  # 既に一致 → 黙る
  elif grep -q '^[[:space:]]*sourceDir[[:space:]]*=' "$_toml"; then
    _tmp="$(mktemp "${TMPDIR:-/tmp}/chezmoitoml.XXXXXX")"
    sed "s|^[[:space:]]*sourceDir[[:space:]]*=.*|sourceDir = \"$REPO_ROOT\"|" "$_toml" > "$_tmp" && mv "$_tmp" "$_toml"
    echo "==> chezmoi.toml の sourceDir を追従: ${_cur:-未設定} -> $REPO_ROOT"
  else
    printf 'sourceDir = "%s"\n%s' "$REPO_ROOT" "$(cat "$_toml")" > "$_toml"
    echo "==> chezmoi.toml に sourceDir を追記: $REPO_ROOT"
  fi
  unset _cur
fi
unset _toml
unset -f _norm

# -----------------------------------------------------------------------------
# 5. 案内（本当に必要なステップだけ出す: 差分があれば apply、非 zsh なら exec zsh）
# -----------------------------------------------------------------------------
echo
echo "==> macOS ブートストラップ完了。"
# 以降は本当に必要なステップだけ出す（無ければ完了表示のみ）。
# chezmoi を解決（mise 経由）。解決不能 or 未適用差分あり（applylog の run_after ログは除外）
# なら apply を促す。
CHEZMOI_BIN="$(command -v chezmoi || mise which chezmoi 2>/dev/null || true)"
if [ -z "$CHEZMOI_BIN" ] || [ -n "$("$CHEZMOI_BIN" status --source "$REPO_ROOT" 2>/dev/null | grep -v 'applylog')" ]; then
  echo "  chezmoi diff && chezmoi apply   # dotfiles 配置 + mise install + fzf-tab を自動実行"
fi
# シェル: 現在の対話シェルが zsh でなければ切替を促す（macOS は既定 zsh なので通常出ない）。
_cur="$(ps -o comm= -p "$PPID" 2>/dev/null | sed 's/^-//')" || true
case "$_cur" in
  *zsh*) ;;
  *) echo "  exec zsh -l                     # zsh へ切替（現セッションは ${_cur:-非zsh}・mise activate も効く）" ;;
esac
unset _cur CHEZMOI_BIN
