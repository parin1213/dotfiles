#!/usr/bin/env bash
# install/apps/homeassistant.sh — アプリ層: Home Assistant（Docker Compose / HA Container）
#
# 位置づけ（4軸モデル）: os=入口 / env=設定 / weight=資源 / app=機能。本ファイルは app 層。
#   どの env に入れるかは .chezmoidata.toml の envs.<env>.apps（正本）が決め、install/linux.sh
#   末尾の apps runner が DF_APPS のリストを install/apps/<name>.sh として呼ぶ（＝この入口）。
#   手動でも叩ける: cd ~/src/dotfiles && ./install/apps/homeassistant.sh
#
#   層の依存: OS ネイティブ(linux.sh §1-4) → CLI/runtime(mise) → 設定(chezmoi apply) → app(ここ)。
#   docker は linux.sh §4.4(DF_DOCKER) が rootless で導入済みである前提。HA は docker 必須なので
#   この app を持つ env は .chezmoidata.toml で docker=true にしておく（未導入なら下で検出して停止）。
#
# 方式の選定（Docker Compose / HA Container）:
#   - HA 公式イメージを compose で常駐。更新は image pull だけ。設定は宣言的で git に乗る。
#   - Supervised（アドオン/スナップショット可）は rootful docker 必須・OS 要件が厳格で
#     現状の rootless 構成と衝突するため採らない。HA OS はデバイス占有で本スクリプト要件外。
#
# rootless Docker の制約（重要）:
#   - rootless では `network_mode: host` がコンテナを rootlesskit の net namespace に置き、
#     実ホスト網に通らない → mDNS/SSDP の自動ディスカバリが効かない。
#     そこで bridge + ポート公開(8123:8123) にする。統合は IP 指定で手動追加できる
#     （「とりあえず起動」を優先）。フル discovery が要るなら rootful + host network を別途検討。
#   - USB Zigbee/Z-Wave ドングルの device 渡しも rootless では追加設定が要る（今は未対応）。
#
# 使い方（raspi4 上）:
#   cd ~/src/dotfiles && ./install/raspi.sh
#   → http://<raspi4 の IP>:8123 を開いて初期セットアップ
#
# 設定/更新:
#   compose:  ~/homeassistant/docker-compose.yml （未存在時のみ生成・手編集は上書きしない）
#   config :  ~/homeassistant/config （HA が自動生成する runtime 状態。chezmoi 管理しない）
#   更新   :  cd ~/homeassistant && docker compose pull && docker compose up -d
#   ログ   :  docker compose -f ~/homeassistant/docker-compose.yml logs -f

set -euo pipefail

# HA の配置先（compose と config の親）。環境変数で差し替え可。
HA_DIR="${HA_DIR:-$HOME/homeassistant}"
HA_IMAGE="ghcr.io/home-assistant/home-assistant:stable"
HA_TZ="${HA_TZ:-Asia/Tokyo}"

# -----------------------------------------------------------------------------
# 1. 前提チェック（docker / compose plugin / rootless daemon の起動待ち）
# -----------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker が見つからない。先に provision で Docker を入れる:" >&2
  echo "         cd ~/src/dotfiles && bootstrap   # = install/linux.sh §4.4 (DF_DOCKER)" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' プラグインが無い（docker-compose-plugin 未導入?）。" >&2
  echo "         bootstrap で docker-compose-plugin が入る。再実行する。" >&2
  exit 1
fi

# rootless Docker への接続を確実にする。
# 競合対策: linux.sh §4.4 が rootless をセットアップした直後の同一 provision 実行だと、
# user systemd セッション / socket がまだ立ち上がりきっておらず docker info が即失敗し得る。
# そこで (1)非対話でも user daemon に届くよう XDG_RUNTIME_DIR/DOCKER_HOST を補い、
# (2)未応答なら user サービスを起こし、(3)daemon が応答するまで待つ。
_uid="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${_uid}}"
_sock="${XDG_RUNTIME_DIR}/docker.sock"
# rootless が見えるなら DOCKER_HOST をそこへ向ける（rootful 専用機ならデフォルトのまま）。
if [ -S "$_sock" ] || systemctl --user is-enabled docker >/dev/null 2>&1; then
  export DOCKER_HOST="unix://${_sock}"
fi

# daemon が応答するまで最大 ~20s 待つヘルパ（rootless 起動直後の socket 立ち上がり待ち）。
_wait_docker() {
  _i=0
  while ! docker info >/dev/null 2>&1; do
    _i=$((_i + 1))
    [ "$_i" -ge 20 ] && return 1
    sleep 1
  done
  return 0
}

if ! docker info >/dev/null 2>&1; then
  # rootless user サービスを起こしてから待つ（linger 済みなら非対話でも届く）。
  echo "==> docker daemon 未応答。rootless user サービスを起動して待機する"
  systemctl --user start docker 2>/dev/null || true
  export DOCKER_HOST="unix://${_sock}"
  _wait_docker || true
fi

# ここまでで繋がらなければ、初回 rootless セットアップ直後で user systemd セッションが
# 未確立な可能性が高い。明確に案内して終了（apps runner は失敗として記録し、他は続行する）。
if ! docker info >/dev/null 2>&1; then
  cat >&2 <<EOM
ERROR: rootless Docker に接続できない（DOCKER_HOST=${DOCKER_HOST:-未設定}）。
       初回 provision で rootless をセットアップした直後はよく起きる（user systemd 未確立）。
       一度ログインし直すか、次を実行してから本スクリプトを再実行する:
         sudo loginctl enable-linger "$USER"
         systemctl --user start docker
       再実行: cd ~/src/dotfiles && ./install/apps/homeassistant.sh
EOM
  exit 1
fi

# -----------------------------------------------------------------------------
# 2. 配置先と compose ファイル（未存在時のみ生成＝手編集を上書きしない）
# -----------------------------------------------------------------------------
mkdir -p "$HA_DIR/config"
_compose="$HA_DIR/docker-compose.yml"
if [ -f "$_compose" ]; then
  echo "==> compose: 既に存在（上書きしない）: $_compose"
else
  echo "==> compose を生成: $_compose"
  cat > "$_compose" <<EOF
# Home Assistant (Container) — install/raspi.sh が初回生成。以降の手編集は保持される。
# rootless Docker 前提のため bridge + ポート公開。host network は使わない（上の注記参照）。
services:
  homeassistant:
    container_name: homeassistant
    image: ${HA_IMAGE}
    restart: unless-stopped
    environment:
      - TZ=${HA_TZ}
    volumes:
      - ./config:/config
    ports:
      - "8123:8123"
EOF
fi

# -----------------------------------------------------------------------------
# 3. イメージ取得 → 起動（冪等: 変化が無ければ up -d は no-op）
# -----------------------------------------------------------------------------
echo "==> docker compose pull（${HA_IMAGE}）"
docker compose -f "$_compose" pull
echo "==> docker compose up -d"
docker compose -f "$_compose" up -d

# -----------------------------------------------------------------------------
# 4. 案内（接続先 URL と運用コマンド）
# -----------------------------------------------------------------------------
# LAN 上の IP を最良努力で1つ拾う（取れなければ hostname 表示にフォールバック）。
_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$_ip" ] && _ip="$(hostname).local"
echo
echo "==> Home Assistant 起動完了。"
echo "    URL : http://${_ip}:8123   # ブラウザで開いて初期セットアップ（起動直後は数十秒待つ）"
echo "    更新: cd $HA_DIR && docker compose pull && docker compose up -d"
echo "    ログ: docker compose -f $_compose logs -f"
