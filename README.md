# dotfiles

[![Managed with chezmoi](https://img.shields.io/badge/managed%20with-chezmoi-3b5fc0)](https://www.chezmoi.io/)
![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Linux%20%7C%20Windows-555)
![Tooling: mise](https://img.shields.io/badge/tooling-mise-fa6a8e)
[![Prompt: starship](https://img.shields.io/badge/prompt-starship-DD0B78?logo=starship&logoColor=white)](https://starship.rs/)

複数 OS（macOS / Linux: WSL・Ubuntu・Debian・Raspberry Pi / Windows）の個人環境を
**[chezmoi](https://www.chezmoi.io/)** で一元管理する。新しいマシンを **2 ステップ**で復元できる。

配置先は全 OS 共通で `~/src/dotfiles`（各環境に clone し git で同期。chezmoi の sourceDir もここ）。

---

## セットアップ

新マシンの復元は **① provision → ② restore** の 2 ステップ。

### 1. リポジトリを置く

```sh
git clone https://github.com/parin1213/dotfiles ~/src/dotfiles
cd ~/src/dotfiles
```

> remote が無い新規マシンへは、別マシンで `git bundle create dotfiles.bundle master` → 転送 → `git clone -b master dotfiles.bundle ~/src/dotfiles`。

### 2. provision（OS ネイティブ層を入れる）

mise で入らないもの（mise 本体・ビルド土台・zsh・GUI/フォント）だけを OS のパッケージ管理で入れる。
入口は **OS 共通で `bootstrap` 一語**（`code` のように、名前が OS ごとに正しい実体へ解決される）。

| OS | コマンド | 委譲先 / 入るもの |
|---|---|---|
| macOS / Linux | `./bootstrap` | `uname` で `bootstrap-macos.sh` / `bootstrap-linux.sh` へ |
| Windows (PowerShell) | `.\bootstrap.ps1` | `bootstrap-windows.ps1`（winget import ＋ chezmoi） |

- 初回は repo 直下で `./bootstrap`（Unix）/ `.\bootstrap.ps1`（Windows）。`chezmoi apply` 後は
  `~/.local/bin` の shim 経由で**どこでも `bootstrap` 一語**で再実行できる（この dir は全 OS で PATH 上）。
- Linux 系（WSL / Ubuntu / Debian / Raspberry Pi）で**何を入れるか**は環境ごとに違う。これは
  `home/.chezmoidata.toml` の `envs.<env>` 能力フラグ（`op` / `op_interop` / `gui_apps` /
  `tailscale` / `docker` / `sshd`）が**正本**で、`bootstrap-linux.sh` は `chezmoi execute-template`
  でそれを読み込み（`DF_*`）分岐するだけ（環境判定の重複を排除）。
- 各 bootstrap が `~/.config/chezmoi/chezmoi.toml`（`sourceDir` = clone 先を自動導出）も生成する。
- 認証が要るもの（`tailscale up` / `op signin` / 1Password アプリ連携）はユーザー本人が行う。

### 3. restore（設定を復元する）

```sh
chezmoi diff      # 差分確認
chezmoi apply     # 設定配置 ＋ mise install ＋ fzf-tab clone ＋ 背景画像（すべて自動）
exec zsh -l       # 反映（Windows は新しい PowerShell を開く）
```

> remote 登録済みなら、1〜3 は `chezmoi init --apply parin1213/dotfiles` 一発でも可（sourceDir は chezmoi 既定）。

---

## アーキテクチャ

### 2 フェーズ（provision / restore）

- **provision** = `bootstrap-{os}`：mise で入らない **OS ネイティブ層**だけを入れる。
- **restore** = `chezmoi apply`：設定ファイルを配置し、CLI/ランタイムの `mise install`（`run_onchange`）と
  fzf-tab の clone（`.chezmoiexternal.toml`）を **apply 中に自動実行**。

### 3 層モデル

| 層 | 担当 | 例 |
|---|---|---|
| OS ネイティブ | `bootstrap-{os}` | mise 本体・git・ビルド土台・zsh・ghostty / Terminal・フォント |
| CLI / ランタイム | **mise** | node / python / ruby / deno / rust / gh / rg / fd / eza / zoxide / starship … |
| 設定・プラグイン・画像 | **chezmoi** | dotfiles・fzf-tab・背景画像 |

### OS / ホスト判定

- OS 分岐：`{{ .chezmoi.os }}`（`windows` / `darwin` / `linux`）。
- WSL 判定：`.chezmoi.kernel.osrelease` に `microsoft` を含むか。
- **Raspberry Pi 判定：hostname が `raspi*`**（OS は Debian でも Pi として扱う）。
- これら判定は `home/.chezmoitemplates/profile`（中央リゾルバ）に集約。env→設定値・能力フラグは
  `home/.chezmoidata.toml` の正本表に全列挙し、consumer（mise / starship / ghostty / **bootstrap**）は
  読むだけ。bootstrap は `profile-env` partial を `chezmoi execute-template` で `DF_*` に落として読む。

---

## リポジトリ構成

`.chezmoiroot` で chezmoi のソースルートを `home/` に向けている。直下の補助物
（`README.md` / `Brewfile` / `bootstrap-*.{sh,ps1}` / `winget-packages.json` / `skills/`）は chezmoi 管理外。

```
dotfiles/
├── Brewfile / Brewfile.optional # macOS の brew bundle
├── bootstrap / bootstrap.ps1    # OS 共通入口（uname / pwsh で OS 別 provision へ委譲）
├── bootstrap-macos.sh           # macOS provision
├── bootstrap-linux.sh           # Linux 系 provision（.chezmoidata.toml の能力フラグで出し分け）
├── bootstrap-windows.ps1        # Windows provision
├── distribute.ps1               # 全環境へ配る hub（local-pc から push→各機 pull+apply。-DryRun 可）
├── winget-packages.json         # Windows GUI/システムアプリ（CLI は mise）
├── skills/                      # エージェントスキル管理（manifest.toml + setup.sh/.ps1 + 自作/採用 skill）
└── home/                        # chezmoi ソース（dot_ 命名 / .chezmoiroot）
    ├── .chezmoidata.toml        # 環境ごとの正本表（weight / 能力フラグ op・docker… を全 env 列挙）
    ├── .chezmoiignore           # OS ごとに適用対象を出し分け（テンプレ）
    ├── .chezmoiexternal.toml    # 外部 git（fzf-tab を ~/.local/share に clone）
    ├── Pictures/                # 背景画像 sakura.jpg / ajisai.jpg（linux は除外）
    ├── .chezmoitemplates/       # 共有テンプレ partial（profile / profile-env / agents-common / agents-env）
    ├── dot_local/bin/           # ~/.local/bin（bootstrap 名前解決 shim 等）
    ├── dot_agents/ dot_claude/ dot_codex/ dot_gemini/   # エージェント指示（.tmpl）
    ├── dot_zshrc / dot_zshenv / dot_zprofile / dot_tmux.conf
    ├── dot_config/
    │   ├── shell/common.sh             # zsh/bash 共通層（Unix）
    │   ├── starship.toml.tmpl          # プロンプト（OS ロゴを表示）
    │   ├── mise/config.toml.tmpl       # OS 分岐 ＋ raspi は slim
    │   ├── ghostty/ / gh/ / zellij/
    │   └── …
    ├── Documents/…/Microsoft.PowerShell_profile.ps1            # Windows
    └── AppData/…/WindowsTerminal/…/settings.json.tmpl          # Windows（背景画像パス注入）
```

---

## 使い方（日々の編集）

symlink ではなく chezmoi がソースから展開する。ターゲットを直接編集したらソースへ取り込む。

```sh
chezmoi edit ~/.zshrc                  # ソースを編集（apply まで一括）
vim ~/.zshrc && chezmoi add ~/.zshrc   # 直接編集した実ファイルをソースへ取り込む
chezmoi diff && chezmoi apply          # 差分確認 → 反映
```

### 全環境へ配る（local-pc から）

1 台で直したら、`distribute`（= repo 直下 `distribute.ps1`／`~/.local/bin` shim 経由でどこでも）で
push → 各環境 pull + `chezmoi apply` を一括実行する。`-DryRun` で「何が来て何が変わるか」だけ確認できる。

```powershell
distribute -DryRun                 # 確認のみ（incoming commit と chezmoi 差分。変更しない）
distribute                         # push → 全環境 pull + apply
distribute -Only surface-go3,wsl   # 対象環境を限定
distribute -NoPush                 # push 済みのとき（pull + apply だけ）
```

対象は local-pc / surface-go3 / raspi4 / wsl（`distribute.ps1` の `$envs` に明示）。1 環境が落ちても
他は続行し、最後に失敗環境を要約する。`applylog`（run_after の純ログ）は差分判定から除外。

---

## 仕様・詳細

### OS 差分の出し分け

- **適用対象**：`home/.chezmoiignore`（テンプレ）。例：`.zshrc` / `mise` / `gh` / `shell` は Windows で無視、
  `Documents` / `AppData` / `statusline.ps1` は非 Windows で無視、`Pictures` は linux で無視。
- **1 ファイル内 OS 分岐**：`*.tmpl` ＋ `{{ if eq .chezmoi.os "windows" }}…{{ end }}`。

### mise ツールセット

- **全 OS 共通の軽量 CLI**：`rg` / `fd` / `eza` / `zoxide` / `starship` / `gh` / `jq` / `yq` / `gitleaks` / `ast-grep` / `zellij` / `chezmoi`。
- **raspi 以外**はこれに加えてフルセット：`node` / `python` / `ruby` / `deno` / `rust` / `terraform` / `dotnet` / `gcloud` / `aws-cli` / npm・pipx パッケージ等。
- **raspi は slim**（hostname `raspi*` で自動）。コンパイル系（ruby/python）や大型 DL（dotnet/gcloud）を除外。
- mise config は全 OS 管理（Windows は `config.toml.tmpl` の raw 文字列で `{{ version }}` 記法の衝突を回避）。

### プロンプト（starship）

先頭に **OS ロゴ**を表示し、どの環境かひと目で分かる。starship 標準 `[os]` モジュール。

| 環境 | ロゴ |
|---|---|
| Windows / macOS | Windows / Apple |
| Ubuntu / Debian | Ubuntu / Debian |
| Raspberry Pi | Pi（hostname `raspi*`。OS が Debian でも Pi ロゴ） |

### エージェント指示（.agents / Claude / Codex / Gemini）

共通指示の正本は `home/.chezmoitemplates/agents-common.md`。各ツールの指示は、これと環境固有 partial
（`agents-env.md`）を `includeTemplate` で合成して生成する。

| 出力 | 構成 |
|---|---|
| `~/.agents/AGENTS.md` | 共通 ＋ 環境固有 |
| `~/.claude/CLAUDE.md` | 共通 ＋ 環境固有 ＋ Claude 固有（rate limit / permissions / モデル運用） |
| `~/.codex/AGENTS.md` | 共通 ＋ 環境固有 ＋ Codex 固有 |
| `~/.gemini/GEMINI.md` | 共通 ＋ 環境固有 |

共通指示を直す → `agents-common.md` を編集 → `chezmoi apply`（全ツールへ波及）。

### 外部依存（chezmoi 管理外）

無くても無音でスキップされるだけ。新環境で「効かない」時はここを疑う。

| 依存 | 用途 | 用意方法 |
|---|---|---|
| `~/.local/share/fzf-tab` | zsh 補完強化 | chezmoi external が自動で clone/更新（全 OS） |
| `~/.zfunc/_dora` | `helpdora`（mise: `npm:helpdora`）の zsh 補完 | `helpdora completion zsh > ~/.zfunc/_dora`（任意） |
| LM Studio CLI (`lms`) | PowerShell の `lmsi` / `lmsq` 関数 | LM Studio を手動インストール |

---

## スキル管理（エージェントスキル）

エージェントスキル（`~/.claude/skills/` 等）は**出所で 4 型に分けて管理**する。宣言は `skills/manifest.toml`、復元は `skills/setup.sh`（restore で実行）。

| 型 | 取得方法 | 正本 | 例 |
|---|---|---|---|
| **① 自作** | このリポの `skills/<name>/` を `gh skill install --from-local` | dotfiles | 今後の独自 skill |
| **② コマンド付属（公式）** | ツール同梱の skill-deploy コマンド | ツール（mise で版固定） | 例: `sentry cli setup`（skill 版をバイナリに一致させたい時の代替）。現状の manifest では未使用 |
| **③ gh skill（独立配布・信頼・公式上流）** | `gh skill install <org/repo> <skill>`（必要なら `--pin <ver>`。Claude＋共有へ） | 上流 repo（公式は latest 追従可） | `playwright-cli`（`microsoft/playwright-cli`）/ `sentry-cli`（`getsentry/cli`、`plugins/` 規約で同梱） |
| **④ 野良（未検証）** | **検収フロー**で取り込んで判断 → ①/③ へ昇格 | 採用後に確定 | `/grill-me` 等の個人配布 |

- 配置: `skills/`（追跡）= ①自作 ＋ ④から採用した skill。`skills-staging/`（gitignore）= ④検収中。
- **配置先（2 ターゲット）**: Claude=`~/.claude/skills`（`--agent claude-code`）/ 共有=`~/.agents/skills`（`--dir`。Codex / Cursor / Gemini CLI 等が読む標準 dir）。**両 dir は別物**（Claude は `.agents/skills` を読まない）。
  - 注: `gh skill --agent codex` は `~/.codex/skills` へ入れるが Codex の標準読取は `.agents/skills` なので、Codex 向けは `--dir ~/.agents/skills` に固定する。
- 復元: `manifest.toml` を type 別に **Claude＋共有の両方へ**導入（②=ツールのコマンド、③=`gh skill`、①/④=`--from-local`）。
  - WSL / raspi / mac: `./skills/setup.sh`（bash）
  - Windows: `powershell -ExecutionPolicy Bypass -File .\skills\setup.ps1`（同等の PowerShell 版）

### 野良(④)の検収フロー（取り込み → 判断 → 昇格）

```sh
gh skill preview <repo> <skill>                              # 1. 入れずに中身確認
gh skill install <repo> <skill> --dir skills-staging/<name>  # 2. 隔離（agent dir を汚さない）
# 3. SKILL.md / scripts / allowed-tools を精査（危険コマンド・外部送信）。必要なら --scope project で試用
mv skills-staging/<name> skills/<name>                       # 4. OK → ①自作扱いで固める（上流改変から隔離・既定）
#   （上流を信頼するなら manifest に ③ として pin。NG なら staging を破棄）
```

新規 skill の振り分け: 公式上流が gh skill で配布（`plugins/` 規約 or `.well-known/skills/`）→**③**（公式は latest 可・他は信頼 org を pin）/ それが無くツール同梱の deploy コマンドのみ→**②** / 自作→**①** / それ以外→**④**（必ず検収、既定は repo に固める）。

---

## 秘密の扱い

- 秘密はリポジトリに入れない。
- `~/.gitconfig` の `[user]` は別管理（`~/.gitconfig.local` 等）。identity はリポに置かない。
- `gh` の `hosts.yml`（トークン）、Claude の `.credentials.json`、Codex の `auth.json` は対象外。

---

## 既知の制約 / ロードマップ

- `.gitconfig` / `.bashrc` は未管理（identity 破壊・bash 退行回避）。テンプレ化は今後。
- `~/.agents/skills/` の chezmoi 取り込みは未着手。
- macOS 固有の環境指示（`agents-env.md` の darwin 分岐）は雛形のみ。Mac 運用時に追記。
