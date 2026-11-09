"""睡眠の読取りと保存。認証を開始せず、承認済みの呼出側からだけ使用する。"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from google_steps import BASE, NoRedirect, StepsError, GoogleSteps, parse_day

from health_scopes import SLEEP_SCOPE
ENDPOINT = BASE + "users/me/dataTypes/sleep/dataPoints"
MISSING = {"present", "no_sessions", "summary_missing", "overlapping_sessions"}


class SleepError(StepsError):
    pass


def request_sleep_json(method, url, payload, token):
    parsed = urlsplit(url)
    base = url.split("?", 1)[0]
    query = parse_qs(parsed.query)
    if (method != "GET" or payload is not None or parsed.fragment
            or base not in {BASE + "users/me/identity", ENDPOINT}
            or (base.endswith("identity") and parsed.query)
            or set(query) - {"filter", "pageSize", "pageToken"}
            or any(len(v) != 1 for v in query.values())):
        raise SleepError("睡眠APIの接続先が許可されていません")
    request = Request(url, method="GET", headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise SleepError("睡眠API応答が大きすぎます")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise SleepError("睡眠API応答の形式が不正です")
            return value
    except (HTTPError, URLError, OSError, ValueError):
        raise SleepError("睡眠APIを読み取れません。権限・同期状態を確認してください") from None


def stamp(value):
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ValueError()
        return result
    except (TypeError, ValueError):
        raise SleepError("睡眠の日時にはタイムゾーンが必要です") from None


def session(point, day, zone):
    try:
        name, sleep = point["name"], point["sleep"]
        if not isinstance(name, str) or not re.fullmatch(r"users/[A-Za-z0-9-]+/dataTypes/sleep/dataPoints/[A-Za-z0-9_-]+", name):
            raise ValueError()
        start, end = stamp(sleep["interval"]["startTime"]), stamp(sleep["interval"]["endTime"])
        if not timedelta(0) < end - start <= timedelta(days=2) or end.astimezone(zone).date() != day:
            raise ValueError()
        minutes = sleep.get("summary", {}).get("minutesAsleep")
        if minutes is not None:
            if isinstance(minutes, bool) or not re.fullmatch(r"[0-9]+", str(minutes)):
                raise ValueError()
            minutes = int(minutes)
            if not 0 <= minutes <= (end - start).total_seconds() / 60 + 1:
                raise ValueError()
        return {"id": name, "start": start.isoformat(), "end": end.isoformat(), "minutes_asleep": minutes}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise SleepError("睡眠セッションの形式や対象日が不正です") from None


def summarize(sessions):
    if not sessions:
        return None, "no_sessions"
    ordered = sorted(sessions, key=lambda s: stamp(s["start"]))
    if any(stamp(a["end"]) > stamp(b["start"]) for a, b in zip(ordered, ordered[1:])):
        return None, "overlapping_sessions"
    if any(s["minutes_asleep"] is None for s in ordered):
        return None, "summary_missing"
    total = sum(s["minutes_asleep"] for s in ordered)
    if total > 2880:
        raise SleepError("睡眠時間が確認範囲を超えています")
    return total, "present"


@dataclass(frozen=True)
class SleepSnapshot:
    date: str
    minutes: int | None
    observed_at: str
    account_hash: str
    missing_state: str
    sessions: tuple


class GoogleSleep(GoogleSteps):
    def __init__(self, access_token, expected_health_user_id, *, transport=request_sleep_json, now=None):
        super().__init__(access_token, expected_health_user_id, transport=transport, now=now)

    def fetch_day(self, target, zone_name):
        day = parse_day(target)
        try:
            zone = timezone.utc if zone_name == "UTC" else ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise SleepError("睡眠の集計タイムゾーンを確認してください") from None
        identity = self._transport("GET", BASE + "users/me/identity", None, self._token)
        if not isinstance(identity, dict) or identity.get("healthUserId") != self._expected:
            raise SleepError("Google Healthの本人確認が一致しません")
        start = datetime.combine(day, datetime.min.time(), tzinfo=zone).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=zone).astimezone(timezone.utc)
        query = {"pageSize": 25, "filter": f'sleep.interval.end_time >= "{start.isoformat()}" AND sleep.interval.end_time < "{end.isoformat()}"'}
        seen, items = set(), {}
        for _ in range(20):
            response = self._transport("GET", ENDPOINT + "?" + urlencode(query), None, self._token)
            if not isinstance(response, dict) or not isinstance(response.get("dataPoints", []), list):
                raise SleepError("睡眠一覧が不正です")
            points = response.get("dataPoints", [])
            if len(points) > 25:
                raise SleepError("睡眠一覧が指定範囲を超えています")
            for point in points:
                item = session(point, day, zone)
                if item["id"].split("/")[1] not in {"me", self._expected}:
                    raise SleepError("睡眠の取得元アカウントが一致しません")
                if item["id"] in items and items[item["id"]] != item:
                    raise SleepError("同じ睡眠IDに異なる値があります")
                items[item["id"]] = item
            page = response.get("nextPageToken", "")
            if not isinstance(page, str):
                raise SleepError("睡眠一覧のページが不正です")
            if not page:
                break
            if len(page) > 4096 or page in seen:
                raise SleepError("睡眠一覧のページが不正です")
            seen.add(page)
            query["pageToken"] = page
        else:
            raise SleepError("睡眠一覧の取得が完了しませんでした")
        sessions = tuple(sorted(items.values(), key=lambda s: (s["start"], s["id"])))
        minutes, missing = summarize(sessions)
        observed = self._now()
        if observed.utcoffset() is None:
            raise SleepError("取得時刻にタイムゾーンが必要です")
        return SleepSnapshot(target, minutes, observed.astimezone(timezone.utc).isoformat(timespec="seconds"),
                             hashlib.sha256(self._expected.encode()).hexdigest(), missing, sessions)


def save_snapshot(store, snapshot):
    if not isinstance(snapshot, SleepSnapshot):
        raise SleepError("検証済みの睡眠記録が必要です")
    parse_day(snapshot.date)
    observed = stamp(snapshot.observed_at)
    if (not re.fullmatch(r"[a-f0-9]{64}", snapshot.account_hash)
            or snapshot.missing_state not in MISSING
            or summarize(snapshot.sessions) != (snapshot.minutes, snapshot.missing_state)):
        raise SleepError("睡眠記録が不正です")
    provenance = {"window_date": snapshot.date, "account_hash": snapshot.account_hash,
                  "identity_verified": True, "fit_sync_verified": False,
                  "missing_state": snapshot.missing_state, "sleep_sessions": list(snapshot.sessions)}
    content = json.dumps(provenance, sort_keys=True, ensure_ascii=False)
    identifier = str(uuid5(NAMESPACE_URL, "lacia-sleep:" + content + snapshot.observed_at))
    record = {"id": identifier, "kind": "sleep", "occurred_at": snapshot.observed_at, "value": snapshot.minutes,
              "text": "Google Healthの睡眠。起床日で集計し、昼寝を含む。欠測は0時間にしない。"}
    with store.lock, store.exclude_sync():
        previous = []
        for path in store.record_paths(f"{snapshot.date}_健康記録_*_*.md"):
            if path.is_symlink() or path.stat().st_size > 256 * 1024:
                continue
            try:
                fields = dict(line.split(": ", 1) for line in path.read_text(encoding="utf-8").split("\n---\n", 1)[0][4:].splitlines())
                if fields.get("kind") != "sleep" or fields.get("source") != "google_health":
                    continue
                if json.loads(fields["account_hash"]) != snapshot.account_hash:
                    continue
                same = all(json.loads(fields[k]) == v for k, v in provenance.items()) and json.loads(fields["value"]) == snapshot.minutes
                previous.append((stamp(fields["occurred_at"]), path, same))
            except (ValueError, KeyError, TypeError, OSError, SleepError):
                continue
        if previous:
            newest = max(previous, key=lambda item: item[0])
            if newest[2] and newest[0] <= observed:
                return {"path": newest[1].relative_to(store.root).as_posix(), "unchanged": True}
        return store._save(record, record_day=snapshot.date, provenance=provenance)
