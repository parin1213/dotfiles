# install/windows.ps1 — Windows 向け初期セットアップ（provision フェーズ）
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
#   .\install\windows.ps1        # または bootstrap（dispatcher 経由）
#   chezmoi diff; chezmoi apply

$ErrorActionPreference = 'Stop'

# install/ の親がリポジトリルート。sourceDir 生成と chezmoi --source に使う。
$RepoRoot = Split-Path $PSScriptRoot -Parent

# -----------------------------------------------------------------------------
# 1. winget import（OS ネイティブ層: GUI/システム + git + mise + Terminal）
# -----------------------------------------------------------------------------
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Error "winget が見つからない。App Installer（Microsoft Store）を入れてから再実行する。"
}
Write-Host "==> winget import install/packages/winget-packages.json"
winget import (Join-Path $PSScriptRoot "packages\winget-packages.json") --accept-source-agreements --accept-package-agreements --ignore-unavailable

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
# 3. chezmoi sourceDir（このリポジトリの実体位置に自動追従）
# -----------------------------------------------------------------------------
# chezmoi.toml の sourceDir を REPO_ROOT に常に合わせる:
#   一致 → 何も出さない / ズレ・未設定 → sourceDir 行だけ自動書換（他設定は保持）/ 無 → 生成
$cfgDir = Join-Path $env:USERPROFILE ".config\chezmoi"
New-Item -ItemType Directory -Force $cfgDir | Out-Null
$cfg = Join-Path $cfgDir "chezmoi.toml"
# chezmoi.toml は forward slash 推奨（TOML 文字列で backslash escape を避ける）。
$srcDir = $RepoRoot -replace '\\', '/'
if (-not (Test-Path $cfg)) {
    "sourceDir = `"$srcDir`"" | Out-File -Encoding utf8 $cfg
    Write-Host "==> $cfg を生成: sourceDir = $srcDir"
} else {
    $m = Select-String -Path $cfg -Pattern '^\s*sourceDir\s*=\s*"(.*)"' | Select-Object -First 1
    $cur = if ($m) { $m.Matches.Groups[1].Value } else { $null }
    if ($cur -eq $srcDir) {
        # 既に一致 → 何も出さない
    } elseif (Select-String -Path $cfg -Pattern '^\s*sourceDir\s*=' -Quiet) {
        (Get-Content $cfg) -replace '^\s*sourceDir\s*=.*', "sourceDir = `"$srcDir`"" | Set-Content -Encoding utf8 $cfg
        Write-Host "==> chezmoi.toml の sourceDir を追従: $(if ($cur) { $cur } else { '未設定' }) -> $srcDir"
    } else {
        @("sourceDir = `"$srcDir`"") + (Get-Content $cfg) | Set-Content -Encoding utf8 $cfg
        Write-Host "==> chezmoi.toml に sourceDir を追記: $srcDir"
    }
}

# -----------------------------------------------------------------------------
# 4. 案内（本当に必要なステップだけ出す: PATH 未反映なら新シェル、差分があれば apply）
# -----------------------------------------------------------------------------
Write-Host "`n==> Windows ブートストラップ完了。"
# 以降は本当に必要なステップだけ出す（無ければ完了表示のみ）。
$chezmoi = Get-Command chezmoi -ErrorAction SilentlyContinue
if (-not $chezmoi) {
    # winget 導入分が現セッションの PATH に未反映 → 新シェルが要る（mise / chezmoi 解決）。
    Write-Host "  新しい PowerShell を開く        # winget 導入分を PATH に反映"
    Write-Host "  chezmoi diff; chezmoi apply     # dotfiles 配置 + mise install + fzf-tab を自動実行"
} else {
    # chezmoi 解決可。未適用の差分があるときだけ apply を促す（status が空＝適用済み）。
    # applylog は run_after で毎回 status に出る純粋なログなので除外する。
    $st = & $chezmoi.Source status --source $RepoRoot 2>$null | Where-Object { $_ -notmatch 'applylog' }
    if ($st) {
        Write-Host "  chezmoi diff; chezmoi apply     # 未適用の差分あり（mise install + fzf-tab も自動）"
    }
}
