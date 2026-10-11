# herdr で Claude Code か Codex を起動する（Stream Deck の Claude Code / Codex キーから呼ぶ）。
#   例: start-agent.ps1 -Kind codex
#   ターミナルが前面のとき: herdr で今見ているペインが何も動いていないシェルならそこで起動する。
#                           Claude / Codex などが動いているペインには触らず、同じ Space に同じディレクトリでタブを開いて起動する。
#   それ以外のとき        : ホームディレクトリに新しい Space を作って起動し、ターミナルを前面に出す。
# ホームディレクトリの「このフォルダを信頼するか」は、chezmoi の claude-trust / codex-config スクリプトが信頼済みにしてある。
param(
  [ValidateSet('claude', 'codex')][string]$Kind = 'claude',
  [string]$Cwd = $HOME
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
# Stream Deck からは画面なしで動くので、失敗したときに追えるよう直近 1 回分の記録を残す
Start-Transcript -LiteralPath (Join-Path $env:TEMP "start-$Kind.log") -Force | Out-Null

Add-Type -Namespace StreamDeck -Name Fg -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
'@

# Stream Deck から -NoProfile で呼ばれると mise の shim が PATH に無いので、インストール先も探す
$herdr = (Get-Command herdr -ErrorAction SilentlyContinue).Source
if (-not $herdr) {
  $herdr = Get-ChildItem "$env:LOCALAPPDATA\mise\installs\aqua-herdrdev-herdr\*\herdr.exe" |
    Sort-Object { [version]$_.Directory.Name } | Select-Object -Last 1 -ExpandProperty FullName
}
if (-not $herdr) { throw 'herdr が見つからない' }

function Invoke-Herdr { & $herdr @args | ConvertFrom-Json }

# エージェントを起動する。名前は herdr 全体で重複できず、小文字・数字・- _ だけなので、ペイン ID から作る
function Start-Agent([string]$PaneId) {
  $name = "$Kind-" + ($PaneId.ToLowerInvariant() -replace '[^a-z0-9_-]', '-')
  $out = & $herdr agent start $name --kind $Kind --pane $PaneId --timeout 30000 2>&1 | Out-String
  Write-Output $out
  return $out -notmatch 'not at|not_at_prompt|pane_busy'
}

$fgPid = 0
[void][StreamDeck.Fg]::GetWindowThreadProcessId([StreamDeck.Fg]::GetForegroundWindow(), [ref]$fgPid)
$terminalInFront = (Get-Process -Id $fgPid -ErrorAction SilentlyContinue).ProcessName -eq 'WindowsTerminal'
$clients = Get-CimInstance Win32_Process -Filter "Name='herdr.exe'" | Where-Object { $_.CommandLine -notmatch '\sserver\s*$' }

if ($terminalInFront -and $clients) {
  $snap = (Invoke-Herdr api snapshot).result.snapshot
  $focused = $snap.panes | Where-Object pane_id -eq $snap.focused_pane_id
  # 今のペインを使うのは、前面で動いているのがシェルだけのときに限る。
  # Claude / Codex やエディタが動いているペインに打ち込むと、その作業を壊すため
  $fgNames = (Invoke-Herdr pane process-info --pane $focused.pane_id).result.process_info.foreground_processes.name
  $idleShell = $fgNames -and -not ($fgNames | Where-Object { $_ -notin 'pwsh.exe', 'powershell.exe', 'cmd.exe', 'bash.exe', 'zsh', 'bash', 'fish' })
  if ($focused -and -not $focused.agent -and $idleShell -and (Start-Agent $focused.pane_id)) { exit 0 }
  # エージェントやほかのプログラムが動いているペインなら、触らずに隣にタブを開く
  $tab = Invoke-Herdr tab create --workspace $focused.workspace_id --cwd $focused.cwd --focus
  [void](Start-Agent $tab.result.root_pane.pane_id)
  exit 0
}

$created = Invoke-Herdr workspace create --cwd $Cwd --focus
[void](Start-Agent $created.result.root_pane.pane_id)

# herdr の画面（server 以外の herdr.exe）が無ければ開く。あれば Windows Terminal を前面に出す
if (-not $clients) {
  Start-Process wt.exe -ArgumentList 'herdr'
} else {
  & (Join-Path $PSScriptRoot 'focus-app.ps1') -Process WindowsTerminal -Launch wt.exe
}
