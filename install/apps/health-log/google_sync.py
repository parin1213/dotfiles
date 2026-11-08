"""継続同期の1回分。実行には承認後の暗号化資格情報と公開設定が必要。"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from google_once import AuthError, TOKEN_URL, post_form
from google_steps import GoogleSteps, StepsError, SCOPE, request_json, save_snapshot
from server import Store, refresh_dashboard
from sync_credentials import CredentialError, encrypt_bundle, load_runtime, rotated
from sync_state import write_status


class SyncFailure(Exception):
    def __init__(self, reason, completed=0):
        self.reason, self.completed = reason, completed
        super().__init__("歩数同期を停止しました: " + reason)


def target_days(now, zone_name, day_count=2):
    if type(day_count) is not int or not 1 <= day_count <= 2 or not zone_name or now.utcoffset() is None:
        raise SyncFailure("configuration_required")
    try:
        zone = timezone.utc if zone_name == "UTC" else ZoneInfo(zone_name)
        today = now.astimezone(zone).date()
    except (ZoneInfoNotFoundError, ValueError):
        raise SyncFailure("configuration_required") from None
    return [str(today - timedelta(days=offset)) for offset in reversed(range(day_count))]


def run_sync(bundle, store, *, zone_name, expected_account, expected_project, day_count=2, now=None, grant=post_form,
             api=request_json, credential_writer=None):
    now = now or datetime.now(timezone.utc)
    days = target_days(now, zone_name, day_count)
    try:
        bundle.live(now)
    except CredentialError:
        raise SyncFailure("credential_expired_or_invalid") from None
    if bundle.account != expected_account or bundle.project_id != expected_project:
        raise SyncFailure("credential_account_mismatch")
    response, token, completed = None, None, 0
    try:
        response = grant(TOKEN_URL, {"grant_type": "refresh_token", "client_id": bundle.client_id,
                          "client_secret": bundle.client_secret, "refresh_token": bundle.refresh_token})
        if (not isinstance(response, dict) or str(response.get("token_type", "")).lower() != "bearer"
                or ("scope" in response and set(str(response["scope"]).split()) != {SCOPE})):
            raise SyncFailure("invalid_grant_response")
        token = response.get("access_token")
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise SyncFailure("invalid_grant_response")
        if "refresh_token" in response and response["refresh_token"] != bundle.refresh_token:
            if credential_writer is None:
                raise SyncFailure("credential_rotation_not_saved")
            try:
                credential_writer(rotated(bundle, response["refresh_token"]))
            except Exception:
                raise SyncFailure("credential_rotation_not_saved") from None
        client = GoogleSteps(token, bundle.health_user_id, transport=api, now=lambda: now)
        # 取得段階が一部で失敗したら、その回は新しいノートを書かない。
        snapshots = [client.fetch_day(day) for day in days]
        for snapshot in snapshots:
            save_snapshot(store, snapshot)
            completed += 1
        with store.lock, store.exclude_sync():
            dashboard_status = refresh_dashboard(store.root)
        return {"status": "success", "completed_day_count": completed, "requested_day_count": len(days),
                "dashboard_status": dashboard_status}
    except AuthError:
        raise SyncFailure("authentication_failed", completed) from None
    except StepsError:
        raise SyncFailure("data_request_failed", completed) from None
    except (OSError, ValueError):
        raise SyncFailure("vault_save_failed", completed) from None
    finally:
        if isinstance(response, dict):
            response.clear()
        token = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    state = Path.home() / ".local/state/health-steps-sync/status.json"
    encrypted = Path.home() / ".local/share/health-steps-sync/credentials/google-health.cred"
    code = 1
    try:
        with args.config.open("rb") as source:
            settings = tomllib.load(source)["health_steps_sync"]
        runtime = os.environ.get("CREDENTIALS_DIRECTORY")
        if not runtime:
            raise SyncFailure("missing_runtime_credentials")
        result = run_sync(load_runtime(runtime), Store(args.vault), zone_name=settings["timezone"],
                          expected_account=settings["account"], expected_project=settings["project_id"],
                          day_count=settings["recent_days"], now=now,
                          credential_writer=lambda bundle: encrypt_bundle(bundle, encrypted))
        code = 0
    except SyncFailure as error:
        result = {"status": "error", "error_code": error.reason, "completed_day_count": error.completed}
    except CredentialError:
        result = {"status": "error", "error_code": "missing_or_invalid_credentials"}
    except Exception:
        result = {"status": "error", "error_code": "configuration_or_storage_error"}
    try:
        write_status(state, result, now)
    except OSError:
        result = {"status": "error", "error_code": "status_save_failed"}
        code = 1
    print("歩数同期: " + ("成功" if code == 0 else "失敗（" + result["error_code"] + "）"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
