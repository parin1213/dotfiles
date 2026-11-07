#!/usr/bin/env bash
# app軸から承認済みの歩数同期を登録する。設定または資格情報がなければ保留する。
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/health-log" && pwd)"
DATA="$APP_DIR/../../../home/.chezmoidata.toml"
VAULT="${OBSIDIAN_VAULT:-$HOME/obsidian-vault}"
PYTHON="$(command -v python3)"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)'
if ! settings=$("$PYTHON" -c 'import sys,tomllib; from zoneinfo import ZoneInfo; d=tomllib.load(open(sys.argv[1],"rb"))["health_steps_sync"]; z=d["timezone"]; d["account"]; d["project_id"]; ZoneInfo(z) if z else None; print(z); print(d["interval_minutes"]); print(d["recent_days"])' "$DATA"); then
  echo "歩数同期の公開設定とタイムゾーンを確認してください" >&2
  exit 1
fi
mapfile -t values <<< "$settings"
if [[ "${#values[@]}" != 3 || -z "${values[0]}" ]]; then
  echo "==> 歩数同期: 本人のタイムゾーンが未設定のため登録を保留"
  exit 0
fi
if [[ "${values[1]}" != 60 || ! "${values[2]}" =~ ^[12]$ ]]; then
  echo "歩数同期は60分間隔・今日と昨日までの設定を確認してください" >&2
  exit 1
fi
CREDENTIAL="$HOME/.local/share/health-steps-sync/credentials/google-health.cred"
if [[ ! -f "$CREDENTIAL" || -L "$CREDENTIAL" || ! -d "$VAULT/ログ" || ! -d "$VAULT/.git" ]]; then
  echo "==> 歩数同期: 承認済み資格情報または既存Vaultがないため登録を保留"
  exit 0
fi
VAULT="$(cd "$VAULT" && pwd -P)"
for value in "$APP_DIR" "$DATA" "$VAULT" "$PYTHON"; do
  if [[ "$value" == *'"'* || "$value" == *'%'* || "$value" == *$'\n'* || "$value" == *'\'* ]]; then
    echo "設定パスに二重引用符・%・改行・バックスラッシュは使えません" >&2
    exit 1
  fi
done

UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
temporary="$(mktemp -d)"
trap 'rm -f "$temporary/health-steps-sync.service" "$temporary/health-steps-sync.timer"; rmdir "$temporary"' EXIT
cat > "$temporary/health-steps-sync.service" <<EOF
[Unit]
Description=本人の日別歩数を既存Vaultへ同期
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
ExecStart="$PYTHON" "$APP_DIR/sync_credentials_exec.py" "$APP_DIR/google_sync.py" --config "$DATA" --vault "$VAULT"
RuntimeDirectory=health-steps-sync
RuntimeDirectoryMode=0700
Environment=PYTHONDONTWRITEBYTECODE=1
NoNewPrivileges=yes
UMask=0077
Nice=10
EOF
cat > "$temporary/health-steps-sync.timer" <<EOF
[Unit]
Description=本人の歩数同期を1時間ごとに起動

[Timer]
OnBootSec=2min
OnUnitActiveSec=60min
RandomizedDelaySec=5min
Unit=health-steps-sync.service

[Install]
WantedBy=timers.target
EOF
systemd-analyze --user verify "$temporary/health-steps-sync.service" "$temporary/health-steps-sync.timer"
changed=0
for name in health-steps-sync.service health-steps-sync.timer; do
  if ! cmp -s "$temporary/$name" "$UNIT_DIR/$name"; then
    install -m 600 "$temporary/$name" "$UNIT_DIR/$name"
    changed=1
  fi
done
if [[ "$changed" == 1 ]]; then
  systemctl --user daemon-reload
fi
systemctl --user enable health-steps-sync.timer
if [[ "$changed" == 1 ]]; then
  systemctl --user restart health-steps-sync.timer
else
  systemctl --user start health-steps-sync.timer
fi
systemctl --user is-active --quiet health-steps-sync.timer
echo "==> 歩数同期: 1時間ごとのユーザータイマーを登録"
