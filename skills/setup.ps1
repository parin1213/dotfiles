#Requires -Version 5.1
# skills/setup.ps1 — manifest.toml を読んでエージェントスキルを導入（Windows / restore フェーズ）。
# setup.sh（bash; WSL/raspi/mac 用）の Windows 版。挙動は同じ。
#
# 配置先（Agent Skills 仕様準拠の 2 ターゲット）:
#   - Claude : ~/.claude/skills        （gh skill の --agent claude-code）
#   - 共有   : ~/.agents/skills          （--dir 指定。Codex / Cursor / Gemini CLI 等が読む標準 dir）
#
# 前提（restore 順: install\bootstrap.ps1（windows provision）→ chezmoi apply(mise install) → これ）:
#   gh(>=2.90), yq(mise) が PATH 上。type=tool は対応ツールが mise 導入済みのこと。
# 使い方: powershell -ExecutionPolicy Bypass -File .\skills\setup.ps1

$Here      = $PSScriptRoot
$RepoRoot  = Split-Path -Parent $Here
$Man       = Join-Path $Here 'manifest.toml'
$SharedDir = Join-Path $env:USERPROFILE '.agents\skills'

foreach ($c in 'yq', 'gh') {
  if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { Write-Host "ERROR: $c が無い（mise install 後に実行）"; exit 1 }
}
New-Item -ItemType Directory -Force $SharedDir | Out-Null

function Get-Toml([string]$Expr) { (& yq -p toml -o yaml $Expr $Man) }

# Claude(~/.claude/skills) と 共有(~/.agents/skills) の両方へ install。
function Install-Both([string]$Target, [string]$Name, [string[]]$Extra) {
  & gh skill install $Target $Name @Extra --agent claude-code --scope user -f
  & gh skill install $Target $Name @Extra --dir $SharedDir -f
}

$n = [int](Get-Toml '.skill | length')
for ($i = 0; $i -lt $n; $i++) {
  $name = Get-Toml ".skill[$i].name"
  $type = Get-Toml ".skill[$i].type"

  # requires: 指定バイナリが無い環境では skip
  $req = Get-Toml ".skill[$i].requires"
  if ($req -and $req -ne 'null' -and -not (Get-Command $req -ErrorAction SilentlyContinue)) {
    Write-Host "==> [$name] requires '$req' 未導入のため skip"; continue
  }

  switch ($type) {
    'tool' {
      $cmd = Get-Toml ".skill[$i].install"
      $bin = ($cmd -split '\s+')[0]
      if (Get-Command $bin -ErrorAction SilentlyContinue) {
        Write-Host "==> [$name] tool: $cmd"; Invoke-Expression $cmd
      } else { Write-Host "==> [$name] tool: '$bin' 未導入のため skip" }
    }
    'ghskill' {
      $repo  = Get-Toml ".skill[$i].repo"
      $skill = Get-Toml ".skill[$i].skill"; if ($skill -eq 'null') { $skill = $name }
      $pin   = Get-Toml ".skill[$i].pin"
      $extra = @(); if ($pin -and $pin -ne 'null') { $extra = @('--pin', $pin) }
      Write-Host "==> [$name] ghskill: $repo $skill"
      Install-Both $repo $skill $extra
    }
    'own' {
      # ① 自作 / ④ 採用: 既定はこのリポ。from でローカルパス指定可（Windows では PowerShell 式で）。
      $src = $RepoRoot
      $fromexpr = Get-Toml ".skill[$i].from"
      if ($fromexpr -and $fromexpr -ne 'null') { $src = Invoke-Expression $fromexpr }
      if (Test-Path $src) {
        Write-Host "==> [$name] own (from-local: $src)"; Install-Both $src $name @('--from-local')
      } else { Write-Host "==> [$name] own: source '$src' が無いため skip" }
    }
    default { Write-Host "ERROR: unknown type '$type' for skill '$name'"; exit 1 }
  }
}
Write-Host "==> skills setup done"
