"""MCPへ出す同期状態は、日時・成否・稼働状況だけに限定する。"""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import health


class HealthStatusTests(unittest.TestCase):
    def test_missing_state_never_reads_credentials_or_checks_timer(self):
        with tempfile.TemporaryDirectory() as folder, patch("health.subprocess.run") as process:
            result = health.status(Path(folder)/"missing.json")
            self.assertFalse(result["automatic_steps"])
            process.assert_not_called()

    def test_valid_state_reports_timer_without_leaking_unknown_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"status.json"
            module = health.app_module("sync_state")
            module.write_status(path,{"status":"success","completed_day_count":2},datetime(2026,11,6,tzinfo=timezone.utc))
            data = json.loads(path.read_text()) | {"client_secret":"fixture-private", "steps":17}
            path.write_text(json.dumps(data))
            with patch("health.subprocess.run",return_value=SimpleNamespace(returncode=0)) as process:
                result = health.status(path)
            self.assertTrue(result["automatic_steps"])
            self.assertEqual(result["last_run"]["status"],"success")
            self.assertNotIn("fixture-private",json.dumps(result))
            self.assertNotIn("steps",result["last_run"])
            self.assertEqual(process.call_args.args[0],["systemctl","--user","is-active","--quiet","health-steps-sync.timer"])

    def test_inactive_timer_and_previous_failure_are_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"status.json"
            health.app_module("sync_state").write_status(path,{"status":"error","error_code":"authentication_failed"},datetime(2026,11,6,tzinfo=timezone.utc))
            with patch("health.subprocess.run",return_value=SimpleNamespace(returncode=3)):
                result = health.status(path)
            self.assertFalse(result["automatic_steps"])
            self.assertEqual(result["scheduler"],"停止中")
            self.assertEqual(result["last_run"]["error_code"],"authentication_failed")

    def test_credential_shaped_file_is_not_exposed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"status.json"
            path.write_text('{"refresh_token":"fixture-private"}')
            self.assertNotIn("fixture-private",json.dumps(health.status(path)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
