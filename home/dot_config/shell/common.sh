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

# サプライチェーン L1: Takumi Guard(GMO Flatt) を各レジストリに挟み、既知の悪性パッケージを
# DL 時にブロックする（匿名=トークン不要）。詳細方針は ~/.claude/CLAUDE.md「サプライチェーンセキュリティ」。
# pnpm は ~/.config/pnpm/config.yaml、gem は ~/.bundle/config で別途設定済み。ここは npm/npx と Python。
# 注: publish は CI が registry を明示するため非影響。ローカル publish 時のみ registry override が要る。
export NPM_CONFIG_REGISTRY="https://npm.flatt.tech/"
export UV_DEFAULT_INDEX="https://pypi.flatt.tech/simple/"
export PIP_INDEX_URL="https://pypi.flatt.tech/simple/"

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

# WSL の op: native Linux op は Windows アプリ連携(PolKit/Linux アプリ前提)に繋がらず
# "not signed in" になる。Windows の op.exe を WSL interop で呼べば Windows アプリ+Hello で
# 認証でき `op signin` 不要。op.exe が PATH に居る時だけ alias する（winget で op 導入後
# `wsl --shutdown` で Windows PATH を取り込むと op.exe が見える）。
# 注: `op read`/`op item get` 等の値取得向け。`op run` でラップする子プロセスは Windows 側で
# 動くため、WSL ネイティブな op run が要る用途では native op + `op signin` を使う。
if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null && command -v op.exe >/dev/null 2>&1; then
  alias op='op.exe'
fi

# ---------------------------------------------------------------------
# 関数
# ---------------------------------------------------------------------

# Docker Compose (fig) 実行サポート
figrm() { docker compose run --rm app "$@"; }
figbe() { figrm bundle exec "$@"; }

# macOS の `open` 相当（Linux/WSL 用）。ファイル/ディレクトリ/URL を既定アプリで開く。
# 引数なしはカレントディレクトリ。macOS はネイティブの /usr/bin/open があるので定義しない
# （関数で shadow すると -a 等のオプションが死ぬ）。
if [ "$(uname -s)" = "Linux" ]; then
  open() {
    [ $# -eq 0 ] && set -- .
    if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
      # WSL: Windows 側の既定アプリで開く。explorer.exe はファイル/ディレクトリ/URL
      # いずれも扱えて追加依存なし（wslview 不要）。パスのみ wslpath -w で Windows 形式に
      # 変換（ext4 上は \\wsl.localhost\... の UNC になる）。URL はそのまま渡す。
      # explorer.exe は成功しても exit 1 を返す仕様なので失敗扱いにしない。
      for _target in "$@"; do
        case "$_target" in
          *://*) explorer.exe "$_target" || true ;;
          *)     explorer.exe "$(wslpath -w "$_target")" || true ;;
        esac
      done
      unset _target
    elif command -v xdg-open >/dev/null 2>&1; then
      # デスクトップ Linux: xdg-open は 1 引数のみ受けるためループで回す
      for _target in "$@"; do xdg-open "$_target"; done
      unset _target
    else
      echo "open: xdg-open が見つかりません（sudo apt install xdg-utils で導入）" >&2
      return 127
    fi
  }
fi

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
  Linux)
    # rootless Docker: user daemon の socket に向ける（rootful の /var/run とは別系統）。
    # WSL は Docker Desktop interop を使うので触らない。socket 実在時だけ設定して
    # rootless 未構成の機で docker が壊れないようにする（bootstrap が rootless 化する）。
    if ! grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
      _docker_rootless_sock="/run/user/$(id -u)/docker.sock"
      [ -S "$_docker_rootless_sock" ] && export DOCKER_HOST="unix://$_docker_rootless_sock"
      unset _docker_rootless_sock
    fi
    ;;
esac

unset __SHELL
