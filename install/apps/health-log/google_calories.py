"""総消費カロリーの読取り。基礎代謝を含むGoogle推定値を取得する。"""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo
from google_steps import BASE, NoRedirect, StepsError, GoogleSteps, parse_day, civil, matches_civil

ENDPOINT = BASE + "users/me/dataTypes/total-calories/dataPoints:dailyRollUp"
FAMILY = "users/me/dataSourceFamilies/google-wearables"
MISSING = {"present", "calories_omitted", "no_window"}


def request_calories_json(method, url, payload, token):
    if not ((method == "GET" and url == BASE + "users/me/identity" and payload is None)
            or (method == "POST" and url == ENDPOINT)):
        raise StepsError("総消費APIの接続先が許可されていません")
    raw = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=raw, method=method, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise StepsError("総消費API応答が大きすぎます")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise StepsError("総消費API応答の形式が不正です")
            return result
    except (HTTPError, URLError, OSError, ValueError):
        raise StepsError("総消費APIを読み取れません。権限・同期状態を確認してください") from None


@dataclass(frozen=True)
class CaloriesSnapshot:
    date: str
    kcal: float | None
    observed_at: str
    account_hash: str
    missing_state: str
    time_zone: str
    day_elapsed: bool
    source: str = "google_health"
    source_family: str = FAMILY
    identity_verified: bool = True
    fit_sync_verified: bool = False


class GoogleCalories(GoogleSteps):
    def __init__(self, token, expected, *, transport=request_calories_json, now=None):
        super().__init__(token, expected, transport=transport, now=now)

    def fetch_day(self, target, zone_name):
        if zone_name != "Asia/Tokyo":
            raise StepsError("総消費の日付判定は日本時間に限定します")
        day, zone = parse_day(target), ZoneInfo(zone_name)
        observed = self._now()
        if observed.utcoffset() is None or day > observed.astimezone(zone).date():
            raise StepsError("総消費の対象日または取得日時が不正です")
        identity = self._transport("GET", BASE + "users/me/identity", None, self._token)
        if not isinstance(identity, dict) or identity.get("healthUserId") != self._expected:
            raise StepsError("Google Healthの本人IDが一致しません")
        payload = {"range": {"start": civil(day), "end": civil(day + timedelta(days=1))},
                   "windowSizeDays": 1, "pageSize": 1, "dataSourceFamily": FAMILY}
        response = self._transport("POST", ENDPOINT, payload, self._token)
        if not isinstance(response, dict) or response.get("nextPageToken"):
            raise StepsError("総消費のAPI応答が未完了です")
        points = response.get("rollupDataPoints", [])
        if not isinstance(points, list) or len(points) > 1:
            raise StepsError("総消費のAPI応答が1日分ではありません")
        kcal, missing = None, "no_window"
        if points:
            point = points[0]
            if (not isinstance(point, dict) or not matches_civil(point.get("civilStartTime"), day)
                    or not matches_civil(point.get("civilEndTime"), day + timedelta(days=1))):
                raise StepsError("総消費の期間が対象日と一致しません")
            energy = point.get("totalCalories")
            if energy is None:
                missing = "calories_omitted"
            elif not isinstance(energy, dict) or "kcalSum" not in energy:
                missing = "calories_omitted"
            else:
                kcal = energy["kcalSum"]
                if type(kcal) not in (int, float) or not math.isfinite(kcal) or not 0 <= kcal <= 20000:
                    raise StepsError("総消費の数値が不正です")
                missing = "present"
        return CaloriesSnapshot(str(day), kcal, observed.astimezone(timezone.utc).isoformat(timespec="seconds"),
            hashlib.sha256(self._expected.encode()).hexdigest(), missing, zone_name,
            day < observed.astimezone(zone).date())


def validate_snapshot(snapshot):
    if not isinstance(snapshot, CaloriesSnapshot):
        raise StepsError("検証済みの総消費が必要です")
    day = parse_day(snapshot.date)
    observed = datetime.fromisoformat(snapshot.observed_at)
    if (observed.utcoffset() is None or snapshot.source != "google_health" or snapshot.source_family != FAMILY
            or snapshot.identity_verified is not True or snapshot.fit_sync_verified is not False
            or not re.fullmatch(r"[a-f0-9]{64}", snapshot.account_hash)
            or snapshot.missing_state not in MISSING
            or (snapshot.kcal is None) != (snapshot.missing_state != "present")
            or (snapshot.kcal is not None and (type(snapshot.kcal) not in (int, float)
                or not math.isfinite(snapshot.kcal) or not 0 <= snapshot.kcal <= 20000))
            or snapshot.time_zone != "Asia/Tokyo" or type(snapshot.day_elapsed) is not bool
            or snapshot.day_elapsed != (day < observed.astimezone(ZoneInfo(snapshot.time_zone)).date())
            or day > observed.astimezone(ZoneInfo(snapshot.time_zone)).date()):
        raise StepsError("総消費の記録形式が不正です")


def save_snapshot(store, snapshot):
    validate_snapshot(snapshot)
    provenance = {"data_source_family": FAMILY, "account_hash": snapshot.account_hash,
        "window_date": snapshot.date, "identity_verified": True, "fit_sync_verified": False,
        "missing_state": snapshot.missing_state, "time_zone": snapshot.time_zone, "day_elapsed": snapshot.day_elapsed}
    content = {"source": "google_health", "value": snapshot.kcal, **provenance}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    record = {"id": str(uuid5(NAMESPACE_URL, "lacia-calories:" + digest + snapshot.observed_at)),
        "kind": "total_calories", "occurred_at": snapshot.observed_at, "value": snapshot.kcal,
        "text": "Google/Fitbitウェアラブル由来の総消費推定。基礎代謝を含むため歩数・基礎代謝を再加算しない。"
                "日付はGoogleのローカル日集計。終了日でも装着・同期の完全性は未確認。"}
    with store.lock, store.exclude_sync():
        previous = []
        for path in store.record_paths(f"{snapshot.date}_健康記録_*_*.md"):
            if path.is_symlink() or path.stat().st_size > 256 * 1024:
                continue
            try:
                fields = dict(line.split(": ", 1) for line in path.read_text(encoding="utf-8").split("\n---\n", 1)[0][4:].splitlines())
                if fields.get("kind") != "total_calories" or fields.get("source") != "google_health":
                    continue
                stamp = datetime.fromisoformat(fields["occurred_at"])
                if stamp.utcoffset() is None:
                    continue
                old = {"source": fields["source"], "value": json.loads(fields["value"]),
                       **{key: json.loads(fields[key]) for key in provenance}}
                previous.append((stamp, path, old == content))
            except (ValueError, KeyError, TypeError, OSError, UnicodeError):
                continue
        if previous:
            latest = max(item[0] for item in previous)
            matches = [item for item in previous if item[0] == latest]
            if len(matches) == 1 and matches[0][2] and latest <= datetime.fromisoformat(snapshot.observed_at):
                return {"path": matches[0][1].relative_to(store.root).as_posix(), "unchanged": True}
        return store._save(record, record_day=snapshot.date, provenance=provenance)
