# miseで選択中のOpenCodeに同梱されたWindows実行ファイルを使う。
# インストール後スクリプトが無効でも、配布物を書き換えずに起動する。
$ErrorActionPreference = 'Stop'
$miseExe = (Get-Command mise.exe -CommandType Application -ErrorAction SilentlyContinue).Source
if (-not $miseExe) {
    $miseExe = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\jdx.mise_*\mise\bin\mise.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $miseExe) { throw 'mise.exeが見つかりません。bootstrapで導入してください。' }
$installRoot = & $miseExe where 'npm:@opencode/cli'
if ($LASTEXITCODE -ne 0) { throw 'miseでOpenCodeのインストール先を取得できませんでした。' }
$installRoot = (@($installRoot)[-1]).Trim()
$selectedVersion = Split-Path $installRoot -Leaf
$arch = if ("$env:PROCESSOR_ARCHITEW6432 $env:PROCESSOR_ARCHITECTURE" -match 'ARM64') { 'arm64' } else { 'x64-baseline' }
$package = "cli-windows-$arch"
$store = Join-Path $installRoot 'node_modules/.mise'
$binary = $null
if (Test-Path -LiteralPath $store) {
    $installed = Get-ChildItem -LiteralPath $store -Directory -Filter "@opencode+$package@$selectedVersion" |
        Select-Object -First 1
    if ($installed) {
        $binary = Join-Path $installed.FullName "node_modules/@opencode/$package/bin/opencode.exe"
    }
}
if (-not $binary -or -not (Test-Path -LiteralPath $binary)) {
    $binary = Join-Path $installRoot "node_modules/@opencode/$package/bin/opencode.exe"
}
if (-not (Test-Path -LiteralPath $binary)) {
    throw 'OpenCodeの公式Windows実行ファイルがありません。miseのインストール状態を確認してください。'
}
$binaryPackage = Get-Content -LiteralPath (Join-Path (Split-Path (Split-Path $binary -Parent) -Parent) 'package.json') -Raw | ConvertFrom-Json
if ($binaryPackage.version -ne $selectedVersion) { throw 'OpenCodeの選択バージョンと実行ファイルのバージョンが一致しません。' }
& $binary @args
exit $LASTEXITCODE
