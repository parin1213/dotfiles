# 総消費カロリーの同期

Google Healthの `total-calories` 日別集計を既存の活動・フィットネス読取り権限で取得します。OAuth権限・認証方式は変更しません。本人ID照合後にGoogle/Fitbitウェアラブル由来の値だけを要求します。特定のPixel Watchとの画面照合は別の確認です。

- 単位はkcal。基礎代謝を含む推定値であり、歩数・運動・基礎代謝を追加しません。
- 今日・昨日を既存タイマーで再取得します。欠測はnullで、明示された0と区別します。同じ日の観測は加算せず、同値の再取得ではファイルを増やしません。
- 日付はGoogle APIのcivil timeです。APIにタイムゾーンを指定する項目はありません。本人が日本滞在中である前提で日付経過をAsia/Tokyoで判定します。海外移動時は日付対応を再確認する必要があります。
- `day_elapsed` は日付が過ぎたことだけを示します。装着時間、Googleへの同期、終日データの完全性を保証しません。当日は途中経過と表示し、食事との差を算出しません。
- 食事ログは報告された分の推定を含みます。「記録分との差」は摂取記録から総消費推定を引いた算術差で、実際の赤字・脂肪減少を保証しません。未記録食事を0にしません。
- 総消費の取得に失敗しても、成功した歩数・睡眠は保持します。認証を自動で追加・変更せず、失敗状態を記録します。
- 健康値は既存の本人用非公開VaultとそのGit同期だけに保存します。コードリポジトリへ実健康値・資格情報を入れません。

検証: `python3 -m unittest test_google_calories test_dashboard test_google_sync test_google_sleep test_google_steps test_sync_state_sleep`。
MCPの `health_day` は `latest_observations.total_calories` に最新観測を返し、`health_status` はカロリー同期の成否を返します。

公式仕様: https://developers.google.com/health/data-types/calories
