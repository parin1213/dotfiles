#!/usr/bin/env bash
# bootstrap-macos.sh — macOS 向け初期セットアップ（provision フェーズ）
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
#   cd ~/src/dotfiles
#   ./bootstrap-macos.sh
#   chezmoi diff && chezmoi apply

set -euo pipefail

# このスクリプト（=リポジトリルート）の物理パス。sourceDir 導出に使う。
REPO_ROOT="$(cd "$(dirname "$0")" && pwd -P)"

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
echo "==> brew bundle (Brewfile)"
brew bundle --file="$REPO_ROOT/Brewfile"

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
# 4. chezmoi sourceDir（このスクリプトの実体位置から導出）
# -----------------------------------------------------------------------------
mkdir -p ~/.config/chezmoi
if [ -f ~/.config/chezmoi/chezmoi.toml ]; then
  echo "==> ~/.config/chezmoi/chezmoi.toml は既存のため生成をスキップ。"
  echo "    sourceDir 想定値: $REPO_ROOT （ズレていれば手で合わせる）"
else
  printf 'sourceDir = "%s"\n' "$REPO_ROOT" > ~/.config/chezmoi/chezmoi.toml
  echo "==> ~/.config/chezmoi/chezmoi.toml を生成: sourceDir = $REPO_ROOT"
fi

# -----------------------------------------------------------------------------
# 5. 案内
# -----------------------------------------------------------------------------
cat <<'EOM'

==> macOS ブートストラップ完了。次の手順:

  chezmoi diff && chezmoi apply   # dotfiles 配置 + mise install(run_onchange) + fzf-tab(external)
  exec zsh -l                     # 反映（mise activate がここで効く）

EOM
