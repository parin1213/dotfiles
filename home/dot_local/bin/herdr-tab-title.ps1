# herdr のタブ名と Spaces の $topic を「そのタブでいま走っているもの」に追従させる。
#
# なぜ: herdr のサイドバーは状態（作業中 / 許可待ち / 完了）を出すが、タブ名は既定で連番のまま。
#       Claude Code が出している会話の要約をタブ名へ写すと、状態と中身が 1 行で揃う。
#       状態記号はサイドバーが持つので、ここでは付けない。
#
# タイトルを常に優先し、ディレクトリ名は**タイトルが無いときだけ**の代役にする。
# 目立たせたいのは「何の話をしているか」であって、どこで作業しているかではない。
#
# 使い方: herdr-tab-title.ps1 [working|waiting|attention|auto|plain]
#   引数は呼び出し元の都合で受け取るだけで、付ける名前は変えない
#   （状態の区別はサイドバーが持つ）。
#
# 手で付けたタブ名は書き換えない。自分が最後に付けた名前を state に控え、
# 既定名（連番）か その控えと一致するタブだけを対象にする。

param([string]$Mode = 'auto')

$ErrorActionPreference = 'SilentlyContinue'

# Claude Code の hook から呼ばれる。ここで失敗してもセッションを止めない。
trap { exit 0 }

if (-not $env:HERDR_ENV -or -not $env:HERDR_PANE_ID -or -not $env:HERDR_TAB_ID) { exit 0 }
if (@('plain', 'auto', 'working', 'waiting', 'attention') -notcontains $Mode) { exit 0 }

$herdr = $env:HERDR_BIN_PATH
if (-not ($herdr -and (Test-Path -LiteralPath $herdr))) {
  $herdr = (Get-Command herdr -ErrorAction SilentlyContinue).Source
}
if (-not $herdr) { exit 0 }

# herdr は UTF-8 で JSON を返す。PowerShell 5.1 の既定は ANSI なので日本語のタイトルが壊れる。
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Invoke-Herdr {
  param([string[]]$Arguments)
  $out = & $herdr @Arguments 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
  try { return ($out | Out-String | ConvertFrom-Json) } catch { return $null }
}

# 表示幅で測る（日本語は 2 幅）。East Asian Wide / Fullwidth だけを 2 とみなす。
function Get-DisplayWidth {
  param([string]$Text)
  $width = 0
  foreach ($ch in $Text.ToCharArray()) {
    $c = [int]$ch
    if (($c -ge 0x1100 -and $c -le 0x115F) -or
        ($c -ge 0x2E80 -and $c -le 0xA4CF) -or
        ($c -ge 0xAC00 -and $c -le 0xD7A3) -or
        ($c -ge 0xF900 -and $c -le 0xFAFF) -or
        ($c -ge 0xFE30 -and $c -le 0xFE6F) -or
        ($c -ge 0xFF00 -and $c -le 0xFF60) -or
        ($c -ge 0xFFE0 -and $c -le 0xFFE6)) { $width += 2 } else { $width += 1 }
  }
  return $width
}

# タブバーは狭く、詳しい話はサイドバーが terminal_title_stripped を丸ごと出す。
# ここは「どのタブか見分けがつく」最小限でよいので短く切る。省略記号は付けない。
# 1 セル惜しいのと、切れていること自体はサイドバーを見れば分かるため。
function Get-Fitted {
  param([string]$Text, [int]$MaxWidth)
  if ((Get-DisplayWidth $Text) -le $MaxWidth) { return $Text }

  $cut = ''
  $width = 0
  foreach ($ch in $Text.ToCharArray()) {
    $chWidth = Get-DisplayWidth ([string]$ch)
    if ($width + $chWidth -gt $MaxWidth) { break }
    $cut += $ch
    $width += $chWidth
  }

  # 語の途中でぶつ切りにしない。末尾が助詞・区切り記号・空白ならそこまで戻す。
  # ただし半分より短くなるなら戻さない（見分けがつかなくなるため）。
  $stops = @('の', 'を', 'に', 'が', 'は', 'で', 'へ', 'と', 'や', 'も', '　', ' ', '・', ':', '：', '/', '／', '|', '｜', '-')
  $trimmed = $cut
  while ($trimmed.Length -gt 0 -and $stops -contains $trimmed.Substring($trimmed.Length - 1, 1)) {
    $trimmed = $trimmed.Substring(0, $trimmed.Length - 1)
  }
  if ((Get-DisplayWidth $trimmed) -ge [int][Math]::Floor($MaxWidth / 2)) { $cut = $trimmed }
  return $cut
}

function Get-CwdLabel {
  $root = & git rev-parse --show-toplevel 2>$null
  if ($LASTEXITCODE -eq 0 -and $root) {
    return (Split-Path (($root | Out-String).Trim() -replace '/', '\') -Leaf)
  }
  return (Split-Path (Get-Location).Path -Leaf)
}

$maxWidth = 10
if ($env:HERDR_TAB_TITLE_WIDTH) {
  $parsed = 0
  if ([int]::TryParse($env:HERDR_TAB_TITLE_WIDTH, [ref]$parsed) -and $parsed -gt 0) { $maxWidth = $parsed }
}

# エージェントが出しているタイトルが第一候補。無い（素のシェル等）ときだけ cwd に落とす。
$pane = Invoke-Herdr @('pane', 'get', $env:HERDR_PANE_ID)
$title = ''
if ($pane) { $title = [string]$pane.result.pane.terminal_title_stripped }

$base = $title
if (-not $base) { $base = Get-CwdLabel }
if (-not $base) { exit 0 }

# Spaces 一覧は同じディレクトリ名のワークスペースが並ぶと見分けがつかない。
# いま何の話をしているかを $topic として渡す。エージェントが居なければ場所の名前で代替。
if ($env:HERDR_WORKSPACE_ID) {
  $topic = $title
  if (-not $topic) {
    $workspace = Invoke-Herdr @('workspace', 'get', $env:HERDR_WORKSPACE_ID)
    if ($workspace) { $topic = [string]$workspace.result.workspace.label }
  }
  if ($topic) {
    & $herdr workspace report-metadata $env:HERDR_WORKSPACE_ID --source herdr-tab-title --token "topic=$topic" > $null 2>&1
  }
}

$name = Get-Fitted $base $maxWidth

$tab = Invoke-Herdr @('tab', 'get', $env:HERDR_TAB_ID)
if (-not $tab) { exit 0 }
$label = [string]$tab.result.tab.label
$number = [string]$tab.result.tab.number
if ($name -eq $label) { exit 0 }

$stateRoot = $env:XDG_STATE_HOME
if (-not $stateRoot) { $stateRoot = Join-Path $env:USERPROFILE '.local\state' }
$stateDir = Join-Path $stateRoot 'herdr-tab-title'
$stateFile = Join-Path $stateDir ($env:HERDR_TAB_ID -replace ':', '_')

$last = ''
if (Test-Path -LiteralPath $stateFile) {
  $last = ([System.IO.File]::ReadAllText($stateFile, (New-Object System.Text.UTF8Encoding $false))).Trim()
}

# 既定名は連番。それか自分が前回付けた名前のときだけ書き換える。
if ($label -ne $number -and $label -ne $last) { exit 0 }

& $herdr tab rename $env:HERDR_TAB_ID $name > $null 2>&1
if ($LASTEXITCODE -ne 0) { exit 0 }

if (-not (Test-Path -LiteralPath $stateDir)) { New-Item -ItemType Directory -Path $stateDir -Force | Out-Null }
[System.IO.File]::WriteAllText($stateFile, $name, (New-Object System.Text.UTF8Encoding $false))
exit 0
