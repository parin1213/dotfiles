#!/usr/bin/env bash
# install/linux.sh — Linux 系（WSL / Ubuntu / Debian / Raspberry Pi）provision
#
# 「誰に何を入れるか」は .chezmoidata.toml の envs.<env> 能力フラグ（op / op_interop /
# gui_apps / tailscale / docker / sshd）が正本。本スクリプトは chezmoi data からそのフラグを
# 読み込み（DF_*）、各節は DF_* を見て分岐するだけ。環境判定（WSL / raspi / GUI）の重複は
# 表へ一元化した（以前は各節に grep microsoft / case raspi* / display-manager 検出が散在）。
# OS ネイティブ層のみ扱い、CLI/ランタイムは mise、設定は chezmoi apply が担当（3 層モデル）。
#
# 入口は OS 共通で `bootstrap`（install/bootstrap dispatcher / ~/.local/bin shim が OS で名前解決）。
# 直接叩く場合は ./install/linux.sh でも可。apt 一覧は install/packages/apt.txt（外出し）。
#
# 使い方:
#   cd ~/src/dotfiles && bootstrap     # = ./install/linux.sh
#   chezmoi diff && chezmoi apply      # dotfiles 配置（旧 install.sh は chezmoi に移行済み）
#   exec zsh -l                        # 反映

set -euo pipefail

if ! command -v apt >/dev/null 2>&1; then
  echo "ERROR: apt が見つからない。Debian/Ubuntu (raspi4 / WSL / Ubuntu) 想定の" >&2
  echo "       スクリプト。RHEL 系で動かすなら別途書く必要がある。" >&2
  exit 1
fi

# このスクリプトの位置（install/）と リポジトリルート（その親）。
# chezmoi --source / sourceDir 生成 / パッケージ一覧(packages/)の解決に使う。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

# -----------------------------------------------------------------------------
# 1. apt ベースパッケージ（全 Linux 共通＝env 非依存。差分は §4 の能力フラグで出し分け）
# -----------------------------------------------------------------------------
# パッケージ一覧は install/packages/apt.txt に外出し（macOS=Brewfile / Windows=winget と対称）。
# 1行1パッケージ・'#' 以降コメント。先頭トークンだけ取り出して配列化する。
mapfile -t PACKAGES < <(awk '{sub(/#.*/,""); if ($1!="") print $1}' "$SCRIPT_DIR/packages/apt.txt")
if [ "${#PACKAGES[@]}" -eq 0 ]; then
  echo "ERROR: install/packages/apt.txt からパッケージを読めなかった" >&2
  exit 1
fi

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

# 4.6 Tauri 2 ビルド依存（score-checker desktop を WSL/Linux で cargo check/clippy するため）
# GTK/webkit の dev ライブラリ群は重く headless 機には不要なので、tauri_build=true（=WSL のみ）で gate。
# 一覧は install/packages/apt-tauri.txt に外出し（base apt.txt と同じ読み方）。apt install は冪等。
if [ "${DF_TAURI_BUILD:-0}" = 1 ]; then
  mapfile -t TAURI_PKGS < <(awk '{sub(/#.*/,""); if ($1!="") print $1}' "$SCRIPT_DIR/packages/apt-tauri.txt")
  if [ "${#TAURI_PKGS[@]}" -eq 0 ]; then
    echo "WARNING: install/packages/apt-tauri.txt を読めなかった（Tauri 依存 skip）" >&2
  else
    echo "==> Tauri ビルド依存を導入（apt）: ${TAURI_PKGS[*]}"
    sudo apt install -y "${TAURI_PKGS[@]}"
  fi
else
  echo "==> Tauri ビルド依存: 対象外（DF_TAURI_BUILD=0）"
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
# 6. アプリ層（app 軸: DF_APPS のリストを install/apps/<name>.sh で展開）
# -----------------------------------------------------------------------------
# infra(§4) の「上」に乗る機能単位。どの env に何を入れるかは .chezmoidata.toml の
# envs.<env>.apps が正本（§3 で DF_APPS に落ちている）。ここは「リストを回すだけ」。
# アプリ追加 = install/apps/<name>.sh を置き、対象 env の apps に "<name>" を足すだけ。
# 1 アプリが落ちても他は続行（infra と違いアプリは任意性が高い）。最後に失敗を要約。
_app_failed=""
for _app in ${DF_APPS:-}; do
  _app_sh="$SCRIPT_DIR/apps/${_app}.sh"
  if [ ! -f "$_app_sh" ]; then
    echo "WARNING: アプリ '$_app' のスクリプトが無い: $_app_sh" >&2
    _app_failed="$_app_failed $_app"
    continue
  fi
  echo "==> アプリ層: $_app ($_app_sh)"
  if ! bash "$_app_sh"; then
    echo "WARNING: アプリ '$_app' の導入に失敗（続行）" >&2
    _app_failed="$_app_failed $_app"
  fi
done
[ -n "$_app_failed" ] && echo "WARNING: 失敗したアプリ:$_app_failed" >&2
unset _app _app_sh _app_failed

# -----------------------------------------------------------------------------
# 7. chezmoi sourceDir（このリポジトリの実体位置に自動追従）
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
# 8. 案内（本当に必要なステップだけ出す: 差分があれば apply、非 zsh なら exec zsh）
# -----------------------------------------------------------------------------
echo
echo "==> Linux ブートストラップ完了。"
# 以降は本当に必要なステップだけ出す（無ければ完了表示のみ）。
# chezmoi: 未適用の差分があるときだけ apply を促す。applylog は run_after で毎回 status に
# 出る純粋なログなので除外して判定する（残りが空＝適用済みで apply 不要）。
if [ -n "$("$CHEZMOI_BIN" status --source "$REPO_ROOT" 2>/dev/null | grep -v 'applylog')" ]; then
  echo "  chezmoi diff && chezmoi apply   # 未適用の差分あり（dotfiles 配置 + mise install + fzf-tab を自動実行）"
fi
# シェル: 現在の対話シェルが zsh でなければ切替を促す（ログインシェルは chsh 済み）。
_cur="$(ps -o comm= -p "$PPID" 2>/dev/null | sed 's/^-//')" || true
case "$_cur" in
  *zsh*) ;;  # 既に zsh → exec 不要
  *) echo "  exec zsh -l                     # zsh へ切替（現セッションは ${_cur:-非zsh}・mise activate も効く）" ;;
esac
unset _cur
