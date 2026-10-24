# Daily `mise up` for Windows (PowerShell 5.1 compatible). Counterpart of the Unix
# home/dot_local/bin/executable_pkg-update, which also runs brew on mac.
# winget is not upgraded here: machine-scope packages need UAC, and nobody is at the
# screen when the scheduled task runs. bootstrap.ps1 / distribute.ps1 -Full cover winget.
# claude-code / codex skip the cooldown via minimum_release_age_excludes in
# ~/.config/mise/config.toml, so mise up picks up their daily releases right away.
# Runs from Task Scheduler (registered by run_onchange_after_pkg-update.ps1).
#
# On failure, a one-line summary goes to $Failed and the pwsh profile prints it once
# at the next shell start, so a failed night run is noticed without opening the log.
# Messages are English-only on purpose: this file is deployed by chezmoi without a BOM,
# and PowerShell 5.1 misreads non-ASCII in a BOM-less file.

$StateDir = Join-Path $HOME ".local\state"
$Log = Join-Path $StateDir "pkg-update.log"
$Failed = Join-Path $StateDir "pkg-update.failed"
$Lock = Join-Path $StateDir "pkg-update.lock"

if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force | Out-Null }

function Write-UpdateLog([string]$Message) {
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    Add-Content -Path $Log -Value "$ts $Message"
}

if (Test-Path $Log) {
    $lines = Get-Content $Log
    if ($lines.Count -gt 1000) { $lines | Select-Object -Last 500 | Set-Content $Log }
}

# A manual run overlapping the scheduled one would fight over the same install dirs,
# so the later one does nothing. Locks older than 2h are leftovers from a crashed run.
if (Test-Path $Lock) {
    $age = (Get-Date) - (Get-Item $Lock).LastWriteTime
    if ($age.TotalHours -lt 2) {
        Write-UpdateLog "SKIP: another pkg-update is running"
        exit 0
    }
    Remove-Item -Recurse -Force $Lock -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $Lock -Force | Out-Null

# Resolve the global config, not a project mise.toml from the current directory.
Set-Location $HOME

# mise prints a lot of progress; the cause is in the trailing ERROR lines.
function Get-OneLine([string[]]$Output) {
    $summary = $Output | Where-Object { $_ -match 'ERROR|Error:|error:' -and $_ -notmatch 'ERROR (Version:|Run with)' } | Select-Object -Last 2
    if (-not $summary) { $summary = $Output | Select-Object -Last 2 }
    $text = ($summary -join ' ')
    if ($text.Length -gt 300) { $text = $text.Substring(0, 300) }
    $text
}

$errors = @()
try {
    $mise = (Get-Command mise -ErrorAction SilentlyContinue).Source
    if (-not $mise) {
        $mise = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\jdx.mise_*\mise\bin\mise.exe" -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $mise) {
        $errors += "mise not found"
        Write-UpdateLog "ERROR: mise not found"
    } else {
        $before = & $mise ls --current 2>$null
        $out = & $mise up 2>&1 | ForEach-Object { "$_" }
        $status = $LASTEXITCODE
        $after = & $mise ls --current 2>$null
        if ($status -ne 0) {
            $msg = "mise up (EXIT=$status): $(Get-OneLine $out)"
            $errors += $msg
            Write-UpdateLog "ERROR: $msg"
        } else {
            $changed = Compare-Object @($before) @($after) |
                       Where-Object { $_.SideIndicator -eq '=>' } |
                       ForEach-Object { $f = -split $_.InputObject; "$($f[0])@$($f[1])" }
            if ($changed) {
                Write-UpdateLog "OK: mise upgraded: $($changed -join ' ')"
            } else {
                Write-UpdateLog "OK: mise (no change)"
            }
        }
    }

    # A same-named CLI in node's global npm outside mise shadows the mise one on PATH,
    # and updates stop taking effect. Removing it is left to a human; only log it.
    foreach ($pkg in @('@openai\codex', '@anthropic-ai\claude-code')) {
        Get-ChildItem "$env:LOCALAPPDATA\mise\installs\node\*\node_modules\$pkg" -Directory -ErrorAction SilentlyContinue |
            ForEach-Object { Write-UpdateLog "WARN: $pkg outside mise at $($_.FullName) shadows PATH (remove with npm rm -g)" }
    }
} finally {
    Remove-Item -Recurse -Force $Lock -ErrorAction SilentlyContinue
}

if ($errors.Count -gt 0) {
    $line = "$((Get-Date).ToString('MM/dd')) $($errors -join ' / ')"
    if ($line.Length -gt 200) { $line = $line.Substring(0, 200) }
    Set-Content -Path $Failed -Value $line
    exit 1
}
Remove-Item -Force $Failed -ErrorAction SilentlyContinue
exit 0
