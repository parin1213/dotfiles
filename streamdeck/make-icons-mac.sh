#!/bin/bash
# Mac のプロファイルで使うアプリのキー画像（144×144 PNG）を icons/ に作る。
# make-icons.ps1 のアプリのキーと同じ見た目にする: 暗いグラデーションに上からの薄い光、中央に 104px のロゴ。
# ロゴは手元のアプリ（.app のアイコン）か公式サイトから取る。各社のロゴなのでコミットしない（.gitignore 済み）。
# Claude Code / Codex CLI / GitHub / YouTube Music / Obsidian は Windows の make-icons.ps1 が作ったものを local-pc から持ってくる
# （Claude Code と Codex のロゴは Windows の VS Code 拡張にしか入っていないため）。
# 必要なもの: ImageMagick（magick）。実行: bash make-icons-mac.sh
set -euo pipefail
cd "$(dirname "$0")"
out=icons
cache=out/mac-icons
mkdir -p "$out" "$cache"

# name と取り元。app:<.app のパス> / url:<画像の URL>
icons=(
  "slack|app:/Applications/Slack.app"
  "chatgpt|app:/Applications/ChatGPT.app"
  "ghostty|app:/Applications/Ghostty.app"
  "vscode|app:/Applications/Visual Studio Code.app"
  "google-drive|app:$HOME/Applications/Chrome Apps.localized/Google ドライブ.app"
  "google-calendar|url:https://ssl.gstatic.com/calendar/images/dynamiclogo_2020q4/calendar_31_2x.png"
  "notion|url:https://www.notion.so/images/logo-ios.png"
)

# .app のアイコンを 512px の PNG にする。icns でも Assets.car でも取れるよう、Finder と同じ NSWorkspace の絵を使う
app_icon() {
  osascript -l JavaScript - "$1" "$2" <<'EOF' >/dev/null
ObjC.import('AppKit');
function run(argv) {
  const img = $.NSWorkspace.sharedWorkspace.iconForFile(argv[0]);
  img.setSize($.NSMakeSize(512, 512));
  const rep = $.NSBitmapImageRep.imageRepWithData(img.TIFFRepresentation);
  rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $()).writeToFileAtomically(argv[1], true);
}
EOF
}

for entry in "${icons[@]}"; do
  name=${entry%%|*}
  src=${entry#*|}
  logo="$cache/$name.png"
  case $src in
    app:*)
      [ -d "${src#app:}" ] || { echo "skip $name: ${src#app:} が無い"; continue; }
      app_icon "${src#app:}" "$logo" ;;
    url:*)
      [ -f "$logo" ] || curl -fsSL "${src#url:}" -o "$logo" ;;
  esac
  # 地のグラデーション（左上 #27272a → 右下 #09090b）に、上から白 20% → 0% の光を重ね、ロゴを中央に置く
  magick -size 144x144 -define gradient:direction=SouthEast gradient:'#27272a-#09090b' \
    \( -size 144x144 gradient:'rgba(255,255,255,0.2)-rgba(255,255,255,0)' \) -compose over -composite \
    \( "$logo" -resize 104x104 -background none -gravity center -extent 104x104 \) -gravity northwest -geometry +20+20 -compose over -composite \
    "$out/$name.png"
  echo "$out/$name.png"
done

for name in claude-code codex-cli github-pr youtube-music obsidian; do
  [ -f "$out/$name.png" ] && continue
  scp -q "local-pc:C:/dev/src/dotfiles/streamdeck/icons/$name.png" "$out/" && echo "$out/$name.png（local-pc から）" || echo "skip $name: local-pc から取れなかった"
done
chmod 644 "$out"/*.png
