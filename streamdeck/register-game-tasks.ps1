# 原神 / 崩壊：スターレイルを「最上位の特権で実行」するタスクとして登録する。
# どちらの exe も管理者権限を要求するので、Stream Deck から直接起動すると毎回 UAC が出る。
# 登録済みのタスクを起動すれば UAC を出さずに立ち上がる（HoYoPlay を通らないのでアップデート確認は飛ぶ）。
# トリガーは付けないので、Stream Deck のキーから起動したときにしか動かない。
# 何度実行しても同じ状態になる。管理者として実行する: Start-Process pwsh -Verb RunAs -ArgumentList '-File', '<このファイル>'
#Requires -RunAsAdministrator

$games = @(
  @{ name = 'Genshin';  exe = 'C:\Program Files\HoYoPlay\games\Genshin Impact game\GenshinImpact.exe' }
  @{ name = 'StarRail'; exe = 'C:\Program Files\HoYoPlay\games\Star Rail Games\StarRail.exe' }
)

$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

foreach ($g in $games) {
  if (-not (Test-Path -LiteralPath $g.exe)) { Write-Warning "見つからないので飛ばす: $($g.exe)"; continue }
  $action = New-ScheduledTaskAction -Execute $g.exe -WorkingDirectory (Split-Path $g.exe)
  Register-ScheduledTask -TaskPath '\StreamDeck\' -TaskName $g.name -Action $action -Principal $principal -Settings $settings -Force | Out-Null
  "登録: \StreamDeck\$($g.name)"
}
