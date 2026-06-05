#requires -Version 5.1
<#
distribute.ps1 — dotfiles を全環境へ配る hub（local-pc から実行）。

毎回 push → 各環境で pull + chezmoi apply、を手で繰り返すのが面倒なので一発化する。
hub は local-pc（ssh で surface/raspi に届き、wsl は interop、自分は直接 apply）。

使い方:
  .\distribute.ps1                         push → 全環境 pull + chezmoi apply
  .\distribute.ps1 -DryRun                 変更せず確認だけ（incoming commit と chezmoi 差分）
  .\distribute.ps1 -Only surface-go3,wsl   対象環境を限定
  .\distribute.ps1 -NoPush                 push を省略（既に push 済みのとき）

設計メモ:
  - 環境定義は $envs に全 env 明示（local/ssh/wsl）。追加はここに1行。
  - applylog は run_after で毎回 chezmoi status に出る純ログなので残差判定から除外。
  - 1 環境が落ちても他は続行（最後に失敗環境を要約）。
#>
[CmdletBinding()]
param(
  [switch]$DryRun,
  [string[]]$Only,
  [switch]$NoPush
)
$RepoRoot = $PSScriptRoot

# 環境定義（全 env 明示）。Kind: local / ssh / wsl。
$envs = @(
  [pscustomobject]@{ Name = 'local-pc';    Kind = 'local' }
  [pscustomobject]@{ Name = 'surface-go3'; Kind = 'ssh'   }
  [pscustomobject]@{ Name = 'raspi4';      Kind = 'ssh'   }
  [pscustomobject]@{ Name = 'wsl';         Kind = 'wsl'   }
)
if ($Only) { $envs = $envs | Where-Object { $Only -contains $_.Name } }

# Linux（ssh/wsl）で走らせるスニペット。mise shim を PATH 前置し chezmoi/mise を解決。
$pfx = 'export PATH="$HOME/.local/share/mise/shims:$PATH"; cd ~/src/dotfiles && '
$snApply = $pfx + 'git pull --ff-only && chezmoi apply --source ~/src/dotfiles && { printf "[applied] residual: "; chezmoi status --source ~/src/dotfiles 2>/dev/null | grep -v applylog | tr "\n" " "; echo "(clean if empty)"; }'
$snDry   = $pfx + 'git fetch -q origin master; echo "[incoming]"; git --no-pager log --oneline HEAD..origin/master; echo "[drift]"; chezmoi status --source ~/src/dotfiles 2>/dev/null | grep -v applylog || true'

$failed = @()

# 未コミット警告（remote には push されないため）。
$dirty = git -C $RepoRoot status --porcelain
if ($dirty -and -not $DryRun) {
  Write-Warning "未コミットの変更があります（remote へは push されません。local-pc の apply にのみ反映）:"
  $dirty | ForEach-Object { Write-Host "    $_" }
}

# push（通常時のみ）。
if (-not $DryRun -and -not $NoPush) {
  Write-Host "==> git push origin master"
  git -C $RepoRoot push origin master
  if ($LASTEXITCODE -ne 0) { Write-Warning "push 失敗。中断します。"; return }
}

foreach ($e in $envs) {
  $tag = "$($e.Name) ($($e.Kind))" + $(if ($DryRun) { ' [dry-run]' } else { '' })
  Write-Host "`n========== $tag =========="
  try {
    switch ($e.Kind) {
      'local' {
        $cm = (Get-Command chezmoi -ErrorAction SilentlyContinue).Source
        if (-not $cm) { throw 'chezmoi が解決できない（mise activate 済みシェルで実行）' }
        if ($DryRun) {
          git -C $RepoRoot fetch -q origin master
          Write-Host '[unpushed]'; git -C $RepoRoot --no-pager log --oneline origin/master..HEAD
          Write-Host '[drift]';    & $cm status --source $RepoRoot 2>$null | Where-Object { $_ -notmatch 'applylog' }
        } else {
          # local-pc は commit 元なので pull しない（push 済み前提）。apply のみ。
          & $cm apply --source $RepoRoot
          if ($LASTEXITCODE -ne 0) { throw "chezmoi apply 失敗 (exit $LASTEXITCODE)" }
          $res = & $cm status --source $RepoRoot 2>$null | Where-Object { $_ -notmatch 'applylog' }
          if ($res) { Write-Host ("[applied] residual: " + ($res -join ' ')) } else { Write-Host '[applied] clean' }
        }
      }
      'ssh' {
        ssh -o ConnectTimeout=10 $e.Name $(if ($DryRun) { $snDry } else { $snApply })
        if ($LASTEXITCODE -ne 0) { throw "ssh 失敗 (exit $LASTEXITCODE)" }
      }
      'wsl' {
        wsl -e bash -lc $(if ($DryRun) { $snDry } else { $snApply })
        if ($LASTEXITCODE -ne 0) { throw "wsl 失敗 (exit $LASTEXITCODE)" }
      }
    }
  } catch {
    Write-Warning "$($e.Name): $_"
    $failed += $e.Name
  }
}

Write-Host "`n==> 完了$(if ($DryRun) { '（dry-run: 何も変更していません）' })"
if ($failed) { Write-Warning ("失敗した環境: " + ($failed -join ', ')) }
