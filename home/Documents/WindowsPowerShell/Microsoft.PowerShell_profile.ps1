$isInteractiveSsh = $env:SSH_CONNECTION -and
                    -not $env:ZELLIJ -and
                    -not [Console]::IsInputRedirected -and
                    -not [Console]::IsOutputRedirected

if ($isInteractiveSsh) {
    zellij attach -c
    [Environment]::Exit($LASTEXITCODE)
}

Set-Alias -Name sudo -Value gsudo

$script:Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $script:Utf8NoBom
[Console]::OutputEncoding = $script:Utf8NoBom
$global:OutputEncoding = $script:Utf8NoBom

# LM Studio (lms) は別ファイル lms.ps1 に分離し、初回 lmsi/lmsq 呼び出し時にだけ読み込む（profile/起動を軽く保つ）。
$script:LmsScript = Join-Path $PSScriptRoot 'lms.ps1'
function lmsi { . $script:LmsScript; lmsi @args }
function lmsq { . $script:LmsScript; lmsq @args }

# Activate mise so its shims (zoxide/eza/rg/fd/jq/gitleaks/direnv, runtimes) are on PATH.
# PS 5.1 lacks chpwd hooks (PS7+ only); silence that warning.
if (Get-Command mise -ErrorAction SilentlyContinue) {
    $env:MISE_PWSH_CHPWD_WARNING = '0'
    (& mise activate pwsh | Out-String) | Invoke-Expression
}

# starship プロンプト（mise 経由で入る。環境名などを表示。未導入でも壊れないよう gate）。
if (Get-Command starship -ErrorAction SilentlyContinue) {
    Invoke-Expression (& { (starship init powershell | Out-String) })
}

# zoxide / eza は mise 経由で PATH に乗る。mise activate 失敗や未導入でも
# プロファイル読み込みが壊れないよう存在を確認してから設定する。
if (Get-Command zoxide -ErrorAction SilentlyContinue) {
    Invoke-Expression (& { (zoxide init powershell | Out-String) })
}

if (Get-Command eza -ErrorAction SilentlyContinue) {
    Set-Alias -Name ls -Value eza -Option AllScope
    function ll { eza -l @args }
    function la { eza -la @args }
    function lt { eza --tree @args }
}

