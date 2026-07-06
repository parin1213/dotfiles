{{- /*
  環境固有指示。判別は中央リゾルバ profile に集約（os / isWSL / machine / weight）。
  「OS で分ける」ではなく「意図（WSL の癖 / slim か / どのマシンか）」で分ける。
  編集は chezmoi source: home/.chezmoitemplates/agents-env.md。
*/ -}}
{{- $p := includeTemplate "profile" . | fromJson -}}
## この環境について
{{ if eq $p.os "windows" }}
- **このマシン = `local-pc`（Windows ネイティブ）**。想定シェルは PowerShell 5.1。
- bash 前提のツール（git-sweep 等）は WSL 内で実行する。
- PowerShell 5.1 は BOM なし UTF-8 を ANSI と誤認する。日本語を含む `.ps1` を編集したら UTF-8 BOM 付きで保存し直す。
- dotfiles は `~/src/dotfiles`（= `C:\Users\<user>\src\dotfiles`, chezmoi source）。`chezmoi apply` で配置。
- **WSL 非対話実行（`wsl -e bash -c`）の作法**（Codex に限らず WSL コマンド全般）:
  - コマンド文字列は**シングルクォート**（ダブルクォートだと `$HOME` 等が Windows 側で展開される事故が実際に起きた）
  - mise 管理ツールは `export PATH="$HOME/.local/share/mise/shims:$PATH"` を前置（非対話は shim が PATH 外）
  - foreground で回す（WSL の background は distro アイドル終了で死ぬ）。一時ファイルは HOME(ext4)
- 昇格（UAC / gsudo）が要る操作は実行前に「UAC が出ます」と予告してから実行する（不在時に出すとキャンセルされる）。ユーザー不在なら保留。
{{- else if $p.isWSL }}
- **このマシン = `local-pc` の WSL（Ubuntu・full）**。ログインシェルは zsh。
- dotfiles は `~/src/dotfiles`（git で同期）。`chezmoi apply` で配置。
- bash 前提のツール（git-sweep / codex 等）はこの WSL 内で実行する（Windows ネイティブは codex sandbox が動かない）。
- WSL 固有の癖: Windows 側 mise shim が PATH に漏れる／一時ファイルは ext4（HOME）に置く。
{{- else if eq $p.machine "raspi4" }}
- **このマシン = `{{ $p.machine }}`（Raspberry Pi・slim）**。素のシェル用途。
- 重いランタイム（ruby/python/node/dotnet 等）は入れない（mise は軽量ツールのみ）。必要時だけ個別に `mise use`。
- dotfiles は `~/src/dotfiles`（bundle 経由で同期）。`chezmoi apply` で配置。
{{- else if eq $p.os "linux" }}
- **このマシン = `{{ $p.machine }}`（Ubuntu・{{ $p.weight }}）**。
{{- if eq $p.weight "slim" }}
- slim 機（素のシェル用途）。重いランタイムは入れない（mise は軽量ツールのみ）。必要時だけ個別に `mise use`。
{{- else if eq $p.weight "lite" }}
- lite 機（低スペック）。agent core（node/python/claude-code/codex 等）までは入るが、重い/クラウド系（ruby/dotnet/gcloud/aws-cli/terraform/gemini-cli）は除外。必要時だけ個別に `mise use`。
{{- end }}
- dotfiles は `~/src/dotfiles`（git で同期）。`chezmoi apply` で配置。
{{- else if eq $p.os "darwin" }}
- **Mac（メイン機）**。Mac 固有の接続先・ツールは必要に応じてここに追記する。
{{- end }}

## SSH 接続先
- **このマシン = `{{ $p.machine }}`**。自己参照になる alias は使わない。
{{ if ne $p.machine "local-pc" -}}
- **`local-pc`** (Windows/WSL): `ssh local-pc`（Windows）/ `ssh local-pc-wsl`（WSL）。
{{ end -}}
{{- if ne $p.machine "raspi4" -}}
- **`raspi4`** (raspi4.local): 素のシェル。`ssh raspi4 <cmd>` で非対話コマンド実行可（接続情報は要設定）。
{{ end -}}
{{- if ne $p.machine "surface-go3" -}}
- **`surface-go3`**: Ubuntu（slim）。`ssh surface-go3 <cmd>`（接続情報は要設定）。
{{ end -}}
- **AWS SSM (`i-*` / `mi-*`)**: SSM `start-session` の ProxyCommand 経由。aws-cli / SSM プラグインと認証情報のセットアップが別途必要。

## 自作資産（この環境）
{{ if ne $p.os "darwin" }}
- **`~/scripts/git-sweep`**: ローカルブランチ整理（純 bash）。`git sweep report` → `prune -y`。`backup/*` は保護。{{ if or (eq $p.os "windows") $p.isWSL }}（WSL で実行）{{ end }}
- memory: `~/.claude/projects/.../memory/`（`MEMORY.md` がインデックス）。
- skills: 共有は `~/.agents/skills/`、Claude は `~/.claude/skills/`（`skills/manifest.toml` ＋ `setup.sh`/`setup.ps1` で復元）。
- 未移植（Mac 専用）: cmux / nippo / zd-notify(VOICEVOX) / redash-cli / dora 等はこのマシンに無い。
{{- else }}
- Mac 側の自作資産（cmux / nippo / zd-notify 等）は必要に応じてここに追記する。
{{- end }}
