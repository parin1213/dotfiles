# bootstrap.ps1 — OS 共通の provision 入口（名前解決トリックの「実体」: Windows 側）。
#
# 狙い: `code` のように「一つの名前 bootstrap」をどの環境でも叩けるようにする。
#   - pwsh は PATH 上の `bootstrap` を bootstrap.ps1 として解決して実行する（検証済み）。
#   - Unix では拡張子なしの bootstrap（uname 振り分け）が解決される（別ファイル）。
# 同ディレクトリの bootstrap-windows.ps1 へ委譲する。初回は repo 直下で `.\bootstrap.ps1`、
# chezmoi apply 後は ~/.local/bin の shim 経由でどこでも `bootstrap`。
$here = $PSScriptRoot
& (Join-Path $here "bootstrap-windows.ps1") @args
