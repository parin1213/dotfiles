#!/usr/bin/env bash
# bootstrap-linux.sh — raspi4 / WSL (Ubuntu/Debian) 向け初期セットアップ
#
# install.sh は OS 非依存 (symlink + fzf-tab clone) なので、Linux 固有の
# パッケージインストール・mise セットアップ・ログインシェル変更はこちらで扱う。
#
# 使い方:
#   cd ~/src/dotfiles
#   ./bootstrap-linux.sh           # apt + mise + chsh + chezmoi.toml 生成 + fzf-tab clone
#   chezmoi diff && chezmoi apply  # dotfiles 配置（旧 install.sh は chezmoi に移行済み・廃止）
#   exec zsh -l                    # 反映

set -euo pipefail

if ! command -v apt >/dev/null 2>&1; then
  echo "ERROR: apt が見つからない。Debian/Ubuntu (raspi4 / WSL Ubuntu) 想定の" >&2
  echo "       スクリプト。RHEL 系で動かすなら別途書く必要がある。" >&2
  exit 1
fi

# -----------------------------------------------------------------------------
# 1. apt パッケージ
# -----------------------------------------------------------------------------
PACKAGES=(
  zsh                       # ログインシェル
  git
  curl
  ca-certificates
  gnupg                     # 1Password apt リポの GPG 鍵 dearmor に必要
  build-essential           # mise が ruby/python ビルドする際に必要
  pkg-config                # 同上
  fzf
  zsh-autosuggestions
  zsh-syntax-highlighting   # おまけ (任意)
  direnv
  ripgrep
  fd-find                   # Ubuntu では実体名 fdfind
  jq
  bubblewrap                # codex の read-only sandbox に必須（無いと codex exec -s read-only が panic）
)

echo "==> apt update"
sudo apt update

echo "==> apt install -y ${PACKAGES[*]}"
sudo apt install -y "${PACKAGES[@]}"

# fd-find は実体名 fdfind なので fd という symlink を ~/.local/bin に作る
mkdir -p "$HOME/.local/bin"
if [ -x /usr/bin/fdfind ] && [ ! -e "$HOME/.local/bin/fd" ]; then
  ln -s /usr/bin/fdfind "$HOME/.local/bin/fd"
  echo "==> linked /usr/bin/fdfind -> ~/.local/bin/fd"
fi

# fzf-tab は chezmoi external（home/.chezmoiexternal.toml）が全 OS 共通で clone する。
# bootstrap 側では扱わない（OS 別 clone ハックを排除）。

# -----------------------------------------------------------------------------
# 1.5 Obsidian（GUI デスクトップのみ・snap 経由）
# -----------------------------------------------------------------------------
# snap がある機にだけ入れる（= surface 等の GUI デスクトップ。raspi/WSL は snap 無しで
# 自動 skip するので headless 機に GUI アプリを入れない）。Obsidian は apt に無いため snap。
# vault 本体は別の private リポを obsidian-git で同期する方針（このリポは管理しない）。
if command -v snap >/dev/null 2>&1; then
  if snap list obsidian >/dev/null 2>&1; then
    echo "==> Obsidian: 既にインストール済み"
  else
    echo "==> sudo snap install obsidian --classic"
    sudo snap install obsidian --classic
  fi
else
  echo "==> snap 無し → Obsidian はスキップ（headless 機）"
fi

# -----------------------------------------------------------------------------
# 1.6 1Password CLI (op) — 公式 apt リポ
# -----------------------------------------------------------------------------
# 秘密の標準バックエンド。設計どおり raspi(slim) は対象外（op 統合は raspi 以外）。
# CLI は mise でなく 1Password 公式チャネルから（署名・更新を本家に委譲＝サプライチェーン整合）。
# サインイン/vault 操作・デスクトップ統合(生体認証)は別途ユーザーが行う（ここは CLI 導入まで）。
case "$(hostname)" in
  raspi*)
    echo "==> op(1Password CLI): raspi は対象外（skip）"
    ;;
  *)
    if command -v op >/dev/null 2>&1; then
      echo "==> op(1Password CLI): 既にインストール済み"
    else
      echo "==> 1Password CLI を公式 apt リポから導入"
      ARCH="$(dpkg --print-architecture)"
      curl -sS https://downloads.1password.com/linux/keys/1password.asc \
        | sudo gpg --dearmor --output /usr/share/keyrings/1password-archive-keyring.gpg
      echo "deb [arch=${ARCH} signed-by=/usr/share/keyrings/1password-archive-keyring.gpg] https://downloads.1password.com/linux/debian/${ARCH} stable main" \
        | sudo tee /etc/apt/sources.list.d/1password.list >/dev/null
      sudo mkdir -p /etc/debsig/policies/AC2D62742012EA22/
      curl -sS https://downloads.1password.com/linux/debian/debsig/1password.pol \
        | sudo tee /etc/debsig/policies/AC2D62742012EA22/1password.pol >/dev/null
      sudo mkdir -p /usr/share/debsig/keyrings/AC2D62742012EA22
      curl -sS https://downloads.1password.com/linux/keys/1password.asc \
        | sudo gpg --dearmor --output /usr/share/debsig/keyrings/AC2D62742012EA22/debsig.gpg
      sudo apt update && sudo apt install -y 1password-cli
    fi
    ;;
esac

# -----------------------------------------------------------------------------
# 1.7 1Password デスクトップアプリ（GUI デスクトップのみ）
# -----------------------------------------------------------------------------
# native op を signin 無し(生体/system 認証=PolKit)で使うにはアプリ連携が要る。
# GUI が無い機(WSL/raspi/headless サーバ)には入れない。判定方針:
#   - WSL は osrelease=microsoft で明示除外（WSLg はあっても native アプリ連携は使わない）
#   - それ以外は display-manager.service の有無で「本物のグラフィカルデスクトップ」を判定
#     （gtk ライブラリ有無より確実。headless でも gtk は依存で入りうるため）
# apt リポは 1.6 の op CLI 導入で既に追加済み。アプリ側の「システム認証で解錠」＋
# 「CLIと連携」トグルはデスクトップ上でユーザーが行う（ここは導入まで）。
if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
  echo "==> 1Password GUI: WSL は対象外（skip。WSL は Windows の op.exe を interop で使う）"
elif [ ! -e /etc/systemd/system/display-manager.service ]; then
  echo "==> 1Password GUI: グラフィカルデスクトップ未検出のため skip（headless 機）"
elif dpkg -s 1password >/dev/null 2>&1; then
  echo "==> 1Password GUI: 既にインストール済み"
else
  echo "==> 1Password デスクトップアプリを導入（apt）"
  sudo apt install -y 1password
fi

# -----------------------------------------------------------------------------
# 2. mise (公式インストーラ)
# -----------------------------------------------------------------------------
if command -v mise >/dev/null 2>&1 || [ -x "$HOME/.local/bin/mise" ]; then
  echo "==> mise: 既にインストール済み"
else
  echo "==> mise インストール (curl https://mise.run | sh)"
  curl -sSf https://mise.run | sh
fi

# chezmoi を mise で確保（鶏卵回避: chezmoi apply を打つ前に binary が要る）。
# config にも chezmoi を載せてあるので apply 後も維持される（orphaned shim 化を防ぐ）。
MISE_BIN="$(command -v mise || echo "$HOME/.local/bin/mise")"
echo "==> mise use -g chezmoi"
"$MISE_BIN" use -g chezmoi

# -----------------------------------------------------------------------------
# 3. ログインシェルを zsh に
# -----------------------------------------------------------------------------
ZSH_PATH="$(command -v zsh)"
if [ -z "$ZSH_PATH" ]; then
  echo "ERROR: zsh が見つからない (apt install で失敗した?)" >&2
  exit 1
fi

if [ "$(getent passwd "$USER" | cut -d: -f7)" = "$ZSH_PATH" ]; then
  echo "==> ログインシェル: 既に zsh ($ZSH_PATH)"
else
  if ! grep -q "^${ZSH_PATH}\$" /etc/shells; then
    echo "==> $ZSH_PATH を /etc/shells に追加"
    echo "$ZSH_PATH" | sudo tee -a /etc/shells >/dev/null
  fi
  # sudo chsh なら root 権限でユーザーのシェルを変更でき、対象ユーザーの
  # パスワード入力が不要（非対話 ssh での provision でも止まらない）。
  echo "==> sudo chsh -s $ZSH_PATH $USER"
  sudo chsh -s "$ZSH_PATH" "$USER"
fi

# -----------------------------------------------------------------------------
# 4. chezmoi sourceDir（このスクリプトの実体位置から導出）
# -----------------------------------------------------------------------------
# sourceDir をハードコードせず、スクリプト自身の物理パスから求める。
# repo は各環境 ~/src/dotfiles に clone する方針だが、別の場所でも追従する。
# pwd -P で symlink を解決した実パスを得る。
REPO_ROOT="$(cd "$(dirname "$0")" && pwd -P)"
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

==> Linux ブートストラップ完了。次の手順:

  chezmoi diff && chezmoi apply   # dotfiles 展開（旧 install.sh は chezmoi に移行済み）
  exec zsh -l                     # 新シェル起動 (mise activate がここで効く)
  mise install                    # mise/config.toml の tool を一括インストール

EOM
