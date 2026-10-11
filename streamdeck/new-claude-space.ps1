# herdr に新しい Space を作り、そこで Claude Code を起動する（Stream Deck の Claude Code キーから呼ぶ）。
# 作った Space に切り替え、herdr の画面が開いていなければ Windows Terminal で開く。
# ホームディレクトリの「このフォルダを信頼するか」は、chezmoi の claude-trust スクリプトが信頼済みにしてある。
param([string]$Cwd = $HOME)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

# Stream Deck から -NoProfile で呼ばれると mise の shim が PATH に無いので、インストール先も探す
$herdr = (Get-Command herdr -ErrorAction SilentlyContinue).Source
if (-not $herdr) {
  $herdr = Get-ChildItem "$env:LOCALAPPDATA\mise\installs\aqua-herdrdev-herdr\*\herdr.exe" |
    Sort-Object { [version]$_.Directory.Name } | Select-Object -Last 1 -ExpandProperty FullName
}
if (-not $herdr) { throw 'herdr が見つからない' }

$created = & $herdr workspace create --cwd $Cwd --focus | ConvertFrom-Json
$pane = $created.result.root_pane.pane_id

# 信頼済みでないフォルダを渡すと確認で止まり agent_not_ready が返るが、Claude は起動済みなので失敗として扱わない
& $herdr agent start claude --kind claude --pane $pane --timeout 30000 | Out-Null

# herdr の画面（server 以外の herdr.exe）が無ければ開く。あれば Windows Terminal を前面に出す
$clients = Get-CimInstance Win32_Process -Filter "Name='herdr.exe'" | Where-Object { $_.CommandLine -notmatch '\sserver\s*$' }
if (-not $clients) {
  Start-Process wt.exe -ArgumentList 'herdr'
} else {
  $wt = Get-Process WindowsTerminal -ErrorAction SilentlyContinue | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
  if ($wt) { (New-Object -ComObject WScript.Shell).AppActivate($wt.Id) | Out-Null }
}
