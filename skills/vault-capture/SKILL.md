---
name: vault-capture
description: |
  汎用エンジニアリング知見（技術的ハマりどころ・価値判断の抽象化・公開可能レベルのエッセイ / Blog 素材）を
  個人 Obsidian vault（~/obsidian-vault）に記録するときに必ず参照する。
  「vault に記録して」「これ学びとして残して」「ハマりどころをメモしておいて」「ブログ素材にして」等で発火。
  業務セッション由来の内容は sanitization（抽象化）を通してから書く。
---

# vault への知見記録の定型フロー

記録先は `~/obsidian-vault`（private repo `parin1213/obsidian-vault`、全マシン共通の clone 先）。
記録規約の正本は vault 側の `AGENTS.md`（持ち込み基準）と `style-guide.md`（命名・プロパティ）。
**書く前に必ずこの 2 つを読む**（このスキルは入口とフローだけを持ち、規約は vault 側に一本化する）。

## 0. 前提確認

```sh
ls ~/obsidian-vault/AGENTS.md
```

無ければ記録せず、`git clone https://github.com/parin1213/obsidian-vault ~/obsidian-vault` をユーザーに案内する
（認証は各機で個別設定のため、勝手に clone を試みない）。

## 1. sanitize（業務由来なら必須）

`AGENTS.md` の持ち込み基準に従い、書く前に抽象化する:

- 社名・プロダクト名・チーム名・人名・顧客/候補者情報・内部 URL・未公開の事業数値を含めない
- 通過基準: 「この文章がこのまま Zenn / Blog に載っても問題ないか」
- 固有名詞は役割語へ置換（「業務プロダクト」「所属チーム」等）。迷ったら書かない

## 2. 置き場所の判断

- 既存ノートに同テーマがないか先に確認する（`grep -ril <キーワード> ~/obsidian-vault --include='*.md'`）。
  あれば追記、なければ新規
- 新規はルート直下（フォルダで分類しない）。frontmatter は style-guide 準拠:
  - 技術知見・ハマりどころ → `type: note` + `topic: [engineering]`、tags に `gotcha` / `til` 等
  - エッセイ / Blog 素材 → `type: essay`、公開前提の下書きは tags に `blog-draft`
- 関連ノートへ内部リンク（`[[...]]`）を張る。未解決リンクも可

## 3. 同期（CLI から書いたら push まで）

Obsidian が起動していない機では obsidian-git の auto-sync が走らないため、手動で完結させる:

```sh
cd ~/obsidian-vault
git pull --no-rebase origin main
git add <書いたファイルを明示>
git log -1 --pretty='%an <%ae>'   # parin1213 / schwarzhuckebein1213@gmail.com であること（業務 identity 混入禁止）
git commit -F <一時ファイル>       # 日本語メッセージ、Conventional prefix は英語
git push origin main
```

identity が業務のままなら `git config user.name parin1213; git config user.email schwarzhuckebein1213@gmail.com`
を per-repo で設定してからコミットする。
