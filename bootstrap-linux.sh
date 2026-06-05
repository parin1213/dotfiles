#!/usr/bin/env bash
# bootstrap-linux.sh — Linux 系（WSL / Ubuntu / Debian / Raspberry Pi）provision
#
# 「誰に何を入れるか」は .chezmoidata.toml の envs.<env> 能力フラグ（op / op_interop /
# gui_apps / tailscale / docker / sshd）が正本。本スクリプトは chezmoi data からそのフラグを
# 読み込み（DF_*）、各節は DF_* を見て分岐するだけ。環境判定（WSL / raspi / GUI）の重複は
# 表へ一元化した（以前は各節に grep microsoft / case raspi* / display-manager 検出が散在）。
# OS ネイティブ層のみ扱い、CLI/ランタイムは mise、設定は chezmoi apply が担当（3 層モデル）。
#
# 入口は OS 共通で `bootstrap`（repo 直下 dispatcher / ~/.local/bin shim が OS で名前解決）。
# 直接叩く場合は ./bootstrap-linux.sh でも可。
#
# 使い方:
#   cd ~/src/dotfiles && bootstrap     # = ./bootstrap-linux.sh
#   chezmoi diff && chezmoi apply      # dotfiles 配置（旧 install.sh は chezmoi に移行済み）
#   exec zsh -l                        # 反映

set -euo pipefail

if ! command -v apt >/dev/null 2>&1; then
  echo "ERROR: apt が見つからない。Debian/Ubuntu (raspi4 / WSL / Ubuntu) 想定の" >&2
  echo "       スクリプト。RHEL 系で動かすなら別途書く必要がある。" >&2
  exit 1
fi

# このスクリプト（= リポジトリルート）の物理パス。chezmoi --source と sourceDir 導出に使う。
REPO_ROOT="$(cd "$(dirname "$0")" && pwd -P)"

# -----------------------------------------------------------------------------
# 1. apt ベースパッケージ（全 Linux 共通＝env 非依存。差分は §4 の能力フラグで出し分け）
# -----------------------------------------------------------------------------
PACKAGES=(
  zsh                       # ログインシェル
  git
  curl
  ca-certificates
  gnupg                     # 1Password / Docker apt リポの GPG 鍵 dearmor に必要
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

# -----------------------------------------------------------------------------
# 2. mise + chezmoi（能力フラグを chezmoi data から読むため、ここで先に確保する）
# -----------------------------------------------------------------------------
# 鶏卵回避: §3 の能力フラグ読み込みに chezmoi が要るので、apt ベースの直後に mise→chezmoi を置く。
# config にも chezmoi を載せてあるので apply 後も維持される（orphaned shim 化を防ぐ）。
if command -v mise >/dev/null 2>&1 || [ -x "$HOME/.local/bin/mise" ]; then
  echo "==> mise: 既にインストール済み"
else
  echo "==> mise インストール (curl https://mise.run | sh)"
  curl -sSf https://mise.run | sh
fi
MISE_BIN="$(command -v mise || echo "$HOME/.local/bin/mise")"
echo "==> mise use -g chezmoi"
"$MISE_BIN" use -g chezmoi
# activate していないシェルから確実に呼べるよう実体パスを解決（shim フォールバック付き）。
CHEZMOI_BIN="$("$MISE_BIN" which chezmoi 2>/dev/null || echo "$HOME/.local/share/mise/shims/chezmoi")"

# -----------------------------------------------------------------------------
# 3. 能力フラグ（DF_*）を .chezmoidata.toml から読み込む（provision ポリシーの正本は1箇所）
# -----------------------------------------------------------------------------
# profile-env テンプレが profile（os/kernel/hostname 判定）→ envs.<env> 行 → DF_*=0/1 に落とす。
# chezmoi.toml に依存しないよう --source を明示（.chezmoiroot=home は repo ルート指定で解決）。
echo "==> 環境プロファイルを読み込む（chezmoi data → DF_*）"
_DF="$("$CHEZMOI_BIN" execute-template --source "$REPO_ROOT" '{{ includeTemplate "profile-env" . }}')"
eval "$_DF"
echo "$_DF" | sed 's/^/    /'
unset _DF

# -----------------------------------------------------------------------------
# 4. 能力フラグに従って OS ネイティブ層を provision
#    WHO（誰に入れるか）= §3 の表、HOW（どう入れるか）= 以下、AUTH（認証）= ユーザー本人。
#    導入は公式チャネル固定（署名・更新を本家に委譲＝サプライチェーン整合）。
# -----------------------------------------------------------------------------

# 4.1 1Password CLI (op) — 公式 apt リポ
if [ "${DF_OP:-0}" = 1 ]; then
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
else
  echo "==> op(1Password CLI): 対象外（DF_OP=0）"
fi
# op_interop（WSL で op→op.exe に寄せる）は common.sh が DF と同じ表を見て alias する（ここでは何もしない）。

# 4.2 GUI デスクトップアプリ（1Password app / Obsidian）
# native op を signin 無し（生体/PolKit）で使うにはアプリ連携が要る。1Password app の apt リポは
# 4.1 で追加済み前提（GUI 機は op=true）。Obsidian は apt に無いため snap（無ければ skip）。
if [ "${DF_GUI_APPS:-0}" = 1 ]; then
  if dpkg -s 1password >/dev/null 2>&1; then
    echo "==> 1Password GUI: 既にインストール済み"
  else
    echo "==> 1Password デスクトップアプリを導入（apt）"
    sudo apt install -y 1password
  fi
  if command -v snap >/dev/null 2>&1; then
    if snap list obsidian >/dev/null 2>&1; then
      echo "==> Obsidian: 既にインストール済み"
    else
      echo "==> sudo snap install obsidian --classic"
      sudo snap install obsidian --classic
    fi
  else
    echo "==> Obsidian: snap 無しのため skip"
  fi
else
  echo "==> GUI アプリ: 対象外（DF_GUI_APPS=0）"
fi

# 4.3 Tailscale（メッシュ VPN）— 公式インストーラ（distro/arch 自動判定）
if [ "${DF_TAILSCALE:-0}" = 1 ]; then
  if command -v tailscale >/dev/null 2>&1; then
    echo "==> Tailscale: 既にインストール済み"
  else
    echo "==> Tailscale を公式インストーラで導入（curl https://tailscale.com/install.sh | sh）"
    curl -fsSL https://tailscale.com/install.sh | sh
  fi
  # `tailscale up`（認証・ログイン）はユーザー本人が行う。
else
  echo "==> Tailscale: 対象外（DF_TAILSCALE=0）"
fi

# 4.4 Docker Engine（公式 apt リポ）＋ rootless 化（daemon も非 root で動かす＝標準構成）
if [ "${DF_DOCKER:-0}" = 1 ]; then
  if command -v docker >/dev/null 2>&1 && dpkg -s docker-ce >/dev/null 2>&1; then
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
  # rootless 化: install だけでは rootful。冪等性は ~/.config/systemd/user/docker.service の有無で判定。
  if ! command -v dockerd-rootless-setuptool.sh >/dev/null 2>&1; then
    echo "==> Docker rootless: docker 未導入のため skip"
  elif [ -f "$HOME/.config/systemd/user/docker.service" ]; then
    echo "==> Docker rootless: 既に構成済み（~/.config/systemd/user/docker.service）"
  else
    echo "==> Docker rootless をセットアップ"
    sudo loginctl enable-linger "$USER" || true                          # ログアウト後も user daemon 維持
    sudo systemctl disable --now docker.service docker.socket 2>/dev/null || true  # rootful daemon は止める
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"       # 非対話でも user systemd に届かせる
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
  # DOCKER_HOST=unix:///run/user/<uid>/docker.sock は dotfiles 側(common.sh)が socket 実在時に設定。
else
  echo "==> Docker: 対象外（DF_DOCKER=0）"
fi

# 4.5 OpenSSH server（このマシンへ ssh で入る受け側）
if [ "${DF_SSHD:-0}" = 1 ]; then
  if dpkg -s openssh-server >/dev/null 2>&1; then
    echo "==> openssh-server: 既にインストール済み"
  else
    echo "==> openssh-server を導入（apt）"
    sudo apt install -y openssh-server
  fi
else
  echo "==> openssh-server: 対象外（DF_SSHD=0）"
fi

# -----------------------------------------------------------------------------
# 5. ログインシェルを zsh に
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
  # sudo chsh なら対象ユーザーのパスワード入力が不要（非対話 ssh の provision でも止まらない）。
  echo "==> sudo chsh -s $ZSH_PATH $USER"
  sudo chsh -s "$ZSH_PATH" "$USER"
fi

# -----------------------------------------------------------------------------
# 6. chezmoi sourceDir（このスクリプトの実体位置から導出）
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
# 7. 案内
# -----------------------------------------------------------------------------
cat <<'EOM'

==> Linux ブートストラップ完了。次の手順:

  chezmoi diff && chezmoi apply   # dotfiles 配置 + mise install(run_onchange) + fzf-tab(external) を自動実行
  exec zsh -l                     # 反映（mise activate がここで効く）

EOM
