#requires -Version 5.1
<#
distribute.ps1 — dotfiles を全環境へ配る hub（local-pc から実行）。

毎回 push → 各環境で pull + chezmoi apply、を手で繰り返すのが面倒なので一発化する。
hub は local-pc（ssh で surface/raspi に届き、wsl は interop、自分は直接 apply）。

使い方:
  .\distribute.ps1                         push → 全環境 pull + chezmoi apply
  .\distribute.ps1 -Full                   フル更新（pull + apt upgrade + mise up + bootstrap + apply）
  .\distribute.ps1 -DryRun                 変更せず確認だけ（incoming commit と chezmoi 差分）
  .\distribute.ps1 -Only surface-go3,wsl   対象環境を限定
  .\distribute.ps1 -NoPush                 push を省略（既に push 済みのとき）

-Full の中身:
  - Linux(ssh/wsl): git pull → sudo apt update && apt upgrade -y → mise up → bootstrap(provision) → chezmoi apply
  - local-pc(Windows): apt が無いので mise up → bootstrap(winget import) → chezmoi apply（winget upgrade --all はしない）
  - sudo を使うため ssh は -t で TTY を割り当てる。パスワードが要る機ではプロンプトが出る。時間もかかる。
  - 通常運用は素の apply（軽量）。-Full は OS パッケージまで上げたい時だけ。-DryRun と併用時は -DryRun 優先（無変更）。

設計メモ:
  - 環境定義は $envs に全 env 明示（local/ssh/wsl）。追加はここに1行。
  - applylog は run_after で毎回 chezmoi status に出る純ログなので残差判定から除外。
  - apply は --force。zellij 等がデプロイ済み config を自動再生成すると chezmoi が
    「外部変更あり、上書きする?」を対話確認しようとし、非対話 ssh では TTY 無しで失敗するため。
    デプロイ済みは source から再生成可能（source が正本）の方針に沿う。保持したいランタイム値は
    source 側に入れる（例: settings.json）。確認だけしたいときは -DryRun。
  - 1 環境が落ちても他は続行（最後に失敗環境を要約）。
#>
[CmdletBinding()]
param(
  [switch]$DryRun,
  [switch]$Full,
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

# Linux（ssh/wsl）で走らせるスニペット。~/.local/bin（mise 本体・bootstrap shim）と
# mise shim を PATH 前置し mise/chezmoi/bootstrap を非対話でも解決。
$pfx = 'export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"; cd ~/src/dotfiles && '
$snApply = $pfx + 'git pull --ff-only && chezmoi apply --force --source ~/src/dotfiles && { printf "[applied] residual: "; chezmoi status --source ~/src/dotfiles 2>/dev/null | grep -v applylog | tr "\n" " "; echo "(clean if empty)"; }'
$snDry   = $pfx + 'git fetch -q origin master; echo "[incoming]"; git --no-pager log --oneline HEAD..origin/master; echo "[drift]"; chezmoi status --source ~/src/dotfiles 2>/dev/null | grep -v applylog || true'
# -Full: OS パッケージ(apt upgrade) + mise up + bootstrap(provision) まで含む重い更新。
# DEBIAN_FRONTEND=noninteractive で debconf プロンプトを抑止（sudo 自体のパスワードは別途 -t で対話）。
$snFull  = $pfx + 'git pull --ff-only && echo "[apt] update && upgrade" && sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y && echo "[mise] up" && mise up && echo "[bootstrap]" && ./install/bootstrap && chezmoi apply --force --source ~/src/dotfiles && { printf "[full applied] residual: "; chezmoi status --source ~/src/dotfiles 2>/dev/null | grep -v applylog | tr "\n" " "; echo "(clean if empty)"; }'

$failed = @()

if ($Full -and -not $DryRun) {
  Write-Host "==> -Full: 各環境で apt upgrade / mise up / bootstrap も実行します（sudo パスワードを要求される場合あり・時間がかかります）" -ForegroundColor Yellow
}

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
  $tag = "$($e.Name) ($($e.Kind))" + $(if ($DryRun) { ' [dry-run]' } elseif ($Full) { ' [full]' } else { '' })
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
          if ($Full) {
            # local-pc(Windows): apt は無い。mise up → bootstrap(winget import) まで上げる。
            Write-Host '[mise] up'
            & mise up
            if ($LASTEXITCODE -ne 0) { throw "mise up 失敗 (exit $LASTEXITCODE)" }
            Write-Host '[bootstrap]'
            & (Join-Path $RepoRoot 'install\bootstrap.ps1')   # 失敗時は内部 Stop で throw → catch
          }
          # local-pc は commit 元なので pull しない（push 済み前提）。apply のみ。
          & $cm apply --force --source $RepoRoot
          if ($LASTEXITCODE -ne 0) { throw "chezmoi apply 失敗 (exit $LASTEXITCODE)" }
          $res = & $cm status --source $RepoRoot 2>$null | Where-Object { $_ -notmatch 'applylog' }
          if ($res) { Write-Host ("[applied] residual: " + ($res -join ' ')) } else { Write-Host '[applied] clean' }
        }
      }
      'ssh' {
        $sn = if ($DryRun) { $snDry } elseif ($Full) { $snFull } else { $snApply }
        if ($Full -and -not $DryRun) {
          ssh -t -o ConnectTimeout=10 $e.Name $sn       # sudo(apt) のため TTY 割当
        } else {
          ssh -o ConnectTimeout=10 $e.Name $sn
        }
        if ($LASTEXITCODE -ne 0) { throw "ssh 失敗 (exit $LASTEXITCODE)" }
      }
      'wsl' {
        $sn = if ($DryRun) { $snDry } elseif ($Full) { $snFull } else { $snApply }
        wsl -e bash -lc $sn
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
