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

# 地のグラデーション（左上 → 右下）に、上から白 20% → 0% の光を重ね、ロゴを中央に置く。引数: ロゴ 地の色 出力
compose() {
  magick -size 144x144 -define gradient:direction=SouthEast gradient:"$2" \
    \( -size 144x144 gradient:'rgba(255,255,255,0.2)-rgba(255,255,255,0)' \) -compose over -composite \
    \( "$1" -resize 104x104 -background none -gravity center -extent 104x104 \) -gravity northwest -geometry +20+20 -compose over -composite \
    "$3"
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
  compose "$logo" '#27272a-#09090b' "$out/$name.png"
  echo "$out/$name.png"
done

# 未読数を出すアプリは、バッジを重ねた絵も作る（icons/badges/<name>-<1〜9 | 9+ | dot>.png）。
# 未読があると離れていても気づけるよう、地を赤いグラデーションにする。
# Stream Deck は SVG に埋め込んだ PNG を描けないので、プラグインは数に合う PNG をそのまま送る
mkdir -p "$out/badges"
for name in slack; do
  [ -f "$cache/$name.png" ] || continue
  compose "$cache/$name.png" '#b91c1c-#450a0a' "$cache/$name-unread.png"
  for label in 1 2 3 4 5 6 7 8 9 9+ dot; do
    # バッジは白い丸（2 文字なら横長）に赤い数字。件数の無い未読（dot）は赤い点。地が赤いので白抜きにして目立たせる
    w=$([ "$label" = 9+ ] && echo 64 || echo 52)
    if [ "$label" = dot ]; then text=(-fill '#dc2626' -draw "circle 26,26 26,16"); else
      text=(-fill '#dc2626' -font Helvetica-Bold -pointsize 32 -gravity center -annotate +0+1 "$label"); fi
    magick "$cache/$name-unread.png" \
      \( -size "${w}x52" xc:none -fill white -stroke '#450a0a' -strokewidth 3 \
         -draw "roundrectangle 2,2 $((w - 3)),49 24,24" -stroke none "${text[@]}" \) \
      -gravity northeast -geometry +2+2 -compose over -composite "$out/badges/$name-$label.png"
  done
  echo "$out/badges/$name-*.png"
done

for name in claude-code codex-cli github-pr youtube-music obsidian; do
  [ -f "$out/$name.png" ] && continue
  scp -q "local-pc:C:/dev/src/dotfiles/streamdeck/icons/$name.png" "$out/" && echo "$out/$name.png（local-pc から）" || echo "skip $name: local-pc から取れなかった"
done
chmod 644 "$out"/*.png "$out"/badges/*.png
