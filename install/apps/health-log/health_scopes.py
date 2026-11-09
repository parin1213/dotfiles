"""継続同期に許可する読取り範囲を検証する。"""
from google_steps import SCOPE


SLEEP_SCOPE = "https://www.googleapis.com/auth/googlehealth.sleep.readonly"


def scope_set(value):
    if not isinstance(value, str):
        raise ValueError("許可されたスコープを確認できません")
    entries = value.split()
    scopes = frozenset(entries)
    if len(entries) != len(scopes) or scopes not in (frozenset({SCOPE}), frozenset({SCOPE, SLEEP_SCOPE})):
        raise ValueError("歩数のみ、または歩数と睡眠の読取り権限だけを使用します")
    return scopes


def requested_scope(include_sleep=False):
    if type(include_sleep) is not bool:
        raise ValueError("睡眠の読取りを追加するか確認してください")
    return SCOPE + " " + SLEEP_SCOPE if include_sleep else SCOPE
