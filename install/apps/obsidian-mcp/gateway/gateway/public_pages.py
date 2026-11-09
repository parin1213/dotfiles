"""健康連携の説明だけを公開する固定HTTPルート。"""
from starlette.responses import HTMLResponse

HEADERS = {
    "Content-Security-Policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "public, max-age=300",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def page(title, body):
    return ("<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title}</title></head><body><main><h1>{title}</h1>{body}</main></body></html>")


HOME = page("Lacia 健康記録", """
<p>歩数と睡眠をObsidianにまとめ、生活習慣を振り返るための個人用ツールです。利用者本人が管理し、一般向けの利用登録は受け付けていません。</p>
<h2>できること</h2>
<p>本人が許可した範囲でGoogle Healthから歩数と実睡眠時間、睡眠の開始・終了時刻を読み取ります。Googleの健康記録への書き込みは行いません。</p>
<p>記録は本人が管理するRaspberry Pi上のObsidian Vaultに保存し、ダッシュボードと本人が接続したMCP対応アシスタントから参照できます。欠測は0歩・0時間と区別します。</p>
<p>この公開ページに健康記録や認証情報は表示しません。計測・同期の状況により記録が遅れたり取得できない場合があります。医療機器ではなく、診断や治療の判断には使用できません。</p>
<p><a href='/lacia-health/privacy'>プライバシーポリシー</a></p>
""")

PRIVACY = page("Lacia 健康記録 プライバシーポリシー", """
<p>最終更新：2026年11月9日</p>
<h2>対象</h2>
<p>利用者本人が管理する個人用ツール「Lacia 健康記録」に適用します。</p>
<h2>取得する情報と目的</h2>
<p>本人の許可に基づきGoogle Healthから歩数を取得し、睡眠の読み取りも許可された場合は実睡眠時間、開始・終了時刻、セッション識別情報を取得します。本人確認のためのアカウント識別情報、取得日・取得元・同期結果、継続接続用のOAuth資格情報も扱います。</p>
<p>本人の記録、集計、グラフ表示、接続したアシスタントによる振り返りと同期状態の確認に利用します。Googleの健康記録への書き込み、広告配信、データ販売、信用判断、保険・雇用の評価には利用しません。</p>
<p>Google Health APIから受け取った情報は、Limited Use要件を含む<a href="https://developers.google.com/health/policies/health-api-developer-user-data-policy">Google Health API Developer and User Data Policy</a>に従って取り扱います。</p><h2>保存と保護</h2>
<p>健康記録は本人が管理するRaspberry Pi上のObsidian VaultへMarkdownで保存します。Googleの継続接続用資格情報は健康記録と分離し、Pi上に暗号化保存します。資格情報を公開ページや公開ソースコード、健康記録へ掲載しません。</p>
<p>健康記録自体は閲覧可能なファイルです。本人の設定した端末間同期やバックアップの対象になる場合があり、保存先のアクセス権管理が必要です。</p>
<h2>外部サービス</h2>
<p>Googleとは認証と許可されたデータ取得に必要な通信を行います。本人が接続したMCP対応アシスタントが記録を取得すると、要求された情報がそのサービスへ送信されます。ChatGPTから利用する場合はOpenAIのサービスへ送信され、そのサービスの規約・プライバシーポリシー・本人の設定も適用されます。</p>
<p>Vaultの同期やバックアップを設定した場合はその保存先にも記録が保存されることがあります。一般公開用の説明ページに健康記録や認証情報を送信・掲載しません。</p>
<h2>保存期間と削除</h2>
<p>振り返りのため記録を保持し、一律の自動削除期限は設けていません。不要な記録はVaultから削除できます。Git履歴、同期端末、バックアップには削除前の記録が残る場合があり、それぞれ別の削除作業が必要です。</p>
<h2>接続の停止</h2>
<p>本人はGoogleアカウントの接続管理画面で許可を取り消せます。同期サービスの停止とPiに保存された資格情報の削除でも継続取得を停止できます。許可の取り消しだけでは取得済みの記録は自動削除されません。認証期限やAPI変更等で取得できなくなる場合があります。</p>
<h2>公開ページ</h2>
<p>健康情報の入力フォーム、広告、独自のアクセス解析スクリプトは設置しません。ページ配信を行うサービスが通信に伴うIPアドレス等を処理する場合があります。</p>
<h2>変更と管理</h2>
<p>取り扱いを変更する場合はこのページを更新します。新たなGoogle権限が必要な場合は別途本人の同意を求めます。利用者本人が管理する個人用ツールです。</p>
<p><a href='/lacia-health/'>Lacia 健康記録の説明へ</a></p>
""")


def register_public_pages(gateway):
    # 固定文書のみ。ファイル配信・Vault参照・認証設定変更は行わない。
    for path, document in (("/lacia-health/", HOME), ("/lacia-health/privacy", PRIVACY)):
        async def serve(request, body=document):
            return HTMLResponse(body, headers=HEADERS)
        gateway.custom_route(path, methods=["GET", "HEAD"], include_in_schema=False)(serve)
