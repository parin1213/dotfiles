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
# GUI が無い機(WSL/headless サーバ)や op 対象外の raspi(slim) には入れない。判定方針:
#   - raspi(slim) は設計どおり対象外（hostname で明示）。※Raspberry Pi OS は headless 運用でも
#     display-manager が入っており、DM 判定だけでは除外できないため hostname で弾く。
#   - WSL は osrelease=microsoft で除外（native アプリ連携は使わず op.exe interop に委譲）。
#   - 残りは display-manager.service の有無で「本物のグラフィカルデスクトップ」を判定
#     （gtk ライブラリ有無より確実。headless でも gtk は依存で入りうるため）。
# apt リポは 1.6 の op CLI 導入で既に追加済み。アプリ側の「システム認証で解錠」＋
# 「CLIと連携」トグルはデスクトップ上でユーザーが行う（ここは導入まで）。
case "$(hostname)" in
  raspi*)
    echo "==> 1Password GUI: raspi は対象外（skip）"
    ;;
  *)
    if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
      echo "==> 1Password GUI: WSL は対象外（skip。Windows の op.exe を interop で使う）"
    elif [ ! -e /etc/systemd/system/display-manager.service ]; then
      echo "==> 1Password GUI: グラフィカルデスクトップ未検出のため skip（headless 機）"
    elif dpkg -s 1password >/dev/null 2>&1; then
      echo "==> 1Password GUI: 既にインストール済み"
    else
      echo "==> 1Password デスクトップアプリを導入（apt）"
      sudo apt install -y 1password
    fi
    ;;
esac

# -----------------------------------------------------------------------------
# 1.8 Tailscale（メッシュ VPN）— 公式インストーラ
# -----------------------------------------------------------------------------
# 各ノードを Tailnet に載せて相互到達させる。WSL は除外（Windows 側の Tailscale を
# 使い WSL からは interop で届く。WSL 内 tailscaled は systemd / TUN 周りが面倒）。
# raspi/surface 等の実機 Linux は対象（headless 機ほどリモート到達の価値が高い）。
# 公式スクリプトが distro/arch を自動判定して apt リポを設定する（＝公式チャネル）。
# `tailscale up`（認証・ログイン）はユーザー本人が行う（ここは daemon 導入まで）。
if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
  echo "==> Tailscale: WSL は対象外（skip。Windows の Tailscale を interop で使う）"
elif command -v tailscale >/dev/null 2>&1; then
  echo "==> Tailscale: 既にインストール済み"
else
  echo "==> Tailscale を公式インストーラで導入（curl https://tailscale.com/install.sh | sh）"
  curl -fsSL https://tailscale.com/install.sh | sh
fi

# -----------------------------------------------------------------------------
# 1.9 Docker Engine（公式 apt リポ・rootless 対応）
# -----------------------------------------------------------------------------
# コンテナ実行基盤。distro 同梱の docker.io でなく本家 docker-ce を公式チャネルから
# （更新・署名を本家に委譲＝サプライチェーン整合。1Password/Tailscale と同方針）。
# WSL は除外（Windows の Docker Desktop を interop で使う。WSL 内 dockerd は
# systemd / cgroup 周りが面倒）。rootless 実行に要る uidmap / rootless-extras も併せて
# 入れる（rootless 化＝dockerd-rootless-setuptool.sh と daemon 起動はユーザーが行う。
# ここは導入まで）。
if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
  echo "==> Docker: WSL は対象外（skip。Windows の Docker Desktop を interop で使う）"
elif command -v docker >/dev/null 2>&1 && dpkg -s docker-ce >/dev/null 2>&1; then
  echo "==> Docker: 既にインストール済み"
else
  echo "==> Docker Engine を公式 apt リポから導入"
  # 公式リポのパスは ID で分岐（ubuntu / debian / raspbian）。/etc/os-release から導出。
  . /etc/os-release
  ARCH="$(dpkg --print-architecture)"
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" \
    | sudo gpg --dearmor --yes --output /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${ID} ${VERSION_CODENAME:-} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt update
  sudo apt install -y \
    docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin \
    docker-ce-rootless-extras uidmap
fi

# -----------------------------------------------------------------------------
# 1.9b Docker rootless 化（daemon も非 root で動かす＝このリポの標準構成）
# -----------------------------------------------------------------------------
# install だけでは rootful（root daemon）。rootless は per-user セットアップが要る:
#   linger 有効化 → rootful daemon 停止 → dockerd-rootless-setuptool.sh install。
# 非対話 provision でも進むよう XDG_RUNTIME_DIR を明示し、失敗しても bootstrap は
# 止めない（best-effort。完了しない時は最後の案内に従って手動実施）。冪等性は
# ~/.config/systemd/user/docker.service（setuptool が作る）の有無で判定。
# DOCKER_HOST=unix:///run/user/<uid>/docker.sock は dotfiles 側(common.sh)で設定。
if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
  : # WSL は Docker 導入自体を上で skip 済み
elif ! command -v dockerd-rootless-setuptool.sh >/dev/null 2>&1; then
  echo "==> Docker rootless: docker 未導入のため skip"
elif [ -f "$HOME/.config/systemd/user/docker.service" ]; then
  echo "==> Docker rootless: 既に構成済み（~/.config/systemd/user/docker.service）"
else
  echo "==> Docker rootless をセットアップ"
  # ログアウト後も user daemon を維持（headless/ssh で必須）。/run/user/<uid> も用意される。
  sudo loginctl enable-linger "$USER" || true
  # rootful の system daemon は止める（rootless と二重持ちしない＝標準を rootless に寄せる）。
  sudo systemctl disable --now docker.service docker.socket 2>/dev/null || true
  # 非対話シェルでも user systemd に届くよう runtime dir を明示。
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  if dockerd-rootless-setuptool.sh install --force; then
    systemctl --user enable --now docker 2>/dev/null || true
    echo "==> Docker rootless: 構成完了（反映に再ログインが要る場合あり）"
  else
    cat <<'EOM'
==> Docker rootless: 自動セットアップに失敗（systemd user session 未確立の可能性）。
    一度ログインし直してから手動で:
      sudo loginctl enable-linger "$USER"
      dockerd-rootless-setuptool.sh install --force
      systemctl --user enable --now docker
EOM
  fi
fi

# -----------------------------------------------------------------------------
# 1.10 OpenSSH server（このマシンへ ssh で入る受け側）
# -----------------------------------------------------------------------------
# リモートから入る実機（surface / raspi 等）でだけ要る。WSL は除外（Windows 側の
# sshd / 既存経路を使う。WSL 内 sshd は systemd 前提で扱いが面倒）。
if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
  echo "==> openssh-server: WSL は対象外（skip）"
elif dpkg -s openssh-server >/dev/null 2>&1; then
  echo "==> openssh-server: 既にインストール済み"
else
  echo "==> openssh-server を導入（apt）"
  sudo apt install -y openssh-server
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
