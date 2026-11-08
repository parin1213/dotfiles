"""Google Healthの日別歩数。OAuthは開始せず、呼出側から受けた短期トークンだけを使う。"""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from uuid import NAMESPACE_URL, uuid5
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

SCOPE = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly"
BASE = "https://health.googleapis.com/v4/"
FAMILY = "users/me/dataSourceFamilies/all-sources"


class StepsError(Exception):
    """レスポンスやトークンを含めない、呼出側向けのエラー。"""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def request_json(method, url, payload, token):
    if url not in (BASE + "users/me/identity", BASE + "users/me/dataTypes/steps/dataPoints:dailyRollUp"):
        raise StepsError("接続先が許可されていません")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Authorization": "Bearer " + token,
        "Accept": "application/json", "Content-Type": "application/json"})
    # リダイレクトやOSのHTTPプロキシ経由で資格情報を他の接続先へ渡さない。
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise StepsError("API応答が大きすぎます")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise StepsError("API応答の形式が不正です")
            return result
    except HTTPError as error:
        messages = {400: "Google Healthの連携状態または要求内容を確認してください",
                    401: "認証期限切れまたは無効です。自動で再認証しません",
                    403: "権限またはAPIの利用設定を確認してください",
                    429: "APIの回数制限です。時間を置いて再試行してください"}
        raise StepsError(messages.get(error.code, "API呼出しが失敗しました")) from None
    except (URLError, OSError, ValueError):
        raise StepsError("APIへ接続できないか、応答の形式が不正です") from None


def civil(day):
    return {"date": {"year": day.year, "month": day.month, "day": day.day},
            "time": {"hours": 0, "minutes": 0, "seconds": 0, "nanos": 0}}


def parse_day(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise StepsError("対象日はYYYY-MM-DDで指定してください")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise StepsError("対象日が不正です") from None


def matches_civil(value, day):
    if not isinstance(value, dict) or set(value) - {"date", "time"}:
        return False
    clock = value.get("time", {})
    return (value.get("date") == civil(day)["date"] and isinstance(clock, dict)
            and not set(clock) - {"hours", "minutes", "seconds", "nanos"}
            and all(type(v) is int and v == 0 for v in clock.values()))


@dataclass(frozen=True)
class StepsSnapshot:
    date: str
    steps: int | None
    observed_at: str
    account_hash: str
    missing_state: str
    source: str = "google_health"
    source_family: str = FAMILY
    identity_verified: bool = True
    fit_sync_verified: bool = False

    def as_dict(self):
        return asdict(self)


class GoogleSteps:
    def __init__(self, access_token, expected_health_user_id, *, transport=request_json, now=None):
        if not isinstance(access_token, str) or not access_token or any(c.isspace() for c in access_token):
            raise StepsError("短期アクセストークンを呼出側で用意してください")
        if not isinstance(expected_health_user_id, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,63}", expected_health_user_id):
            raise StepsError("本人確認済みのGoogle Health user IDが必要です")
        self._token, self._expected, self._transport = access_token, expected_health_user_id, transport
        self._now = now or (lambda: datetime.now(timezone.utc))

    def fetch_day(self, target):
        day = parse_day(target)
        identity = self._transport("GET", BASE + "users/me/identity", None, self._token)
        if not isinstance(identity, dict) or identity.get("healthUserId") != self._expected:
            raise StepsError("Google Healthのアカウントが本人確認済みIDと一致しません")
        payload = {"range": {"start": civil(day), "end": civil(day + timedelta(days=1))},
                   "windowSizeDays": 1, "pageSize": 1, "dataSourceFamily": FAMILY}
        response = self._transport("POST", BASE + "users/me/dataTypes/steps/dataPoints:dailyRollUp", payload, self._token)
        if not isinstance(response, dict) or response.get("nextPageToken"):
            raise StepsError("API応答が未完了または不正です。値を保存しません")
        points = response.get("rollupDataPoints", [])
        if not isinstance(points, list) or len(points) > 1:
            raise StepsError("日別歩数の応答が1日分ではありません")
        steps, missing = None, "no_window"
        if points:
            point = points[0]
            if (not isinstance(point, dict) or not matches_civil(point.get("civilStartTime"), day)
                    or not matches_civil(point.get("civilEndTime"), day + timedelta(days=1))):
                raise StepsError("対象日と異なる期間です。値を保存しません")
            if "steps" not in point:
                missing = "steps_omitted"
            else:
                value = point["steps"]
                if not isinstance(value, dict) or not isinstance(value.get("countSum"), str) or not re.fullmatch(r"0|[1-9][0-9]{0,6}", value["countSum"]):
                    raise StepsError("歩数の形式が不正です")
                steps = int(value["countSum"])
                if steps > 200000:
                    raise StepsError("歩数が確認範囲を超えています")
                missing = "present"
        observed = self._now()
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise StepsError("取得日時にタイムゾーンが必要です")
        account_hash = hashlib.sha256(self._expected.encode()).hexdigest()
        return StepsSnapshot(str(day), steps, observed.astimezone(timezone.utc).isoformat(timespec="seconds"), account_hash, missing)


def save_snapshot(store, snapshot):
    """検証済みの1日分だけを新規ノートにする。APIの生応答・トークンは保存しない。"""
    if not isinstance(snapshot, StepsSnapshot):
        raise StepsError("検証済みの歩数スナップショットが必要です")
    parse_day(snapshot.date)
    try:
        observed = datetime.fromisoformat(snapshot.observed_at)
        if observed.utcoffset() is None:
            raise ValueError()
    except (TypeError, ValueError):
        raise StepsError("取得日時にタイムゾーンが必要です") from None
    if (snapshot.source != "google_health" or snapshot.source_family != FAMILY
            or snapshot.identity_verified is not True or snapshot.fit_sync_verified is not False
            or not re.fullmatch(r"[a-f0-9]{64}", snapshot.account_hash)
            or snapshot.missing_state not in {"present", "steps_omitted", "no_window"}
            or (snapshot.steps is None) != (snapshot.missing_state != "present")
            or (snapshot.steps is not None and (type(snapshot.steps) is not int or not 0 <= snapshot.steps <= 200000))):
        raise StepsError("歩数スナップショットの形式が不正です")
    provenance = {"data_source_family": FAMILY, "account_hash": snapshot.account_hash,
                  "window_date": snapshot.date, "identity_verified": True,
                  "fit_sync_verified": False, "missing_state": snapshot.missing_state}
    content = {"source": "google_health", "date": snapshot.date, "steps": snapshot.steps, **provenance}
    snapshot_key = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    identifier = str(uuid5(NAMESPACE_URL, "lacia-health:" + snapshot_key + snapshot.observed_at))
    record = {"id": identifier, "kind": "steps", "occurred_at": snapshot.observed_at,
              "value": snapshot.steps,
              "text": f"Google Healthの日別歩数。対象日: {snapshot.date}。取得元がGoogle Fitかは未確認。未記録は0に置換しない。"}
    with store.lock, store.exclude_sync():
        previous = []
        for path in store.record_paths(f"{snapshot.date}_健康記録_*_*.md"):
            if path.is_symlink() or path.stat().st_size > 256 * 1024:
                continue
            try:
                header = dict(line.split(": ", 1) for line in path.read_text(encoding="utf-8").split("\n---\n", 1)[0][4:].splitlines())
                if (header.get("source") != "google_health"
                        or json.loads(header["account_hash"]) != snapshot.account_hash
                        or json.loads(header["window_date"]) != snapshot.date):
                    continue
                stamp = datetime.fromisoformat(header["occurred_at"])
                if stamp.utcoffset() is None:
                    continue
                old_value = json.loads(header["value"])
                same = ((old_value is None if snapshot.steps is None else type(old_value) is int and old_value == snapshot.steps)
                        and json.loads(header["missing_state"]) == snapshot.missing_state
                        and json.loads(header["data_source_family"]) == FAMILY
                        and json.loads(header["identity_verified"]) is True
                        and json.loads(header["fit_sync_verified"]) is False)
                previous.append((stamp, path, same))
            except (ValueError, KeyError, TypeError, OSError, UnicodeError):
                continue
        if previous:
            latest_time = max(item[0] for item in previous)
            latest = [item for item in previous if item[0] == latest_time]
            if len(latest) == 1 and latest[0][2] and latest_time <= observed:
                return {"path": latest[0][1].relative_to(store.root).as_posix(), "source": "google_health", "unchanged": True,
                        "fit_sync_verified": False, "sync": "同じ値の既存ノートを確認。Git同期は未確認"}
        result = store._save(record, record_day=snapshot.date, provenance=provenance)
    return {**result, "source": "google_health", "fit_sync_verified": False,
            "sync": "Vault内保存のみ確認。Git同期は未確認"}


def sync_day(client, store, day):
    """承認後に呼ぶ1回分の読取りと保存。認証・定期実行・Git操作は行わない。"""
    return save_snapshot(store, client.fetch_day(day))
