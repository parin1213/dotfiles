# Stream Deck Neo

Stream Deck Neo のプロファイルとキー画像を生成する。Stream Deck はファイルを取り込んで使う方式なので、chezmoi では配置しない。

## 構成

| ファイル | 役割 |
|---|---|
| `make-icons.ps1` | キー画像（144×144 PNG）を `icons/` に作る。Windows のフォントを使うので Windows で実行する |
| `icons/` | 生成済みのキー画像。Mac でも使えるようにコミットしている。ゲーム（原神 / 崩壊：スターレイル）とアプリを開くキー（Obsidian、YouTube Music、Codex、Windows Terminal、VS Code、Claude Code、GitHub）は各社のロゴなので含めず、`make-icons.ps1` が手元のアプリ（exe・ストアアプリのパッケージ・Claude Code は VS Code 拡張のマスコット）や公式サイトから作る |
| `register-game-tasks.ps1` | 原神 / 崩壊：スターレイルを「最上位の特権で実行」するタスクとして登録する。ゲームのキーはこのタスクを起動するので、UAC を出さずに立ち上がる。管理者として 1 回実行する |
| `start-claude.ps1` | Claude Code のキーから呼ぶ。ターミナルが前面なら herdr で見ているペイン（エージェント稼働中なら同じ Space の新しいタブ）で、そうでなければホームに新しい Space を作って Claude Code を起動する |
| `focus-app.ps1` | アプリが起動していればそのウィンドウを前面に出し、無ければ起動する。ターミナルのキーから呼ぶ |
| `gen-profiles.mjs` | YouTube Music はブラウザでインストールしたアプリ（PWA）があればそれを、無ければサイトを開くキーにする。プロファイル「通常」（普段使い / AI / 会議中）と「エンジニアリング」を `out/*.streamDeckProfile` に作る |

自作プラグインや公式プラグインが要るキー（PC⇄Mac、Space、使用率、経過時間、Codex 送信）は空けてある。

## 更新の手順

1. 新しいマシンでは最初に `Start-Process pwsh -Verb RunAs -ArgumentList '-File', 'register-game-tasks.ps1'`。アイコンを変えたときは `pwsh -File make-icons.ps1`
2. `node gen-profiles.mjs`
3. Stream Deck アプリで、取り込み済みの同名プロファイルを削除する（取り込みは上書きではなく追加になる）
4. `out/*.streamDeckProfile` をダブルクリックして取り込む
5. 「エンジニアリング」をターミナル / VS Code に紐付ける（プロファイル設定の「アプリケーション」）。取り込み直すと消えるので最後に行う
