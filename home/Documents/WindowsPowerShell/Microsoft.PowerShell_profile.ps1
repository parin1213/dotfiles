# PowerShell 5.1 用プロファイル（最小・フォールバック / bootstrap 用）。
# 日常の対話シェルは PowerShell 7 (pwsh) に移行済み。フル設定（mise/starship/zoxide/
# eza/lms 等）は Documents/PowerShell/Microsoft.PowerShell_profile.ps1 を参照。
# ここには 5.1 でも要る最小限だけ置く（素の Windows は 5.1 しか無いため bootstrap で踏む）。

# SSH 対話ログインで 5.1 に着地したときも zellij へ寄せる（単一 "main"）。
# zellij のペインは zellij config の default_shell="pwsh" で 7 を使う。
$isInteractiveSsh = $env:SSH_CONNECTION -and
                    -not $env:ZELLIJ -and
                    -not [Console]::IsInputRedirected -and
                    -not [Console]::IsOutputRedirected
if ($isInteractiveSsh -and (Get-Command zellij -ErrorAction SilentlyContinue)) {
    zellij attach -c main
    [Environment]::Exit($LASTEXITCODE)
}

# 文字化け対策（UTF-8）。5.1 はこれが無いと日本語出力が崩れる。
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$global:OutputEncoding = $Utf8NoBom
