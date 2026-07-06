---
name: chezmoi-change
description: |
  環境設定（dotfiles / シェル / エディタ / エージェント指示 / mise / starship / WT / zellij 等）を変更するときに必ず参照する。
  source 特定 → 編集 → apply → 検証 → 配布の定型フローと、実体直編集・ハング・グリフ消失・BOM の罠を定める。
  「実体を直接編集しない」ルールが即修正の局面で 4 回破られた実績（2026-06）への手順的な対策。
---

# chezmoi 環境変更の定型フロー

## 0. 実体を触る前のゲート（最重要）

設定ファイルの実体を Edit/Write しようとしたら、**その前に必ず**:

```sh
chezmoi managed <path>   # 管理下か確認（chezmoi source-path <path> で source 位置が出る）
```

- 管理下 → source（`~/src/dotfiles`）を編集する。実体は触らない。
- 管理外 → そのアプリが**実際に読むパス**を確認する（zellij が `%APPDATA%\Zellij\config` を読んでいて
  chezmoi 管理下の config を直しても効かなかった実績）。恒久設定は source に取り込んでから配る。

## 1. 編集時の罠

- **Nerd Font 私有領域グリフ**（starship_icon 等）を含むファイルは全書き換え（Write）禁止。部分 Edit のみ。
  編集後に `git diff` でグリフが空に化けていないか確認（化けたら git のバイトから復元）。
- **日本語を含む `.ps1`** は UTF-8 **BOM 付き**で保存し直す（PS 5.1 が ANSI と誤認する）。
- `.chezmoidata.toml` は**全 env 明示列挙**（欠落は fallback に化ける）。

## 2. apply

- `chezmoi diff` で対象を確認してから apply。
- **非対話 apply は対話プロンプトでハングする**（実体が外部変更されているとき）。
  ランタイムが書き換えるファイル（WT settings / `.claude/settings.json` 等）は、保持したい値を先に source へ取り込み、
  apply は `--force`。二重 apply は lock 競合でもハングする。

## 3. 検証 → コミット → 配布

- 表示系（starship / ghostty / WT）は**実際の表示**を確認してから完了とする（アイコン消失を配布後にユーザーが発見した実績）。
- コミットは対象ファイル明示 add ＋ `git commit -F <一時ファイル>`。
- **配布の王道: commit → push → 各環境で pull ＋ apply**（「必ず順守せよ」）。SSH で実体を直接いじらない。
  全環境配布は `distribute.ps1`（確認だけは `-DryRun`、OS パッケージまで上げるのは `-Full`）。
  sudo 事情: raspi4 のみ NOPASSWD。surface-go3 / WSL で sudo が要る手順は `! ssh -t ...` をユーザーに案内。
- 変更したら配布まで行うか、「配布は保留（理由）」を報告に明記する（配布忘れが摩擦になった実績）。
