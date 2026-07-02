# AGENTS.md — dotfiles リポジトリの設計思想（着手前に必ず読む）

このリポジトリは chezmoi source（`~/src/dotfiles` = `C:\dev\src\dotfiles`）。
グローバルな作業規約（言語/セキュリティ/git 等）は `~/.agents` / `~/.claude` 側の指示が正本。
ここには **このリポジトリ固有の「どこに何を書くと、どのスクリプトにどう効くか」** だけを書く。

> 迷ったら原則: **判定は1箇所・設定は1箇所・消費側は読むだけ**。新しい分岐や孤立スクリプトを
> 足したくなったら、まず「既存のどの軸に乗るか」を考える。乗らないなら軸を増やす設計判断であり、
> その場で勝手に作らず複数案を出して相談する。

## 4 つの軸（これが全ての出し分けの土台）

| 軸 | 値 | 何の鍵か | 正本 |
|---|---|---|---|
| **os**（platform） | windows / linux / darwin | provision の**入口**（bootstrap dispatcher） | `uname` / PATHEXT |
| **env** | win / wsl / surface / raspi / mac / linux | **設定表の行**（os と machine 文脈の混合キー） | `.chezmoidata.toml` |
| **machine** | local-pc / raspi4 / surface-go3 | 表示の出し分け・SSH 自己参照判定 | `profile` の if |
| **weight** | slim / lite / full | **mise が入れるツール量**（資源と用途） | `.chezmoidata.toml` |
| **app** | apps=[...] | infra の上に乗る**機能単位**（HA 等） | `.chezmoidata.toml` |

os=入口 / env=設定 / machine=表示 / weight=資源 / app=機能。**この5つは直交させる**。
新しい鍵（例: host 専用スクリプト）を増やすと軸が混ざり拡張不能になる。原則やらない。

## データの流れ（判定 → 表 → 消費）

```
  生の材料:  os / kernel(WSL) / hostname
        │
        ▼
  home/.chezmoitemplates/profile     ← 判定ロジックの唯一の置き場（machine と env を決める）
        │  envs.<env> の行を読む
        ▼
  home/.chezmoidata.toml [envs.<env>]  ← 設定の唯一の正本（全 env 明示）
        │
   ┌────┴───────────────┐
   ▼                    ▼
 chezmoi テンプレ        profile-env → DF_*（環境変数）
 （設定ファイル直読み）    （provision スクリプトが eval して読む）
  - mise: $p.weight      - install/linux.sh が DF_DOCKER / DF_APPS 等で分岐
  - starship/ghostty/WT
  - agents-env
```

- **判定（machine/env）は `profile` だけ**が持つ。他のどこにも hostname 分岐を書かない。
- **設定値は `.chezmoidata.toml` だけ**に書く。全 env を明示列挙する（欠落で fallback に化けるのを防ぐ）。
- 消費側（mise / starship / linux.sh …）は **読むだけ**。値の決定ロジックを持たせない。

## provision の層モデル（4 層）

```
OS ネイティブ(install/*)  →  CLI/runtime(mise)  →  設定(chezmoi apply)  →  app(install/apps/*)
  apt/brew/winget,            weight で                dotfiles 配置          infra の上に
  docker/sshd/tailscale       slim/lite/full           run_onchange           乗るアプリ
```

- 入口は OS 共通の `bootstrap`（Unix=`install/bootstrap`→linux/macos.sh、Win=`bootstrap.ps1`→windows.ps1）。
- **env 差は linux.sh の中で `DF_*` を見て吸収**する。bootstrap 自体は OS でしか分岐しない。
- 導入は**公式チャネル固定**（apt 公式リポ / 公式インストーラ）。署名・更新を本家に委譲する。
- 各節は**冪等**（入っていれば skip）。`==>` で何をしたかを 1 行ログ。

## 拡張レシピ（「X を足したい → ここを触る」）

| やりたいこと | 触る場所 |
|---|---|
| 新マシン追加 | `profile` の if に hostname→machine→env を1行 ＋ `.chezmoidata.toml` に `[envs.<name>]` |
| CLI ツール / 重さで出し分け | `home/dot_config/mise/config.toml.tmpl`（`weight` の slim/lite/full ブロック） |
| OS パッケージ | `install/packages/{apt.txt,Brewfile,winget-packages.json}`（※現状 env 差なし＝全 Linux 一律） |
| infra daemon（docker 等） | `.chezmoidata.toml` に列追加 → `profile` で素通し → `profile-env` で `DF_` → `linux.sh` に §節 |
| **アプリ（HA 等）** | `install/apps/<name>.sh` を置き、対象 env の `apps` に `"<name>"` を足す。**それだけ** |
| 共通エージェント指示 | `home/.chezmoitemplates/agents-common.md`（CLAUDE/AGENTS/GEMINI が取り込む） |
| エージェントスキル | `skills/manifest.toml` に宣言。apply の `run_onchange_after_skills-setup` が全環境へ配布（環境差は `requires` で宣言） |

### アプリ層の作法（app 軸）

- どの env に入れるかは `.chezmoidata.toml` の `envs.<env>.apps` が正本。
- `install/linux.sh` 末尾の apps runner が `DF_APPS` を回し `install/apps/<name>.sh` を実行する。
- 1 アプリが落ちても他は続行（infra と違いアプリは任意性が高い）。
- アプリが要求する infra（HA なら docker）は、その env のフラグを `true` にしておく（runner は infra を入れない）。
- アプリ固有ロジック（compose 定義等）は `install/apps/<name>.sh` に閉じ込める。**linux.sh の infra 節に混ぜない**。

## やってはいけない（過去にやりかけた筋の悪い手）

- **host 名のスクリプトを孤立させる**（例: `install/raspi.sh` を bootstrap からも表からも切り離して置く）。
  → どの軸にも紐付かず「どう効くのか分からない」状態になる。app は必ず `apps=[...]` 経由にする。
- **設定値を消費側に直書き**（linux.sh や mise に hostname 分岐を書く）。→ 判定は `profile`、値は表。
- **env を一部だけ表に書く**。→ 全 env 明示。欠けると `linux`(fallback) に化ける。
- **infra フラグとアプリを混同**（docker/sshd と HA を同じ扱いにする）。→ infra=bool フラグ、app=リスト。

## 設定ファイルと「正本」の所在

- デプロイ済み実体（`~/.zshrc` / `~/.claude/CLAUDE.md` 等）は**直接編集しない**。source を編集して `chezmoi apply`。
- ランタイムが再生成する設定（WT settings / zellij 等）は apply で `--force` 上書きが前提。
  保持したい値は**source 側に取り込む**（実体側の手編集は次の apply で消える）。
- HA の config（`~/homeassistant/config`）のような**実行時状態は chezmoi 管理しない**（`.storage/`・secrets を含む）。
  宣言的な定義（compose など）だけを source/スクリプト側に持つ。

## 配布

- 全環境への配布は `distribute.ps1`（push → 各 env で pull + `chezmoi apply --force`）。
- OS パッケージまで上げるのは `-Full`（apt upgrade + mise up + bootstrap）。通常運用は素の apply。
- 確認だけは `-DryRun`（incoming commit と chezmoi 差分を表示・無変更）。

---

詳細な背景・ハマり履歴は `README.md` を参照。**この 200 行に収まらない経緯は README か git log へ。**
