"""健康値や資格情報を含めず、同期の日時と成否だけを保存・取得する。"""
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import subprocess

ERROR_CODES = {"configuration_required", "credential_expired_or_invalid", "invalid_grant_response",
    "credential_account_mismatch",
    "credential_rotation_not_saved", "authentication_failed", "data_request_failed", "vault_save_failed",
    "missing_runtime_credentials", "missing_or_invalid_credentials", "configuration_or_storage_error", "status_save_failed",
    "sleep_data_request_failed", "sleep_vault_save_failed"}


def safe_details(data):
    result = {}
    if data.get("error_code") in ERROR_CODES:
        result["error_code"] = data["error_code"]
    if data.get("sleep_error_code") in {"sleep_data_request_failed", "sleep_vault_save_failed"}:
        result["sleep_error_code"] = data["sleep_error_code"]
    for key in ("completed_day_count", "requested_day_count", "sleep_completed_day_count"):
        value = data.get(key)
        if type(value) is int and 0 <= value <= 2:
            result[key] = value
    for key in ("dashboard_status", "steps_status"):
        if data.get(key) in {"success", "error"}:
            result[key] = data[key]
    if data.get("sleep_status") in {"success", "error", "not_authorized"}:
        result["sleep_status"] = data["sleep_status"]
    return result


def safe_time(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.isoformat() if parsed.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def read_status(path):
    path = Path(path)
    try:
        if path.is_symlink() or path.stat().st_size > 8192:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("kind") != "health_steps_sync_status" or data.get("schema") != 1
                or data.get("status") not in {"success", "error"} or not safe_time(data.get("last_attempt_at"))):
            return None
        result = {"status": data["status"], "last_attempt_at": safe_time(data["last_attempt_at"]),
                  "last_success_at": safe_time(data.get("last_success_at"))}
        return result | safe_details(data)
    except (OSError, ValueError, TypeError):
        return None


def write_status(path, result, now):
    path = Path(path)
    if path.is_symlink():
        raise OSError("状態ファイルが不正です")
    previous = read_status(path)
    allowed = {"status": "success" if result.get("status") == "success" else "error"}
    allowed.update(safe_details(result))
    payload = {"kind": "health_steps_sync_status", "schema": 1, **allowed,
               "last_attempt_at": now.isoformat(),
               "last_success_at": now.isoformat() if allowed["status"] == "success" else previous.get("last_success_at") if previous else None}
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".status-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False)
        Path(temporary).chmod(0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def describe(path=None):
    result = {"steps_connection": "未接続", "automatic_steps": False,
              "sleep_connection": "未接続", "automatic_sleep": False}
    state = read_status(path or Path.home() / ".local/state/health-steps-sync/status.json")
    if not state:
        return result
    try:
        active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", "health-steps-sync.timer"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        active = None
    steps_status = state.get("steps_status", state["status"])
    sleep_status = state.get("sleep_status", "not_authorized")
    result.update(automatic_steps=active, last_run=state,
                  steps_connection="前回の取得は成功" if steps_status == "success" else "前回の取得は失敗",
                  scheduler="稼働中" if active is True else "停止中" if active is False else "未確認")
    if sleep_status in {"success", "error"}:
        result.update(automatic_sleep=active,
                      sleep_connection="前回の取得は成功" if sleep_status == "success" else "前回の取得は失敗")
    return result
