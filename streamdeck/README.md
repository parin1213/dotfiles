# Stream Deck Neo

Stream Deck Neo のプロファイルとキー画像を生成する。Stream Deck はファイルを取り込んで使う方式なので、chezmoi では配置しない。
`gen-profiles.mjs` は実行したマシンの OS 用のプロファイルを作る。Windows と Mac でキーの配置は同じで、置くアプリと起動の仕方だけが違う。

## 構成

| ファイル | 役割 |
|---|---|
| `make-icons.ps1` | キー画像（144×144 PNG）を `icons/` に作る。Windows のフォントを使うので Windows で実行する |
| `icons/` | 生成済みのキー画像。Mac でも使えるようにコミットしている。ゲーム（原神 / 崩壊：スターレイル）とアプリを開くキー（Obsidian、YouTube Music、Codex アプリ、Windows Terminal、VS Code、Claude Code、Codex CLI、GitHub）は各社のロゴなので含めず、`make-icons.ps1` が手元のアプリ（exe・ストアアプリのパッケージ・Claude Code と Codex は VS Code 拡張の画像）や公式サイトから作る |
| `register-game-tasks.ps1` | 原神 / 崩壊：スターレイルを「最上位の特権で実行」するタスクとして登録する。ゲームのキーはこのタスクを起動するので、UAC を出さずに立ち上がる。管理者として 1 回実行する |
| `start-agent.ps1` | Claude Code / Codex のキーから呼ぶ（`-Kind claude` / `-Kind codex`）。ターミナルが前面なら herdr で見ているペイン（何かが動いていれば同じ Space の新しいタブ）で、そうでなければホームに新しい Space を作って起動する |
| `focus-app.ps1` | アプリが起動していればそのウィンドウを前面に出し、無ければ起動する。ターミナルのキーから呼ぶ |
| `switch-input.ps1` | モニターの入力を DDC/CI で切り替える。PC⇄Mac キーが `-Model U2725QE -Source 0x19`（Dell を TB4 = Mac に）で呼ぶ。`-List` で DDC に応答するモニターの model を出す |
| `make-icons-mac.sh` | Mac のプロファイルで使うアプリのキー画像を作る。Slack・ChatGPT・Ghostty・VS Code・Google ドライブは .app のアイコンから、カレンダーと Notion は公式サイトから。Slack は未読数のバッジを重ねた絵（`icons/badges/`）も作る。Claude Code・Codex CLI・GitHub・YouTube Music・Obsidian は Windows で作ったものを local-pc から持ってくる |
| `start-agent.sh` | Mac の Claude Code / Codex キーから呼ぶ（引数 `claude` / `codex`）。`start-agent.ps1` と同じ動きで、ターミナルは Ghostty |
| `switch-input.sh` | Mac の PC⇄Mac キーから呼ぶ。m1ddc で Dell を DP（PC、15）に切り替える |
| `plugin/` | 自作プラグイン（`io.github.parin1213.desk`）。Infobar の使用率と時計（承認待ちの Space があればその表示）、herdr の Space キー、Claude 5h / 7d、経過時間、PC⇄Mac、アプリキー（Mac は Dock のバッジで Slack などの未読数を右上に出す）、コマンド実行キー（Mac の標準の「開く」は引数付きのコマンドを走らせられないため）。Space キーは置いた列で 1〜4 番目の Space を出し、押すとその Space に移ってターミナルを前に出す |
| `gen-profiles.mjs` | YouTube Music はブラウザでインストールしたアプリ（PWA）があればそれを、無ければサイトを開くキーにする。プロファイル「通常」（普段使い / AI / 会議中）と「エンジニアリング（ターミナル）」「エンジニアリング（VS Code）」（中身は同じリンクと AI の 2 ページで、ターミナル用は AI が先。Stream Deck はプロファイル 1 つにアプリ 1 つしか紐付けられないため 2 つ作る）を `out/*.streamDeckProfile` に作る |

公式プラグインが要るキー（Codex 送信）は空けてある。

Space キーに出る話題は `~/.local/bin/herdr-topic.mjs`（Claude Code の Stop hook）が会話から Haiku で作り直したもの。

## Mac のキー配置

Mac は仕事で使うので、普段使いのページには使っている時間の長いアプリを置く。ゲームは置かない。

| ページ | 上段 | 下段 |
|---|---|---|
| 普段使い | Slack（未読数）・Google カレンダー・Notion・Google ドライブ | 再生/停止・YouTube Music・PC に切替・ロック |
| AI | herdr Space 1〜4 | Claude 5h・Claude 7d・（Codex 送信の空き）・ChatGPT |
| 会議中 | マイク・カメラ・挙手・字幕 | チャット・参加者・会議メモ（Notion）・経過時間 |
| エンジニアリングのリンク | Ghostty・VS Code・Claude Code・Codex | GitHub PR・範囲スクショ・Meet ミュート・Meet カメラ |

ホットキーは Command を使う（Meet のマイクは ⌘D、ロックは ⌃⌘Q、範囲スクショは ⇧⌘4）。

## 更新の手順

Mac では 1 の代わりに次を行う（Stream Deck と m1ddc は Brewfile で入る）。

- `bash make-icons-mac.sh`
- `plugin/` で `pnpm install; pnpm build; pnpm run link`
- Stream Deck にアクセシビリティの許可を出す（ホットキーのキーに要る）

1. 新しいマシンでは最初に次の 2 つを行う。アイコンを変えたときは `pwsh -File make-icons.ps1`
   - `Start-Process pwsh -Verb RunAs -ArgumentList '-File', 'register-game-tasks.ps1'`
   - `plugin/` で `pnpm install; pnpm build; pnpm run link`（Stream Deck が再起動する）。プラグインを直したら `pnpm build; pnpm run restart`
2. `node gen-profiles.mjs`
3. Stream Deck アプリで、取り込み済みの同名プロファイルを削除する（取り込みは上書きではなく追加になる）
4. `out/*.streamDeckProfile` をダブルクリックして取り込む
5. アプリの紐付けはプロファイルに入っているので、取り込めば終わり
