"""歩数と睡眠の同期状態を、健康値や資格情報を含めず検証する。"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from google_sync import main
from sync_state import describe, read_status, write_status


class SleepStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.path = Path(self.temp.name) / "status.json"
        self.now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def test_sleep_failure_keeps_step_success_without_full_success_timestamp(self):
        write_status(self.path, {"status": "success", "completed_day_count": 2}, self.now)
        result = {"status": "error", "steps_status": "success", "sleep_status": "error",
                  "error_code": "sleep_data_request_failed", "sleep_error_code": "sleep_data_request_failed",
                  "completed_day_count": 2, "sleep_completed_day_count": 0, "sleep_hours": 7,
                  "access_token": "fixture-private-token"}
        write_status(self.path, result, self.now + timedelta(hours=1))
        state = read_status(self.path)
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["steps_status"], "success")
        self.assertEqual(state["sleep_status"], "error")
        self.assertEqual(state["last_success_at"], self.now.isoformat())
        self.assertEqual(state["sleep_error_code"], "sleep_data_request_failed")
        self.assertEqual(state["completed_day_count"], 2)
        self.assertNotIn("sleep_hours", state)
        self.assertNotIn("fixture-private-token", self.path.read_text(encoding="utf-8"))
        with patch("sync_state.subprocess.run", return_value=SimpleNamespace(returncode=0)):
            described = describe(self.path)
        self.assertEqual(described["steps_connection"], "前回の取得は成功")
        self.assertEqual(described["sleep_connection"], "前回の取得は失敗")
        self.assertTrue(described["automatic_steps"])
        self.assertTrue(described["automatic_sleep"])

    def test_steps_only_status_does_not_claim_sleep_connection(self):
        write_status(self.path, {"status": "success", "sleep_status": "not_authorized"}, self.now)
        with patch("sync_state.subprocess.run", return_value=SimpleNamespace(returncode=0)):
            result = describe(self.path)
        self.assertFalse(result["automatic_sleep"])
        self.assertEqual(result["sleep_connection"], "未接続")

    def test_invalid_sleep_fields_are_omitted(self):
        write_status(self.path, {"status": "error", "sleep_status": "fixture-private-status",
                                "sleep_error_code": "fixture-private-error", "sleep_completed_day_count": True,
                                "steps_status": "fixture-private-status"}, self.now)
        state = read_status(self.path)
        self.assertNotIn("sleep_status", state)
        self.assertNotIn("sleep_error_code", state)
        self.assertNotIn("sleep_completed_day_count", state)
        self.assertNotIn("steps_status", state)
        self.assertNotIn("fixture-private", json.dumps(state))

    def test_sleep_error_main_exits_nonzero(self):
        settings = {"health_steps_sync": {"timezone": "UTC", "account": "test@example.invalid",
                                         "project_id": "test-health-project", "recent_days": 2}}
        result = {"status": "error", "error_code": "sleep_data_request_failed", "steps_status": "success"}
        with patch("sys.argv", ["google_sync.py", "--vault", str(self.path.parent), "--config", str(self.path)]), \
             patch("google_sync.Path.open"), patch("google_sync.tomllib.load", return_value=settings), \
             patch("google_sync.os.environ.get", return_value="fixture-runtime"), \
             patch("google_sync.load_runtime"), patch("google_sync.Store"), \
             patch("google_sync.run_sync", return_value=result), patch("google_sync.write_status") as status, \
             patch("builtins.print"):
            self.assertEqual(main(), 1)
        self.assertEqual(status.call_args.args[1], result)


if __name__ == "__main__":
    unittest.main()
