# モニターの入力を DDC/CI（VCP 0x60）で切り替える。Stream Deck の PC⇄Mac キーから呼ぶ。
# 例: pwsh -File switch-input.ps1 -Model U2725QE -Source 0x19   # Dell を TB4（Mac）にする
# 入力の値は Dell U2725QE で確かめたもの: 0x0F = DP（PC）、0x11 = HDMI、0x19 = Thunderbolt 4（Mac）。
# 2 台つないでいるので、DDC の能力文字列にある model() で対象のモニターを選ぶ。
# Dell は切り替えに成功しても SetVCPFeature が False を返すので、戻り値では失敗を判定しない。
param(
  [string]$Model = 'U2725QE',
  [int]$Source = -1,
  # 切り替えずに、DDC で見えたモニターの model を出すだけにする
  [switch]$List
)

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class Ddc {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct PHYSICAL_MONITOR { public IntPtr hPhysicalMonitor; [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string szPhysicalMonitorDescription; }
  public delegate bool MonitorEnumProc(IntPtr hMonitor, IntPtr hdc, IntPtr rect, IntPtr data);
  [DllImport("user32.dll")] public static extern bool EnumDisplayMonitors(IntPtr hdc, IntPtr clip, MonitorEnumProc proc, IntPtr data);
  [DllImport("dxva2.dll")] public static extern bool GetNumberOfPhysicalMonitorsFromHMONITOR(IntPtr hMonitor, out uint count);
  [DllImport("dxva2.dll")] public static extern bool GetPhysicalMonitorsFromHMONITOR(IntPtr hMonitor, uint count, [Out] PHYSICAL_MONITOR[] monitors);
  [DllImport("dxva2.dll")] public static extern bool GetCapabilitiesStringLength(IntPtr hMonitor, out uint length);
  [DllImport("dxva2.dll", CharSet = CharSet.Ansi)] public static extern bool CapabilitiesRequestAndCapabilitiesReply(IntPtr hMonitor, StringBuilder caps, uint length);
  [DllImport("dxva2.dll")] public static extern bool SetVCPFeature(IntPtr hMonitor, byte code, uint value);
  [DllImport("dxva2.dll")] public static extern bool DestroyPhysicalMonitors(uint count, PHYSICAL_MONITOR[] monitors);
}
'@

$handles = New-Object System.Collections.Generic.List[IntPtr]
[void][Ddc]::EnumDisplayMonitors([IntPtr]::Zero, [IntPtr]::Zero, { param($h, $dc, $r, $d) $handles.Add($h); $true }, [IntPtr]::Zero)

if (-not $List -and $Source -lt 0) { Write-Error '-Source か -List を指定する'; exit 2 }
$switched = $false
foreach ($h in $handles) {
  $count = 0
  if (-not [Ddc]::GetNumberOfPhysicalMonitorsFromHMONITOR($h, [ref]$count) -or $count -eq 0) { continue }
  $mons = New-Object Ddc+PHYSICAL_MONITOR[] $count
  if (-not [Ddc]::GetPhysicalMonitorsFromHMONITOR($h, $count, $mons)) { continue }
  foreach ($m in $mons) {
    $len = 0
    if (-not [Ddc]::GetCapabilitiesStringLength($m.hPhysicalMonitor, [ref]$len)) { continue }
    $sb = New-Object System.Text.StringBuilder ([int]$len)
    if (-not [Ddc]::CapabilitiesRequestAndCapabilitiesReply($m.hPhysicalMonitor, $sb, $len)) { continue }
    if ($List) { if ($sb.ToString() -match 'model\(([^)]*)\)') { $Matches[1] }; continue }
    if ($sb.ToString() -notmatch "model\($([regex]::Escape($Model))\)") { continue }
    [void][Ddc]::SetVCPFeature($m.hPhysicalMonitor, 0x60, [uint32]$Source)
    $switched = $true
  }
  [void][Ddc]::DestroyPhysicalMonitors($count, $mons)
}

if ($List) { exit 0 }
if (-not $switched) { Write-Error "DDC で $Model が見つからなかった"; exit 1 }
