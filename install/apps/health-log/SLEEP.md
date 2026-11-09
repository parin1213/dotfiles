# 睡眠の読取り

Pixel WatchなどからGoogle Healthに同期された睡眠を、起床日のタイムゾーンで集計する。Googleへの書込みはしない。

- 実睡眠はAPIの `summary.minutesAsleep` を採用し、ベッドにいた時間を睡眠と見なさない。
- 同一セッションIDは重複加算しない。昼寝は別セッションで保持する。
- 記録なし、時間未提供、セッション重複は欠測として扱い、0時間にしない。
- 機械記録は既存の `Attachments/health/records` に置き、日別の最新観測だけをMCP・健康ダッシュボードに表示する。
- 睡眠が失敗しても歩数の保存結果は残し、MCPの状態は歩数と睡眠を分ける。

## 有効化

コード配置だけでは睡眠を読み取らない。承認済み資格情報に睡眠の読取権限がある場合だけ同期する。歩数のみの既存資格情報でも歩数同期は続く。

睡眠読取りの追加とPiへの資格情報の暗号化保存は、本人による操作時の承認が必要。Google CloudのOAuth公開ステータスが「In Production」であることを確認した後、承認済みの場合だけ `google_enroll.py --connect --include-sleep --production --client-config <本人指定ファイル>` を使い、本人のFirefoxで新しく同意する。秘密値を表示したりGitへ入れたりしない。

`--production` はGoogle側の公開状態を変更しない。新しい同意の応答に `refresh_token_expires_in` があれば、その期限を保存する。指定がなければ固定期限を設けないが、取消し・長期未使用などで失効するため、永久に使えることは保証しない。アクセストークンの `expires_in` と混同しない。

`--production` を付けない場合はテスト中として最大7日の期限を守る。既存資格情報も保存済みの期限を維持し、公開状態を変えただけでは期限を延ばさない。更新応答で早い期限が示された場合は暗号化保存してからデータを取得する。

権限の部分同意では保存済み資格情報を置き換えず、一括失効による歩数停止も避ける。受渡し失敗時は保存とGoogle側の許可状態を確認する。再取得は本人同意後に行う。

## 検証

`python -B -m unittest discover -s install/apps/health-log -p 'test_*.py'`

MCPのstdio/HTTPは `install/apps/obsidian-mcp/verify_health.py`。すべて合成データと一時Vaultを使う。Linuxの所有権テストはLinuxファイルシステム上で行う。Web画面の既存テストには同フォルダのUI資産も必要。

実データ・実アカウントの権限追加・Pi稼働は、合成テストの成功とは別に検証する。

資料: https://developers.google.com/health/data-types/sleep
API: https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list
権限: https://developers.google.com/health/scopes
認証期限: https://developers.google.com/health/setup#token-behavior-during-testing
トークン応答: https://developers.google.com/identity/protocols/oauth2/web-server#exchange-authorization-code
