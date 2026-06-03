# PowerShell 7 (pwsh) 用プロファイル — 日常の対話シェル。
# PS 5.1 (Documents/WindowsPowerShell/...) は bootstrap / フォールバック用の最小版。
# pwsh は winget(Microsoft.PowerShell) で導入。既定シェル化は Windows Terminal の
# 既定プロファイルを PowerShell 7 にして行う。

# --- SSH 対話ログインは zellij へ（単一 "main"・モバイル回線断に強い）---
# zellij のペインは zellij config の default_shell="pwsh" でこの 7 を使う。
$isInteractiveSsh = $env:SSH_CONNECTION -and
                    -not $env:ZELLIJ -and
                    -not [Console]::IsInputRedirected -and
                    -not [Console]::IsOutputRedirected
if ($isInteractiveSsh -and (Get-Command zellij -ErrorAction SilentlyContinue)) {
    zellij attach -c main
    [Environment]::Exit($LASTEXITCODE)
}

Set-Alias -Name sudo -Value gsudo

# 文字エンコーディング（pwsh は UTF-8 既定だが明示して統一）。
$script:Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $script:Utf8NoBom
[Console]::OutputEncoding = $script:Utf8NoBom
$global:OutputEncoding = $script:Utf8NoBom

# LM Studio (lms) は別ファイルに分離し、初回 lmsi/lmsq 呼び出し時だけ読み込む（起動を軽く保つ）。
# lms.ps1 は 5.1 と共有するため WindowsPowerShell/ 側の実体を参照する（重複を避ける）。
$script:LmsScript = Join-Path (Split-Path $PSScriptRoot -Parent) 'WindowsPowerShell\lms.ps1'
function lmsi { . $script:LmsScript; lmsi @args }
function lmsq { . $script:LmsScript; lmsq @args }

# mise を有効化（shim を PATH に）。pwsh 7 は chpwd フック対応なので 5.1 の警告抑制は不要。
# PATH 切り詰め（legacy 2047 制限）で shims より後方の mise.exe が落ちることがあるため、
# 見つからなければ winget の既知パスから拾い、activate はフルパスで叩く。activate 後も mise 自身を
# PATH に残して `mise` コマンドを叩けるようにする（shim だけでは mise 本体が呼べないため）。.zprofile と同方針。
$miseExe = (Get-Command mise -ErrorAction SilentlyContinue).Source
if (-not $miseExe) {
    $miseExe = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\jdx.mise_*\mise\bin\mise.exe" -ErrorAction SilentlyContinue |
               Select-Object -First 1 -ExpandProperty FullName
}
if ($miseExe) {
    (& $miseExe activate pwsh | Out-String) | Invoke-Expression
    if (-not (Get-Command mise -ErrorAction SilentlyContinue)) {
        $env:Path = (Split-Path $miseExe) + ';' + $env:Path
    }
}

# starship プロンプト（未導入でも壊れないよう gate）。
if (Get-Command starship -ErrorAction SilentlyContinue) {
    Invoke-Expression (& { (starship init powershell | Out-String) })
}

# zoxide
if (Get-Command zoxide -ErrorAction SilentlyContinue) {
    Invoke-Expression (& { (zoxide init powershell | Out-String) })
}

# eza
if (Get-Command eza -ErrorAction SilentlyContinue) {
    Set-Alias -Name ls -Value eza -Option AllScope
    function ll { eza -l @args }
    function la { eza -la @args }
    function lt { eza --tree @args }
}
