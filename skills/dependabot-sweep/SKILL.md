---
name: dependabot-sweep
description: |
  Dependabot / Renovate 等の bot PR を一括処理する依頼（「dependabot を順次処理して」「bot PR をマージして」）を
  受けたときに必ず参照する。repo 規約の確認、CI 確認、lock 競合を避けた逐次マージ、major 失敗時の対処を定める。
  2 セッションで同型の長い手順を口頭再発明していたことに基づく（2026-06）。
---

# bot PR 一括処理

## 手順

1. **列挙**: `gh search prs --author app/dependabot --state open`（Renovate は `app/renovate`）で対象 repo 横断の open PR を列挙。
   除外指定（「score-checker 以外」等）を先に確認。
2. **repo 規約の確認**（repo ごとに必ず）: AGENTS.md / CLAUDE.md / branch protection を見る。
   既知の例: zundone-cli / helpdora = **squash only・CI(test) 必須・strict**、release-please 運用。lgtv-switcher = Renovate（.NET）。
3. **1 repo 内は逐次マージ**: lockfile 競合を避けるため並列マージしない。
   マージ → 次の PR が conflict になったら `@dependabot rebase` コメント → rebase 完了を待って CI green を確認 → マージ。
   - **group PR は rebase で新番号に再作成される**ことがある（旧番号の close を「失敗」と誤読しない）。
4. **CI が赤い PR**: 原因を見る。
   - major bump で runtime 要件が上がった（例: engines）→ **最新 LTS へ引き上げて通す**のがユーザーの既定方針（Node は「LTS の最新がいいな」）。
   - flaky → rerun。本質的な非互換 → スキップして報告に残す（勝手に close しない）。
5. **セキュリティアラート**は PR 処理と別枠で確認（`gh api repos/{owner}/{repo}/dependabot/alerts`）。
   transitive の場合は overrides（pnpm `overrides`）で対処した実績あり。
6. **完了報告**: repo ごとに「マージ N 件 / スキップ N 件（理由）」＋ main CI の最終状態。
   スキップ分は [判断待ち] として冒頭に分離。

## 禁止

- `git add -A` 相当の一括操作・force push・規約外のマージ方式（merge commit 等）
- CI 未確認マージ（「たぶん通る」で押さない）
