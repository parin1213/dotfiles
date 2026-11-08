"""既存の健康記録保存処理をMCPから使い、日付別の観測値を読む。"""
from datetime import date, datetime
from functools import lru_cache
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
from uuid import UUID


@lru_cache(maxsize=2)
def app_module(name):
    if name not in {"server", "sync_state"}:
        raise ValueError("未対応の健康記録モジュールです")
    path = Path(__file__).resolve().parent.parent / "health-log" / (name + ".py")
    # 固定したリポジトリ内のモジュールを読むだけで、HTTPサーバーは起動しない。
    spec = importlib.util.spec_from_file_location("obsidian_health_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def storage_module():
    return app_module("server")


SCOPE_TEXT = "health_dayはアプリ形式の記録だけを取得。既存台帳はsearch/fetchで参照"


def status(state_path=None):
    result = {"steps_connection": "未接続", "automatic_steps": False,
            "storage": "機械原記録はAttachments/health/records、既存のログ/も読取対応",
            "sync": "端末間のGit同期完了は未確認",
            "scope": SCOPE_TEXT}
    result.update(app_module("sync_state").describe(state_path))
    return result


def record(root, record_id, kind, occurred_at, text="", value=None):
    saved = storage_module().Store(root).save({"id": record_id, "kind": kind,
        "occurred_at": occurred_at, "text": text, "value": value})
    return {"id": saved["path"], **saved, "sync": "Gitの端末間同期は未確認"}


def day(vault, day):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("日付はYYYY-MM-DDで指定してください")
    date.fromisoformat(day)
    folders = storage_module().record_folders(vault.root)
    records, skipped = [], 0
    paths = sorted(path for folder in folders for path in folder.glob(f"{day}_健康記録_*_*.md"))
    if len(paths) > 200:
        raise ValueError("対象日の記録が200件を超えています。search/fetchで確認してください")
    for path in paths:
        relative = path.relative_to(vault.root).as_posix()
        try:
            body = vault.read(relative)
            if not body.startswith("---\n"):
                raise ValueError("未対応の形式")
            header = body.split("\n---\n", 1)[0][4:]
            fields = {}
            for line in header.splitlines():
                key, value = line.split(": ", 1)
                if key in fields:
                    raise ValueError("重複した項目")
                fields[key] = value
            stamp = datetime.fromisoformat(fields["occurred_at"])
            record_id = str(UUID(fields["record_id"]))
            kind, value = fields["kind"], json.loads(fields["value"])
            source = fields["source"]
            expected = f"{day}_健康記録_{stamp:%H%M}_{record_id}.md"
            if (path.name != expected or fields["type"] != "log" or fields["date"] != day
                    or stamp.utcoffset() is None or source not in {"manual", "google_health"}
                    or (source == "manual" and str(stamp.date()) != day)
                    or kind not in {"meal", "weight", "steps"}):
                raise ValueError("記録の形式が一致しません")
            unit = json.loads(fields["unit"])
            if unit != {"meal": "", "weight": "kg", "steps": "steps"}[kind]:
                raise ValueError("単位が一致しません")
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("数値が不正です")
                if kind == "meal" or (kind == "weight" and not 0 < value <= 500) or (kind == "steps" and (not 0 <= value <= 200000 or int(value) != value)):
                    raise ValueError("数値が範囲外です")
            provenance = {}
            if source == "google_health":
                missing = json.loads(fields["missing_state"])
                if (kind != "steps" or json.loads(fields["window_date"]) != day
                        or json.loads(fields["data_source_family"]) != "users/me/dataSourceFamilies/all-sources"
                        or json.loads(fields["identity_verified"]) is not True
                        or json.loads(fields["fit_sync_verified"]) is not False
                        or not re.fullmatch(r"[a-f0-9]{64}", json.loads(fields["account_hash"]))
                        or missing not in {"present", "steps_omitted", "no_window"}
                        or (value is None) != (missing != "present")):
                    raise ValueError("API取得元の情報が不正です")
                provenance = {"window_date": day, "missing_state": missing,
                              "fit_sync_verified": False, "identity_verified": True,
                              "data_source_family": json.loads(fields["data_source_family"])}
            records.append({"id": relative, "record_id": record_id, "kind": kind,
                            "occurred_at": stamp.isoformat(), "value": value, "unit": unit, "source": source, **provenance})
        except (ValueError, KeyError, TypeError, OverflowError, OSError, UnicodeError):
            skipped += 1
    by_id = {}
    conflicts = set()
    for record in records:
        key = record["record_id"]
        comparable = {k: v for k, v in record.items() if k != "id"}
        if key in by_id and comparable != {k: v for k, v in by_id[key].items() if k != "id"}:
            conflicts.add(key)
        else:
            by_id[key] = record
    skipped += len(conflicts)
    records = [record for key, record in by_id.items() if key not in conflicts]
    records.sort(key=lambda item: (datetime.fromisoformat(item["occurred_at"]), item["record_id"]))
    # 同日の累計歩数を足さない。複数の同時刻観測は優劣を決められないため全て返す。
    latest = {}
    for kind in ("weight", "steps"):
        observations = [r for r in records if r["kind"] == kind]
        latest[kind] = [r for r in observations if datetime.fromisoformat(r["occurred_at"]) == datetime.fromisoformat(observations[-1]["occurred_at"])] if observations else []
    return {"date": day, "records": records, "latest_observations": latest,
            "skipped_invalid": skipped, "complete_day": False,
            "scope": SCOPE_TEXT, "note": "欠測はnull。歩数は累計の観測値で、足し合わせません。訂正ノートは自動適用しません。"}
