# =====================================================================
# 共通シェル層 — zsh / bash 両方から source される。
#
# 方針:
#   - POSIX 準拠で書く (raspi4 / WSL の bash でもそのまま動かす)
#   - zsh / bash 固有設定 (compinit, setopt, bindkey, fzf-tab 等) は
#     呼び出し側 (.zshrc / .bashrc) に残す。ここには書かない
#   - 順序依存: brew shellenv → keg-only PATH → tool init の順で並べる
#
# 配置:
#   ~/.config/shell/common.sh
#
# 呼び出し:
#   .zshrc / .bashrc 側で
#     [ -f ~/.config/shell/common.sh ] && . ~/.config/shell/common.sh
# =====================================================================

# ---------------------------------------------------------------------
# シェル検出
# ---------------------------------------------------------------------
if [ -n "${ZSH_VERSION:-}" ]; then
  __SHELL=zsh
elif [ -n "${BASH_VERSION:-}" ]; then
  __SHELL=bash
else
  __SHELL=sh
fi

# ---------------------------------------------------------------------
# Homebrew shellenv (macOS / Linuxbrew どちらでも)
# ---------------------------------------------------------------------
if [ -r "/opt/homebrew/bin/brew" ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -r "/home/linuxbrew/.linuxbrew/bin/brew" ]; then
  eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
fi

# ---------------------------------------------------------------------
# Homebrew keg-only ツールの PATH 上書き (macOS 想定; ディレクトリ存在で gate)
# ---------------------------------------------------------------------

# GNU grep の gnubin を優先 (macOS の BSD grep 上書き)
if [ -d "/opt/homebrew/opt/grep/libexec/gnubin" ]; then
  PATH="/opt/homebrew/opt/grep/libexec/gnubin:$PATH"
fi

# MySQL クライアント
if [ -d "/opt/homebrew/opt/mysql-client/bin" ]; then
  PATH="/opt/homebrew/opt/mysql-client/bin:$PATH"
fi

# ImageMagick: imagemagick-full (7系) を使用。yazi previewer 等が依存。
# 旧バージョン (imagemagick@6) を必要とする gem を扱うときは下3行に切替。
if [ -d "/opt/homebrew/opt/imagemagick-full/bin" ]; then
  export PATH="/opt/homebrew/opt/imagemagick-full/bin:$PATH"
  export LDFLAGS="-L/opt/homebrew/opt/imagemagick-full/lib"
  export CPPFLAGS="-I/opt/homebrew/opt/imagemagick-full/include"
fi
# export PATH="/opt/homebrew/opt/imagemagick@6/bin:$PATH"
# export LDFLAGS="-L/opt/homebrew/opt/imagemagick@6/lib"
# export CPPFLAGS="-I/opt/homebrew/opt/imagemagick@6/include"

# zstd（brew はあるが zstd 未導入だと `brew --prefix zstd` がエラーを吐くので gate）
if command -v brew >/dev/null 2>&1; then
  _zstd_prefix="$(brew --prefix zstd 2>/dev/null)"
  [ -n "$_zstd_prefix" ] && export LIBRARY_PATH="${LIBRARY_PATH:-}:$_zstd_prefix/lib"
  unset _zstd_prefix
fi

# ---------------------------------------------------------------------
# その他 PATH
# ---------------------------------------------------------------------

# XDG 準拠のユーザーローカル bin (mise.run / pipx / cargo install などが使う)
# mise activate よりも先に PATH に乗せる必要があるのでここで処理する。
# 標準のユーザー bin 置き場なので無ければ作る（安心設計）。pipx 等が入れる前から
# PATH に乗せておき、「入れたのに PATH に無い」を防ぐ。
mkdir -p "$HOME/.local/bin"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# Cargo (rust)
if [ -d "$HOME/.cargo/bin" ]; then
  case ":$PATH:" in
    *":$HOME/.cargo/bin:"*) ;;
    *) export PATH="$HOME/.cargo/bin:$PATH" ;;
  esac
fi

# LM Studio CLI (lms)
if [ -d "$HOME/.lmstudio/bin" ]; then
  export PATH="$PATH:$HOME/.lmstudio/bin"
fi

# 個人 scripts ディレクトリ
if [ -d "$HOME/scripts" ]; then
  export PATH="$HOME/scripts:$PATH"
fi

# pnpm: 言語ランタイム本体は mise 配下 (~/.local/share/mise/shims/pnpm)。
# PNPM_HOME は `pnpm link --global` 用の global bin 置き場 (XDG 準拠)。無ければ作る（安心設計）。
export PNPM_HOME="$HOME/.local/share/pnpm"
mkdir -p "$PNPM_HOME"
case ":$PATH:" in
  *":$PNPM_HOME:"*) ;;
  *) export PATH="$PNPM_HOME:$PATH" ;;
esac

# ---------------------------------------------------------------------
# env
# ---------------------------------------------------------------------
export EDITOR='vi'
# less に ANSI エスケープを色として解釈させる
export LESS='-R'
# Homebrew の自動アップデートを 24h に 1 回に
export HOMEBREW_AUTO_UPDATE_SECS=86400

# ---------------------------------------------------------------------
# ツール init (シェル別に出力切り替え)
# ---------------------------------------------------------------------

# mise (ランタイム系一括管理)
if command -v mise >/dev/null 2>&1; then
  eval "$(mise activate "$__SHELL")"
fi

# direnv
if command -v direnv >/dev/null 2>&1; then
  eval "$(direnv hook "$__SHELL")"
fi

# Starship (vscode 統合ターミナルでは無効化して既定 prompt に任せる)
if [ "${TERM_PROGRAM:-}" != "vscode" ] && command -v starship >/dev/null 2>&1; then
  eval "$(starship init "$__SHELL")"
fi

# zoxide
if command -v zoxide >/dev/null 2>&1; then
  eval "$(zoxide init "$__SHELL")"
fi

# ---------------------------------------------------------------------
# alias
# ---------------------------------------------------------------------
alias ls='ls --color=auto'
alias ll='ls -l'
alias la='ls -la'
alias fig='docker compose'
alias git-difft='git -c diff.external=difft diff'
# helpdora をパイプ越しでも色付きに (`dora codex | less` 等のため)
# npm 公開時に dora → helpdora へ改名済み。dora は短縮 alias として維持
alias helpdora='FORCE_COLOR=1 helpdora'
alias dora='FORCE_COLOR=1 helpdora'

# ---------------------------------------------------------------------
# 関数
# ---------------------------------------------------------------------

# Docker Compose (fig) 実行サポート
figrm() { docker compose run --rm app "$@"; }
figbe() { figrm bundle exec "$@"; }

# yazi: 公式推奨 y 関数。終了時 cwd をシェルに引き継ぐ。
# https://yazi-rs.github.io/docs/quick-start
# (`local` は POSIX 規格外だが zsh / bash / dash いずれも実装あり)
y() {
  local tmp cwd
  tmp="$(mktemp -t yazi-cwd.XXXXXX)"
  command yazi "$@" --cwd-file="$tmp"
  cwd="$(cat "$tmp")"
  if [ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && [ -d "$cwd" ]; then
    cd -- "$cwd" || true
  fi
  rm -f -- "$tmp"
}

# ---------------------------------------------------------------------
# OS 別オプション
# ---------------------------------------------------------------------
case "$(uname -s)" in
  Darwin)
    alias winmerge='wine ~/winapp/WinMerge/WinMergeU.exe'
    if [ -f "$HOME/scripts/launch_iterm2_new_window.scpt" ]; then
      alias iterm-new='osascript ~/scripts/launch_iterm2_new_window.scpt'
    fi
    ;;
esac

unset __SHELL
