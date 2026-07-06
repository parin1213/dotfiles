{{- /*
  共通エージェント指示（全ツール・全環境共通）の正本。
  Claude(CLAUDE.md) / Codex(AGENTS.md) / Gemini(GEMINI.md) / ~/.agents/AGENTS.md が
  chezmoi の {{ template "agents-common.md" . }} で取り込む。
  共通指示を直したいときは、このファイル（chezmoi source:
  home/.chezmoitemplates/agents-common.md）を編集する。
*/ -}}
## Language

- Commit messages and PR titles/descriptions: Japanese by default.
- Conventional Commit prefix (`feat:`, `fix:`, `chore:` …) は英語のまま、その後の summary を日本語にする。
- 例: `chore(release): release-please のタグから component prefix を外す`
- 既存リポジトリが明確に英語コミットで揃っている場合のみ英語にする。
- 生成物（エラーメッセージ・ログ・README 等）も日本語。明示指示がない限り英語で書かない。

## Security

- クレデンシャルファイルを直接読み出すことは一切禁止。
  対象例: `~/.aws/credentials`, `~/.aws/config`, `~/.ssh/*`, `.env*`, `*.pem`, `*.key`, `id_rsa*`, `gcloud` の credential json, `kubeconfig`, `netrc`, ブラウザの保存パスワード等、秘密情報を含みうるファイル全般。
  - `cat` / `Get-Content` / `Read` ツール / `head` / `tail` / `less` / `grep` 等で中身を表示・抽出しない。
  - 必要な情報は必ず公式 CLI 経由で取得する。例:
    - AWS アカウント ID / ARN → `aws sts get-caller-identity`
    - 利用中プロファイル一覧 → `aws configure list-profiles`
    - 個別プロファイル設定 → `aws configure get <key> --profile <name>`
    - GCP → `gcloud auth list`, `gcloud config list`
  - 例外的に中身参照が必要なときは、必ず事前にユーザーへ目的を説明し明示の許可を得る。

## 作業スタイル

- ALWAYS: 手を動かす前に Git の前提（branch / upstream / last commit / worktree クリーン）を確認する
- ALWAYS: 環境系（dotfiles・シェル・エディタ・**エージェント指示（CLAUDE.md / AGENTS.md 等）**・mise / starship 等）の変更は **chezmoi source（`~/src/dotfiles`）を編集して `chezmoi apply`** で反映する。デプロイ済みの実体（`~/.zshrc` / `~/.claude/CLAUDE.md` 等）を直接編集しない（次の apply で上書きされ source と乖離するため）
- ALWAYS: 同じ手順を 3 回以上繰り返したらスクリプト化 / skill 化を検討。着手前に「自作資産」で重複確認
- ALWAYS: エージェントスキルは出所で管理（①自作=dotfiles の `skills/` / ②コマンド付属=ツール公式コマンド / ③gh skill=信頼 org を pin / ④野良）。**野良(④)は必ず検収フロー**: `gh skill install <repo> <skill> --dir skills-staging/<name>` で隔離 → SKILL.md・scripts・allowed-tools を精査 → OK なら `skills/` に固める。**未検証のまま `~/.claude/skills` 等へ入れない**（詳細は dotfiles README「スキル管理」）
- ALWAYS: 正解が複数ある選択（設計・ネーミング・口調）は一案に確定せず複数案を提示。ユーザーは codex / ChatGPT と併用する
- ALWAYS: **UX / 画面デザインの判断は「簡易 Claude Design」として振る舞う**。文章や ASCII だけで是非を問わず、**実色・実データで描いた自己完結 HTML モック**（外部依存ゼロ・inline CSS・light/dark 併記・比較対象と並置）を作って提示し、ユーザーがブラウザ / サイドパネルで見比べて選べる形にする。複数バリアント + 推奨 1 案を添える。既存実装のデザイントークン（実在する CSS 変数）を使い、参照 UX があれば同サンプルで並べて「違和感なく寄れているか」を判断可能にする。SendUserFile（display: render）か Artifact で届ける。方向確定後に実装へ入る
- ALWAYS: **ローカル環境の保守的なクリーンアップは確認せず自走する**。判断軸は「**reproducible（再生成可能）かつ local-only（repo / リモートに無影響）**」。該当例: lock とズレた stale 依存の prune（`pnpm install` で reconcile）/ 再生成可能な build artifact・生成物の削除 / `.gitignore` 済み派生物の掃除。これらは「やっていいか」を聞かない（聞かれる側が困る）。逆に reproducible でない or リモート影響のある破壊操作だけ確認する。harness の auto 分類器が削除を拒否したら、その旨を伝え permission rule で緩めてもらう
- NEVER: **「カノニカル」を使わない**（ドキュメント・会話・コメント全てで禁止）。代替: 「唯一の真実」「正本」「公式」「基準」など。新規ドキュメントを書く時は禁則語をスキャンしてから提出
- NEVER: コメント/ドキュメントに**中途半端な過去の経緯**を残さない（`旧:` `以前は` `かつて` 等のナレーション）。理由は「**なぜ今こうか**」を現在形で書き、履歴は git に委ねる。例外は**実行可能な条件付き**のときだけ（例: mise pin の「戻す条件＋日付」）。単なる経緯説明は削除する

## 環境（パッケージ / ツール）

- パッケージは pnpm（npm 直は使わない）
- CLI ツール全般は原則 **mise** で導入。`npm i -g` の前に mise を確認
- ツール/skill は使い回せる形で資産化する

### mise

- aqua 系ツールの `mise up` が attestation 検証で落ちたら、まず aqua-registry の自動更新 PR
  (`chore: update <owner>/<repo> X.Y.Z to X.Y.Z+1`) の CI を確認。同じ失敗が出ていれば upstream バグ確定
- 対処は **last-good version への pin が第一選択**。`aqua.github_attestations = false` で全 aqua ツールの検証を切るのは避ける
- pin する時は config.toml に「戻す条件」と日付をコメントで残す
- 切り分けだけなら `MISE_AQUA_GITHUB_ATTESTATIONS=false mise up <tool>` で一発確認（恒久措置にしない）

### サプライチェーンセキュリティ（全言語・全エコシステム共通）

新しい言語/パッケージマネージャを導入したら、**npm を特別扱いせず同じ 3 層 + 地金**を必ず揃える。

- **L1 ブロック（registry proxy）**: 対応エコシステムは **Takumi Guard（GMO Flatt Security, `*.flatt.tech`）** を registry/index に差し替え、既知の悪性を DL 時にブロックする。GA は npm/pnpm・PyPI(pip/uv/poetry)・RubyGems(bundler)・Go modules・Packagist（**crates.io(Rust) は対象外**）。まず匿名(ブロックのみ)で入れ、追跡/感染通知が要れば `tg_anon_` トークンを **chezmoi secret 化**（平文コミット禁止）。private/社内レジストリのある repo は per-project で除外する。
- **L2 cooldown（時間軸）**: 公開直後の悪性版を掴まない。native 対応があれば設定する — pnpm `minimumReleaseAge`（基準 4320=3日 / 自作 package は exclude）、uv `exclude-newer = "7 days"`。native が無い言語(Rust/Ruby 等)は L1/L3 で補う。
- **L3 scanner（既知脆弱性・悪性）**: **`osv-scanner` を全言語共通の必須スキャナ**にする（npm/PyPI/cargo/gem/nuget/go/maven/composer の lockfile を一括）。L1/L2 が薄い言語は per-ecosystem audit を足す（`cargo-audit` / `pip-audit` / `bundler-audit` 等）。secret 漏洩は `gitleaks`。
- **地金（全言語）**: lockfile を必ずコミットして固定 / postinstall・build script は既定で無効、必要分だけ allowlist（pnpm `onlyBuiltDependencies` 等）/ engines・packageManager をピン / **自分が publish する物**は OIDC(Trusted Publishing)・provenance/attestation 必須・2FA は FIDO（踏むだけでなく「踏み台にされて配布元になる」前提で守る）。

**新エコシステム導入チェックリスト**（言語を足したら必ず通す）:
1. Takumi Guard 対応か → 対応なら registry/index を差替（非対応なら L2/L3 を厚く）
2. native cooldown があるか → あれば設定（無ければ理由を一行残す）
3. `osv-scanner` がその lockfile を読めるか → 読めない形式なら per-ecosystem audit を追加
4. lockfile 固定 / build script allowlist / provenance を上記に合わせる
5. mise（ツール）と chezmoi source（各 config）と `supply-chain-audit` に組み込み、全マシンへ配る

## マシン追加時の判断軸（chezmoi / profile）

新マシンは `home/.chezmoitemplates/profile` で 2 つ決める:
- **machine**: hostname のばらつきを正規ラベルに吸収（判定の単一発生源）。
- **weight**（slim/lite/full）: 入れるツール量＝資源と用途。slim=素のシェル / lite=agent core(node/python/claude-code/codex)まで / full=重い・クラウド系も全部。

表示系も machine で出し分ける。代表例:
- **ghostty font-size**: 同じ pt でも見かけは「論理解像度 = パネル解像度 ÷ OS スケーリング」で決まる。高PPIノート(例 Surface 220PPI→150%→論理1280×853)は行数が半減して大きすぎる→小さめ(16pt)、低PPI大画面(例 49"TV ~91PPI→100%→論理3072×1728)は 24pt が適正。詳細は `ghostty/config.tmpl` のコメント。

## 外部 API メモ

### Notion API

Notion API は 2025〜2026 で大きく動いている。**操作する前に必ず最新 API の事情で効率化できないか確認**する。

- ALWAYS: 本文 (page content) を読み書きするときは **Markdown content API** を最優先で検討する (`Notion-Version: 2026-03-11`)
  - `GET /v1/pages/{id}/markdown` → 本文を enhanced markdown 文字列で取得 (paginate 不要)
  - `PATCH /v1/pages/{id}/markdown` body `{ type: "replace_content", replace_content: { new_str: "..." } }` で全置換 (atomic 1 req)
  - append/prepend 系コマンドも揃っている（2026-05-15 リリース）
  - **旧 block API（`GET /blocks/{id}/children` + 個別 DELETE + `PATCH /children`）は使わない**
- ALWAYS: database query は **`POST /v1/data_sources/{ds_id}/query`** を使う (2025-09-03 以降)
  - 旧 `POST /v1/databases/{db_id}/query` は legacy。`Notion-Version` を 2025-09-03+ に上げると 400
  - data_source ID は `GET /v1/databases/{db_id}` の `data_sources[0].id` で resolve
- ALWAYS: bulk page 更新は **`PATCH /v1/pages/bulk`** (2026-02-01、最大 100 page/req) を検討
- Rate limit は ~3 req/sec 公称 / 2 req/sec 体感。**「呼び出し回数 N を 1 にする」変換を最優先**
- 公式 changelog: https://developers.notion.com/page/changelog

## Git

### Rebase

- ALWAYS: rebase ベースは **`origin/<target>`**（ローカル main/master は fetch 忘れで古い）
- ALWAYS: rebase 前に `git fetch origin <target>` を実行
- ALWAYS: `git rebase --onto <base> <upstream> <branch>` で範囲を明示し、無関係コミットを巻き込まない
- conflict が想定より多ければ**まず abort** してベースを再確認する

### ブランチ

- 独立した機能は独立したブランチに切る。意図と違う祖先なら `--onto` で速やかに載せ替え
- 整理は `git sweep`（`git sweep report` → `prune -y`）。`backup/*` は保護対象

### PR / コミットメッセージ

後から見た人が前提知識なしで理解できることを優先する。

- ALWAYS: PR 本文には **Why（なぜ） / 設計判断（なぜこの実装か） / 変更内容（何を加えたか）** の 3 点を簡潔に（節タイトルは日本語で）
- ALWAYS: スタック PR（base が main 以外）のときは冒頭で **base ブランチと依存 PR 番号** を明示
- ALWAYS: コミットメッセージは日本語で「**なぜ**」を必ず 1-2 行入れる
- ALWAYS: 既知の制約・将来改善余地は「既知の制約」セクションに残す
- 過剰装飾は不要。読み手の認知コストを下げる方向で簡潔に。テストプランは bullet で
