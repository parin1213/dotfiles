# Stream Deck Neo のキー画像（144×144 PNG）を icons/ に作る。
# 用途ごとの色のグラデーションに、Segoe Fluent Icons のグリフとラベルを焼き込む。
# ゲームは HoYoPlay 同梱の公式アイコン、アプリは exe か公式サイトのロゴを使う。
# フォントが Windows にしか無いので、生成は Windows で行い、PNG はコミットして Mac でも使う。
# 実行: pwsh -File make-icons.ps1
Add-Type -AssemblyName System.Drawing

$out = Join-Path $PSScriptRoot 'icons'
New-Item -ItemType Directory -Force $out | Out-Null

$palette = @{
  daily = @('#4f46e5', '#7c3aed')
  ai    = @('#ea580c', '#db2777')
  mtg   = @('#0d9488', '#16a34a')
  dev   = @('#1e40af', '#0891b2')
  sys   = @('#334155', '#0f172a')
  app   = @('#27272a', '#09090b')
}

$hoyo = 'C:\Program Files\HoYoPlay\1.18.0.380\ico'

# name: ファイル名 / cat: 色 / glyph: Segoe Fluent Icons のコードポイント / text + font: Fluent に無い記号 / ico: 画像を使う場合 / label: 下に出す文字
$icons = @(
  @{ name = 'play-pause';    cat = 'daily'; glyph = 0xF5B0; label = '再生' }
  @{ name = 'mute';          cat = 'daily'; glyph = 0xE74F; label = 'ミュート' }
  @{ name = 'youtube-music'; cat = 'app';   url = 'https://music.youtube.com/img/favicon_144.png' }
  @{ name = 'obsidian';      cat = 'app';   exe = "$env:LOCALAPPDATA\Programs\Obsidian\Obsidian.exe" }
  @{ name = 'genshin';       cat = 'daily'; ico = "$hoyo\hk4e_global.ico" }
  @{ name = 'hsr';           cat = 'daily'; ico = "$hoyo\hkrpg_global.ico" }
  @{ name = 'lock';          cat = 'sys';   glyph = 0xE72E; label = 'ロック' }
  @{ name = 'codex-app';     cat = 'ai';    glyph = 0xE99A; label = 'Codex' }
  @{ name = 'mic';           cat = 'mtg';   glyph = 0xE720; label = 'マイク' }
  @{ name = 'camera';        cat = 'mtg';   glyph = 0xE714; label = 'カメラ' }
  @{ name = 'hand';          cat = 'mtg';   text = [string][char]0x270B; font = 'Segoe UI Symbol'; label = '挙手' }
  @{ name = 'captions';      cat = 'mtg';   glyph = 0xE7F0; label = '字幕' }
  @{ name = 'chat';          cat = 'mtg';   glyph = 0xE8BD; label = 'チャット' }
  @{ name = 'people';        cat = 'mtg';   glyph = 0xE716; label = '参加者' }
  @{ name = 'meeting-note';  cat = 'mtg';   glyph = 0xE70B; label = '会議メモ' }
  @{ name = 'terminal';      cat = 'dev';   glyph = 0xE756; label = 'ターミナル' }
  @{ name = 'vscode';        cat = 'dev';   glyph = 0xE943; label = 'VS Code' }
  @{ name = 'claude-code';   cat = 'ai';    glyph = 0xF4A5; label = 'Claude' }
  @{ name = 'github-pr';     cat = 'dev';   glyph = 0xE8AB; label = 'PR' }
  @{ name = 'screenshot';    cat = 'dev';   glyph = 0xF7ED; label = 'スクショ' }
  @{ name = 'meet-mic';      cat = 'mtg';   glyph = 0xE720; label = 'Meet' }
  @{ name = 'meet-camera';   cat = 'mtg';   glyph = 0xE714; label = 'Meet' }
)

$S = 144
$glyphFont = New-Object System.Drawing.Font('Segoe Fluent Icons', 54, [System.Drawing.GraphicsUnit]::Pixel)
$labelFont = New-Object System.Drawing.Font('BIZ UDPGothic', 19, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$center = New-Object System.Drawing.StringFormat
$center.Alignment = 'Center'; $center.LineAlignment = 'Center'

foreach ($i in $icons) {
  $bmp = New-Object System.Drawing.Bitmap($S, $S)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = 'AntiAlias'; $g.TextRenderingHint = 'AntiAliasGridFit'; $g.InterpolationMode = 'HighQualityBicubic'

  $c = $palette[$i.cat]
  $grad = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    (New-Object System.Drawing.Point(0, 0)), (New-Object System.Drawing.Point($S, $S)),
    [System.Drawing.ColorTranslator]::FromHtml($c[0]), [System.Drawing.ColorTranslator]::FromHtml($c[1]))
  $g.FillRectangle($grad, 0, 0, $S, $S)

  # 上から下へ薄い光を足して、平板なグラデーションに奥行きを出す。
  # ブラシの範囲を塗る範囲より広く取り、端でグラデーションが折り返して線が出ないようにする
  $shine = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    (New-Object System.Drawing.Point(0, -1)), (New-Object System.Drawing.Point(0, ($S + 1))),
    [System.Drawing.Color]::FromArgb(50, 255, 255, 255), [System.Drawing.Color]::FromArgb(0, 255, 255, 255))
  $g.FillRectangle($shine, 0, 0, $S, $S)

  if ($i.ico) {
    # ゲームは公式アイコンをそのまま全面に敷く。ラベルはアイコン内のロゴと重なるので付けない
    $icon = New-Object System.Drawing.Icon($i.ico, 256, 256)
    $g.DrawImage($icon.ToBitmap(), 0, 0, $S, $S)
  } elseif ($i.exe -or $i.url) {
    # アプリは公式のロゴを暗い地の中央に置く。ロゴで分かるのでラベルは付けない
    if ($i.exe) {
      $logo = [System.Drawing.Icon]::ExtractIcon($i.exe, 0, 256).ToBitmap()
    } else {
      $cache = Join-Path $PSScriptRoot "out\$($i.name)-source.png"
      New-Item -ItemType Directory -Force (Split-Path $cache) | Out-Null
      if (-not (Test-Path $cache)) { Invoke-WebRequest $i.url -OutFile $cache }
      $logo = [System.Drawing.Image]::FromFile($cache)
    }
    $g.DrawImage($logo, 20, 20, 104, 104)
    $logo.Dispose()
  } elseif ($i.text) {
    $f = New-Object System.Drawing.Font($i.font, 54, [System.Drawing.GraphicsUnit]::Pixel)
    $g.DrawString($i.text, $f, [System.Drawing.Brushes]::White, (New-Object System.Drawing.RectangleF(0, 8, $S, 96)), $center)
  } else {
    $g.DrawString([string][char]$i.glyph, $glyphFont, [System.Drawing.Brushes]::White, (New-Object System.Drawing.RectangleF(0, 8, $S, 96)), $center)
  }

  if ($i.label) {
    $labelBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(235, 255, 255, 255))
    $g.DrawString($i.label, $labelFont, $labelBrush, (New-Object System.Drawing.RectangleF(0, 102, $S, 34)), $center)
  }

  $bmp.Save((Join-Path $out "$($i.name).png"), [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}

# 一覧で見比べるためのシート（コミットしない）
$cols = 6; $rows = [math]::Ceiling($icons.Count / $cols); $pad = 12
$sheet = New-Object System.Drawing.Bitmap(($cols * ($S + $pad) + $pad), ($rows * ($S + $pad) + $pad))
$sg = [System.Drawing.Graphics]::FromImage($sheet); $sg.Clear([System.Drawing.ColorTranslator]::FromHtml('#111111'))
for ($n = 0; $n -lt $icons.Count; $n++) {
  $img = [System.Drawing.Image]::FromFile((Join-Path $out "$($icons[$n].name).png"))
  $sg.DrawImage($img, $pad + ($n % $cols) * ($S + $pad), $pad + [math]::Floor($n / $cols) * ($S + $pad), $S, $S); $img.Dispose()
}
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot 'out') | Out-Null
$sheet.Save((Join-Path $PSScriptRoot 'out\preview.png'), [System.Drawing.Imaging.ImageFormat]::Png)
"icons: $($icons.Count)"
