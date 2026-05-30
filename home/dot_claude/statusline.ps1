# Claude Code statusLine (Windows PowerShell)
# stdin で session JSON を受け取り、1 行の ANSI カラー付きステータスを stdout に出す。
# 表示内容: model | cwd | branch | ctx% | 5h limit | 7d limit | cost
# rate_limits は Pro/Max で初回 API 呼び出し後に有効。欠落時は silent に skip。

$ErrorActionPreference = 'SilentlyContinue'

# Windows PowerShell 5.1 はデフォルト UTF-16 で I/O するため UTF-8 を強制。
# Claude Code は stdin に UTF-8 JSON を渡し、stdout も UTF-8 で読むので必須。
[Console]::InputEncoding  = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$OutputEncoding           = New-Object System.Text.UTF8Encoding $false

# デバッグログ: Claude Code が呼んだかと、stdin/stdout の内容を記録。
# 不要になったら $debugLog を $null にすれば無効化される。
$debugLog = "$env:USERPROFILE\.claude\statusline.log"

# 公式ドキュメント推奨パターン: $input は automatic variable で stdin pipeline を表す。
# `-File` 起動でも parent process が stdin を pipe してくれていれば取れる。
$raw = $input | Out-String
if ($debugLog) {
  $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  "--- $ts ---`nSTDIN ($($raw.Length) chars):`n$raw" | Out-File -FilePath $debugLog -Encoding utf8 -Append
}
try { $j = $raw | ConvertFrom-Json -ErrorAction Stop } catch { exit 0 }

function Get-Field($root, [string]$path) {
  $o = $root
  foreach ($p in $path -split '\.') {
    if ($null -eq $o) { return $null }
    $o = $o.$p
  }
  return $o
}

function To-IntOrNull($v) {
  if ($null -eq $v -or $v -eq '') { return $null }
  try { return [int][math]::Floor([double]$v) } catch { return $null }
}

$model = Get-Field $j 'model.display_name'
$cwd   = Get-Field $j 'workspace.current_dir'
$ctx   = To-IntOrNull (Get-Field $j 'context_window.used_percentage')
$cost  = Get-Field $j 'cost.total_cost_usd'
$r5    = To-IntOrNull (Get-Field $j 'rate_limits.five_hour.used_percentage')
$r7    = To-IntOrNull (Get-Field $j 'rate_limits.seven_day.used_percentage')

# model: " (1M context)" のような括弧以降のサフィックスを落として短縮。
if ($model) { $model = ($model -replace '\s*\(.*\)\s*$', '').Trim() }

# cost: 小数 14 桁の生値が来るので 2 桁に丸める。
$costDisp = $null
if ($null -ne $cost -and $cost -ne '') {
  try { $costDisp = '{0:N2}' -f [double]$cost } catch { $costDisp = $null }
}

# cwd: USERPROFILE は ~ に短縮、それ以外で長ければ末尾セグメントに省略。
$cwdDisp = $cwd
if ($cwdDisp) {
  $h = $env:USERPROFILE
  if ($h -and $cwdDisp.StartsWith($h, [System.StringComparison]::OrdinalIgnoreCase)) {
    $cwdDisp = '~' + $cwdDisp.Substring($h.Length)
  }
  if ($cwdDisp.Length -gt 30) {
    $leaf = Split-Path $cwdDisp -Leaf
    $cwdDisp = if ($leaf) { [char]0x2026 + '\' + $leaf } else { [char]0x2026 + $cwdDisp.Substring($cwdDisp.Length - 29) }
  }
}

# git branch (cwd 基準)
$branch = ''
if ($cwd -and (Test-Path -LiteralPath $cwd)) {
  $b = & git -C $cwd branch --show-current 2>$null
  if ($LASTEXITCODE -eq 0 -and $b) { $branch = ($b | Out-String).Trim() }
}

# ANSI
$ESC = [char]27
$R = "$ESC[0m"; $DIM = "$ESC[2m"
$MAG = "$ESC[35m"; $BLU = "$ESC[34m"; $CYA = "$ESC[36m"
$GRN = "$ESC[32m"; $YEL = "$ESC[33m"; $RED = "$ESC[31m"
$BAR = [char]0x2502
$ICN = [char]0x2387

function Get-PctCol($v) {
  if ($null -eq $v) { return $DIM }
  if ($v -ge 90) { return $RED }
  if ($v -ge 70) { return $YEL }
  return $GRN
}

# パーツは (key, plain, colored) で持ち、長すぎる時に低優先キーから捨てる。
# 優先度 (高→低): model, ctx, cwd, branch, 5h, 7d, cost
$items = New-Object System.Collections.ArrayList
if ($model)          { [void]$items.Add(@{ k='model'; p=$model;          c="$MAG$model$R" }) }
if ($cwdDisp)        { [void]$items.Add(@{ k='cwd';   p=$cwdDisp;        c="$BLU$cwdDisp$R" }) }
if ($branch)         { [void]$items.Add(@{ k='branch';p="$ICN $branch";  c="$CYA$ICN $branch$R" }) }
if ($null -ne $ctx)  { [void]$items.Add(@{ k='ctx';   p="ctx ${ctx}%";   c="$(Get-PctCol $ctx)ctx ${ctx}%$R" }) }
if ($null -ne $r5)   { [void]$items.Add(@{ k='5h';    p="5h ${r5}%";     c="$(Get-PctCol $r5)5h ${r5}%$R" }) }
if ($null -ne $r7)   { [void]$items.Add(@{ k='7d';    p="7d ${r7}%";     c="$(Get-PctCol $r7)7d ${r7}%$R" }) }
if ($costDisp)       { [void]$items.Add(@{ k='cost';  p="`$$costDisp";   c="$DIM`$$costDisp$R" }) }

# ターゲット幅: parent terminal の WindowWidth が取れれば使う、無理なら 100。
# `[Console]::WindowWidth` は detached console だと例外になるので try で握り潰す。
$maxW = 100
try {
  $w = [Console]::WindowWidth
  if ($w -gt 20) { $maxW = $w - 2 }
} catch { }

# 区切り " │ " は ANSI 抜きで 3 文字。
$plainLen = { param($arr) ($arr | ForEach-Object { $_.p.Length } | Measure-Object -Sum).Sum + 3 * ([Math]::Max(0, $arr.Count - 1)) }

# 低優先 (末尾) から削っていって幅に収める。model だけは必ず残す。
$dropOrder = @('cost','7d','5h','branch','cwd')
foreach ($drop in $dropOrder) {
  if ((& $plainLen $items) -le $maxW) { break }
  $idx = -1
  for ($i = 0; $i -lt $items.Count; $i++) { if ($items[$i].k -eq $drop) { $idx = $i; break } }
  if ($idx -ge 0) { $items.RemoveAt($idx) }
}

$sep = " $DIM$BAR$R "
$result = [string]::Join($sep, ($items | ForEach-Object { $_.c }))
Write-Host $result -NoNewline

if ($debugLog) {
  "STDOUT ($($result.Length) chars):`n$result`n" | Out-File -FilePath $debugLog -Encoding utf8 -Append
}
