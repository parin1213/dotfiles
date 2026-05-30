# bootstrap-windows.ps1 — Windows 向け初期セットアップ（provision フェーズ）
#
# 役割: mise で入らない OS ネイティブ層だけを入れる。
#   - winget import（GUI/システムアプリ + git + mise + Windows Terminal）
#   - chezmoi（mise 経由）
#   - chezmoi.toml を生成
# CLI/ランタイムの大半は mise が見るので、設定復元（chezmoi apply）時の
# mise install（run_onchange）でまとめて入る。ここでは扱わない。
#
# 使い方（PowerShell 5.1）:
#   cd ~/src/dotfiles            # = $env:USERPROFILE\src\dotfiles
#   ./bootstrap-windows.ps1
#   chezmoi diff; chezmoi apply

$ErrorActionPreference = 'Stop'

# このスクリプト（=リポジトリルート）の物理パス。sourceDir 導出に使う。
$RepoRoot = $PSScriptRoot

# -----------------------------------------------------------------------------
# 1. winget import（OS ネイティブ層: GUI/システム + git + mise + Terminal）
# -----------------------------------------------------------------------------
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Error "winget が見つからない。App Installer（Microsoft Store）を入れてから再実行する。"
}
Write-Host "==> winget import winget-packages.json"
winget import (Join-Path $RepoRoot "winget-packages.json") --accept-source-agreements --accept-package-agreements --ignore-unavailable

# -----------------------------------------------------------------------------
# 2. mise / chezmoi（鶏卵回避: mise を確実にしてから chezmoi を載せる）
# -----------------------------------------------------------------------------
# winget import 直後は PATH が現セッションに未反映なことがあるため明示的に通す。
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")
if (-not (Get-Command mise -ErrorAction SilentlyContinue)) {
    Write-Error "mise が見つからない（winget の jdx.mise が失敗した?）。新しいシェルで再実行する。"
}
Write-Host "==> mise use -g chezmoi"
mise use -g chezmoi

# -----------------------------------------------------------------------------
# 3. chezmoi sourceDir（このスクリプトの実体位置から導出）
# -----------------------------------------------------------------------------
$cfgDir = Join-Path $env:USERPROFILE ".config\chezmoi"
New-Item -ItemType Directory -Force $cfgDir | Out-Null
$cfg = Join-Path $cfgDir "chezmoi.toml"
# chezmoi.toml は forward slash 推奨（TOML 文字列で backslash escape を避ける）。
$srcDir = $RepoRoot -replace '\\', '/'
if (Test-Path $cfg) {
    Write-Host "==> $cfg は既存のため生成をスキップ。sourceDir 想定値: $srcDir"
} else {
    "sourceDir = `"$srcDir`"" | Out-File -Encoding utf8 $cfg
    Write-Host "==> $cfg を生成: sourceDir = $srcDir"
}

# -----------------------------------------------------------------------------
# 4. 案内
# -----------------------------------------------------------------------------
Write-Host @'

==> Windows ブートストラップ完了。次の手順（新しいシェルで）:

  chezmoi diff; chezmoi apply   # dotfiles 配置 + mise install(run_onchange) + fzf-tab(external)

'@
