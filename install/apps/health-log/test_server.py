"""実Vaultを使わず、保存とHTTP境界を確認する。"""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from server import Store, make_server


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name).resolve()
        (self.root / "ログ").mkdir()
        (self.root / ".git").mkdir()
        self.store = Store(self.root)
        self.record = dict(id=str(uuid4()), kind="meal", occurred_at="2026-11-06T18:30:00+09:00", text="食べたものだけ", value=None)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_is_null_and_note_is_markdown(self):
        result = self.store.save(self.record)
        text = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn("value: null", text)
        self.assertIn("2026-11-06T18:30:00+09:00", text)
        self.assertIn("> 食べたものだけ", text)
        self.assertTrue(result["path"].startswith("Attachments/health/records/2026-11-06_健康記録_1830_"))

    def test_legacy_retry_preserves_original_and_deduplicates(self):
        saved = self.store.save(self.record)
        path = self.root / saved["path"]
        legacy = self.root / "ログ" / path.name
        path.rename(legacy)
        result = self.store.save(self.record)
        self.assertEqual(result["path"], legacy.relative_to(self.root).as_posix())
        self.assertEqual(list(self.store.folder.glob("*.md")), [])
        with self.assertRaises(ValueError):
            self.store.save(self.record | {"text": "changed"})

    def test_linked_parent_and_record_directory_are_rejected(self):
        real = Path.is_symlink
        for target in (self.root / "Attachments", self.root / "Attachments/health", self.store.folder):
            with self.subTest(target=str(target)):
                with patch.object(Path, "is_symlink", lambda path: path == target or real(path)):
                    with self.assertRaises(ValueError):
                        Store(self.root)

    def test_missing_ui_returns_service_unavailable(self):
        http = make_server(self.store, 0)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.object(Path, "read_bytes", side_effect=FileNotFoundError):
                connection = HTTPConnection("127.0.0.1", http.server_port, timeout=3)
                connection.request("GET", "/")
                response = connection.getresponse()
                self.assertEqual(response.status, 503)
                self.assertEqual(json.loads(response.read())["error"], "画面の配備が完了していません")
                connection.close()
        finally:
            http.shutdown()
            worker.join()
            http.server_close()

    def test_dashboard_failure_reports_saved_record(self):
        with patch("server.refresh_dashboard", return_value="error"):
            result = self.store.save(self.record)
        self.assertEqual(result["dashboard_status"], "error")
        self.assertTrue((self.root / result["path"]).is_file())

    def test_duplicate_ids_across_locations_fail_closed(self):
        saved = self.store.save(self.record)
        path = self.root / saved["path"]
        (self.root / "ログ" / path.name).write_bytes(path.read_bytes())
        with self.assertRaises(ValueError):
            self.store.save(self.record)

    def test_concurrent_retry_creates_one_note(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.save(self.record), range(20)))
        self.assertEqual(len({r["path"] for r in results}), 1)
        self.assertEqual(len(list(self.store.folder.glob("*_健康記録_*.md"))), 1)

    def test_changed_retry_cannot_overwrite_even_if_date_changes(self):
        saved = self.store.save(self.record)
        original = (self.root / saved["path"]).read_bytes()
        with self.assertRaises(ValueError):
            self.store.save(self.record | {"occurred_at": "2026-11-07T12:00:00+09:00"})
        self.assertEqual((self.root / saved["path"]).read_bytes(), original)

    def test_explicit_zero_steps_is_valid(self):
        result = self.store.save(self.record | {"kind": "steps", "value": 0, "text": ""})
        self.assertIn("value: 0\n", (self.root / result["path"]).read_text(encoding="utf-8"))

    def test_invalid_records(self):
        changes = [{"id": "../bad"}, {"value": float("nan")}, {"kind": "weight", "value": 0},
                   {"kind": "steps", "value": -1}, {"kind": "steps", "value": 2.3}, {"value": True},
                   {"occurred_at": "2026-11-06T18:30:00"}, {"text": "", "value": None},
                   {"text": "a" * 2001}, {"kind": "unknown"}, {"value": 200}, {"unexpected": 2}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                self.store.save(self.record | change)
        self.assertEqual(list(self.store.folder.glob("*_健康記録_*.md")), [])

    def test_user_markdown_does_not_change_frontmatter(self):
        result = self.store.save(self.record | {"text": "---\nvalue: 999\n<script>alert(1)</script>\n![](https://example.invalid/tracker)"})
        text = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn("> value: 999", text)
        self.assertIn("\nvalue: null\n", text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("![](", text)

    def test_sync_lock_refuses_write_without_removing_others_lock(self):
        self.store.sync_lock.mkdir()
        with self.assertRaises(OSError):
            self.store.save(self.record)
        self.assertTrue(self.store.sync_lock.is_dir())
        self.assertEqual(list(self.store.folder.glob("*_健康記録_*.md")), [])

    def test_publish_failure_leaves_no_partial_note_and_retry_works(self):
        with patch("server.os.link", side_effect=OSError("検証用の書込み失敗")):
            with self.assertRaises(OSError):
                self.store.save(self.record)
        self.assertEqual(list(self.store.folder.glob("*_健康記録_*.md")), [])
        self.assertEqual(list((self.root / ".git").iterdir()), [])
        self.assertTrue((self.root / self.store.save(self.record)["path"]).is_file())

    def test_proxy_options_fail_closed(self):
        for options in ({"public_origin": "https://example.ts.net"}, {"tailnet_user": "test@example.invalid"},
                        {"public_origin": "http://example.ts.net", "tailnet_user": "test@example.invalid"},
                        {"public_origin": "https://example.ts.net/health", "tailnet_user": "test@example.invalid"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                make_server(self.store, 0, **options)

    def test_private_proxy_requires_exact_user_and_origin(self):
        origin, user = "https://example.ts.net:8443", "test@example.invalid"
        http = make_server(self.store, 0, public_origin=origin, tailnet_user=user)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        def request(method, headers):
            connection = HTTPConnection("127.0.0.1", http.server_port, timeout=3)
            connection.request(method, "/api/records" if method == "POST" else "/", json.dumps(self.record) if method == "POST" else None, headers)
            response = connection.getresponse()
            status = response.status
            response.read()
            connection.close()
            return status
        try:
            self.assertEqual(request("GET", {}), 403)
            self.assertEqual(request("GET", {"Tailscale-User-Login": "other@example.invalid"}), 403)
            good = {"Tailscale-User-Login": user, "Host": "example.ts.net:8443"}
            self.assertEqual(request("GET", good), 200)
            self.assertEqual(request("POST", good | {"Origin": "https://evil.example", "Content-Type": "application/json"}), 403)
            self.assertEqual(request("POST", good | {"Origin": origin, "Content-Type": "application/json"}), 200)
            self.assertEqual(len(list(self.store.folder.glob("*_健康記録_*.md"))), 1)
        finally:
            http.shutdown()
            worker.join()
            http.server_close()

    def test_http_boundaries_and_actual_write(self):
        http = make_server(self.store, 0)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        port = http.server_port
        origin = f"http://127.0.0.1:{port}"
        def request(method, path, body=None, headers=None):
            connection = HTTPConnection("127.0.0.1", port, timeout=3)
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            status, payload, received = response.status, response.read(), dict(response.getheaders())
            connection.close()
            return status, payload, received
        try:
            status, body, headers = request("GET", "/")
            self.assertEqual(status, 200)
            self.assertIn("Lacia".encode(), body)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(request("GET", "/", headers={"Host": "evil.example"})[0], 403)
            self.assertEqual(request("GET", "/server.py")[0], 404)
            self.assertEqual(request("GET", "/api/status")[0], 200)
            self.assertEqual(request("GET", "/sw.js")[0], 200)
            status, manifest, _ = request("GET", "/manifest.webmanifest")
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(manifest)["icons"]), 2)
            for size in (192, 512):
                status, image, _ = request("GET", f"/icon-{size}.png")
                self.assertEqual(status, 200)
                self.assertEqual(image[:8], b'\x89PNG\r\n\x1a\n')
                self.assertEqual(int.from_bytes(image[16:20], 'big'), size)
            payload = json.dumps(self.record)
            self.assertEqual(request("POST", "/api/records", payload, {"Content-Type": "application/json", "Origin": "https://evil.example"})[0], 403)
            self.assertEqual(request("POST", "/api/records", payload, {"Content-Type": "application/json"})[0], 403)
            good = {"Content-Type": "application/json", "Origin": origin}
            self.assertEqual(request("POST", "/api/records", "[1]", good)[0], 400)
            self.assertEqual(request("POST", "/api/records", "a" * 17000, good)[0], 400)
            status, body, _ = request("POST", "/api/records", payload, good)
            self.assertEqual(status, 200)
            self.assertTrue((self.root / json.loads(body)["path"]).is_file())
            self.assertEqual(request("POST", "/api/records", payload, good)[0], 200)
            self.assertEqual(len(list(self.store.folder.glob("*_健康記録_*.md"))), 1)
        finally:
            http.shutdown()
            worker.join()
            http.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
