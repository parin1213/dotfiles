# Stream Deck Neo

Stream Deck Neo のプロファイルとキー画像を生成する。Stream Deck はファイルを取り込んで使う方式なので、chezmoi では配置しない。

## 構成

| ファイル | 役割 |
|---|---|
| `make-icons.ps1` | キー画像（144×144 PNG）を `icons/` に作る。Windows のフォントを使うので Windows で実行する |
| `icons/` | 生成済みのキー画像。Mac でも使えるようにコミットしている。ゲーム（原神 / 崩壊：スターレイル）とアプリを開くキー（Obsidian、YouTube Music、Codex アプリ、Windows Terminal、VS Code、Claude Code、Codex CLI、GitHub）は各社のロゴなので含めず、`make-icons.ps1` が手元のアプリ（exe・ストアアプリのパッケージ・Claude Code と Codex は VS Code 拡張の画像）や公式サイトから作る |
| `register-game-tasks.ps1` | 原神 / 崩壊：スターレイルを「最上位の特権で実行」するタスクとして登録する。ゲームのキーはこのタスクを起動するので、UAC を出さずに立ち上がる。管理者として 1 回実行する |
| `start-agent.ps1` | Claude Code / Codex のキーから呼ぶ（`-Kind claude` / `-Kind codex`）。ターミナルが前面なら herdr で見ているペイン（何かが動いていれば同じ Space の新しいタブ）で、そうでなければホームに新しい Space を作って起動する |
| `focus-app.ps1` | アプリが起動していればそのウィンドウを前面に出し、無ければ起動する。ターミナルのキーから呼ぶ |
| `switch-input.ps1` | モニターの入力を DDC/CI で切り替える。PC⇄Mac キーが `-Model U2725QE -Source 0x19`（Dell を TB4 = Mac に）で呼ぶ。`-List` で DDC に応答するモニターの model を出す |
| `plugin/` | 自作プラグイン（`io.github.parin1213.desk`）。Infobar の使用率と時計（承認待ちの Space があればその表示）、herdr の Space キー、Claude 5h / 7d、経過時間、PC⇄Mac。Space キーは置いた列で 1〜4 番目の Space を出し、押すとその Space に移ってターミナルを前に出す |
| `gen-profiles.mjs` | YouTube Music はブラウザでインストールしたアプリ（PWA）があればそれを、無ければサイトを開くキーにする。プロファイル「通常」（普段使い / AI / 会議中）と「エンジニアリング」（2 ページ目は通常と同じ AI ページ）を `out/*.streamDeckProfile` に作る |

公式プラグインが要るキー（Codex 送信）は空けてある。

Space キーに出る話題は `~/.local/bin/herdr-topic.mjs`（Claude Code の Stop hook）が会話から Haiku で作り直したもの。

## 更新の手順

1. 新しいマシンでは最初に次の 2 つを行う。アイコンを変えたときは `pwsh -File make-icons.ps1`
   - `Start-Process pwsh -Verb RunAs -ArgumentList '-File', 'register-game-tasks.ps1'`
   - `plugin/` で `pnpm install; pnpm build; pnpm run link`（Stream Deck が再起動する）。プラグインを直したら `pnpm build; pnpm run restart`
2. `node gen-profiles.mjs`
3. Stream Deck アプリで、取り込み済みの同名プロファイルを削除する（取り込みは上書きではなく追加になる）
4. `out/*.streamDeckProfile` をダブルクリックして取り込む
5. 「エンジニアリング」をターミナル / VS Code に紐付ける（プロファイル設定の「アプリケーション」）。取り込み直すと消えるので最後に行う
