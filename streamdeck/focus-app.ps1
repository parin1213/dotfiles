# アプリが起動していればそのウィンドウを前面に出し、起動していなければ起動する（Stream Deck のキーから呼ぶ）。
# 例: focus-app.ps1 -Process WindowsTerminal -Launch wt.exe
param(
  [Parameter(Mandatory)][string]$Process,
  [Parameter(Mandatory)][string]$Launch,
  [string]$Arguments
)

Add-Type -Namespace StreamDeck -Name Win32 -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
'@

$window = Get-Process -Name $Process -ErrorAction SilentlyContinue |
  Where-Object MainWindowHandle -ne 0 | Select-Object -First 1

if (-not $window) {
  if ($Arguments) { Start-Process $Launch -ArgumentList $Arguments } else { Start-Process $Launch }
  exit 0
}

$h = $window.MainWindowHandle
if ([StreamDeck.Win32]::IsIconic($h)) { [void][StreamDeck.Win32]::ShowWindow($h, 9) }  # 9 = SW_RESTORE
# 裏で動くプロセスからは前面化を拒否されるので、Alt を一度押したことにして許可を得る
[StreamDeck.Win32]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
[StreamDeck.Win32]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
[void][StreamDeck.Win32]::SetForegroundWindow($h)
