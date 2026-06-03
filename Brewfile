# Brewfile — 必須パッケージ
# 新マシンで dotfiles を動かすのに最低限必要なもの。
#
# 使い方:
#   brew bundle --file=Brewfile
#
# 追加の project 固有や VS Code 拡張などは Brewfile.optional を参照。

tap "homebrew/services"

# --- dotfiles 依存 (これが無いと zshrc が正しく動かない) ---
brew "mise"                   # 言語ランタイム管理
brew "starship"               # プロンプト
brew "direnv"                 # プロジェクトごとの env 切替
brew "fzf"                    # fuzzy finder + Ctrl-R
brew "tmux"                   # セッション管理
brew "zsh-autosuggestions"    # 履歴ベースサジェスト
brew "zsh-completions"        # 補完強化
brew "grep"                   # GNU grep (PATH 先頭で使う)

# --- 汎用 CLI ---
brew "wget"

# --- Git / Dev workflow ---
brew "difftastic"             # `git-difft` alias で利用
brew "gitleaks"               # secret scan (pre-commit と併用)
brew "pre-commit"             # git hooks
brew "just"                   # task runner (Makefile 代替)

# --- ビルド / 言語共通依存 ---
brew "make"
brew "cmake"
brew "openssl@3"              # Ruby/Python/その他
brew "libyaml"                # Ruby
brew "zstd"                   # 圧縮 (env LIBRARY_PATH で参照)

# --- Terminal + Font ---
cask "ghostty"
cask "font-hackgen"
cask "font-hackgen-nerd"

# --- Notes ---
cask "obsidian"               # vault は別の private git repo を obsidian-git で同期

# --- Secrets ---
brew "1password-cli"          # op。vault 操作・op:// 参照のランタイム注入に使用（公式 formula）
