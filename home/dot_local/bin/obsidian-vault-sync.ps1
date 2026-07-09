# Obsidian vault (~/obsidian-vault) auto git sync (Windows, PowerShell 5.1 compatible).
# Mirrors home/dot_local/bin/executable_obsidian-vault-sync (Unix) — same logic, same
# commit message format, same conflict handling (abort, never auto-resolve).
# Messages are English-only on purpose: this file is deployed by chezmoi without a BOM,
# and PowerShell 5.1 misreads non-ASCII in a BOM-less file.

$Vault = Join-Path $HOME "obsidian-vault"
$Log = Join-Path $HOME ".local\state\obsidian-vault-sync.log"

if (-not (Test-Path (Join-Path $Vault ".git"))) { exit 0 }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { exit 0 }

$logDir = Split-Path $Log -Parent
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

function Write-SyncLog([string]$Message) {
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    Add-Content -Path $Log -Value "$ts $Message"
}

function Invoke-LogRotate {
    if (Test-Path $Log) {
        $lines = Get-Content $Log
        if ($lines.Count -gt 1000) {
            $lines | Select-Object -Last 500 | Set-Content $Log
        }
    }
}
Invoke-LogRotate

# mkdir-based lock (atomic). Lives under .git/ so it is never picked up by `git add -A`.
# Stale (>30min) locks are assumed to be leftovers from a crashed previous run.
$Lock = Join-Path $Vault ".git\obsidian-vault-sync.lock"
if (Test-Path $Lock) {
    $age = (Get-Date) - (Get-Item $Lock).LastWriteTime
    if ($age.TotalMinutes -gt 30) {
        Remove-Item -Recurse -Force $Lock -ErrorAction SilentlyContinue
    } else {
        exit 0
    }
}
try {
    New-Item -ItemType Directory -Path $Lock -ErrorAction Stop | Out-Null
} catch {
    exit 0
}

try {
    Set-Location $Vault

    $status = git status --porcelain 2>$null
    if ($status) {
        git add -A
        $nowIso = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        git commit -m "vault backup (auto-sync): $nowIso" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-SyncLog "ERROR: git commit failed"
            exit 1
        }
    }

    $pullOut = git pull --no-rebase origin main 2>&1
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path (Join-Path $Vault ".git\MERGE_HEAD")) {
            git merge --abort 2>$null
            Write-SyncLog "CONFLICT: merge aborted, manual resolution needed"
        } else {
            $joined = ($pullOut | Out-String).Replace("`r", " ").Replace("`n", " ")
            $short = $joined.Substring(0, [Math]::Min(200, $joined.Length))
            Write-SyncLog "ERROR: git pull failed: $short"
        }
        exit 1
    }

    $ahead = git rev-list --count origin/main..HEAD 2>$null
    if (-not ($ahead -match '^\d+$')) { $ahead = 0 }
    if ([int]$ahead -gt 0) {
        git push origin main | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-SyncLog "ERROR: git push failed"
            exit 1
        }
        Write-SyncLog "OK: synced ($ahead commit(s) pushed)"
    } else {
        Write-SyncLog "OK: no changes to push"
    }
} finally {
    Remove-Item -Recurse -Force $Lock -ErrorAction SilentlyContinue
}
