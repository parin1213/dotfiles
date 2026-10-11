# Stream Deck Neo

Stream Deck Neo のプロファイルとキー画像を生成する。Stream Deck はファイルを取り込んで使う方式なので、chezmoi では配置しない。

## 構成

| ファイル | 役割 |
|---|---|
| `make-icons.ps1` | キー画像（144×144 PNG）を `icons/` に作る。Windows のフォントを使うので Windows で実行する |
| `icons/` | 生成済みのキー画像。Mac でも使えるようにコミットしている。ゲーム（原神 / 崩壊：スターレイル）とアプリ（Obsidian / YouTube Music）は各社のロゴ・画像なので含めず、`make-icons.ps1` が手元のアプリや公式サイトから作る |
| `gen-profiles.mjs` | プロファイル「通常」（普段使い / AI / 会議中）と「エンジニアリング」を `out/*.streamDeckProfile` に作る |

自作プラグインや公式プラグインが要るキー（PC⇄Mac、Space、使用率、経過時間、Codex 送信）は空けてある。

## 更新の手順

1. アイコンを変えたときは `pwsh -File make-icons.ps1`
2. `node gen-profiles.mjs`
3. Stream Deck アプリで、取り込み済みの同名プロファイルを削除する（取り込みは上書きではなく追加になる）
4. `out/*.streamDeckProfile` をダブルクリックして取り込む
5. 「エンジニアリング」をターミナル / VS Code に紐付ける（プロファイル設定の「アプリケーション」）。取り込み直すと消えるので最後に行う
