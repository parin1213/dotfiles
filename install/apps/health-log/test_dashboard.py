"""実Vaultを変更せず、健康表示の集計・欠測・出力境界を確認。"""
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
from dashboard import generate, parse_meals, parse_weights, parse_snapshot, load_steps, safe_path

MEAL = """# 食事ログ
## 最近の食事
| 日付 | 朝 | 昼 | 夕 | 間食 | 記録分の合計 |
|---|---|---|---|---|---|
| [[#2026-11-08\\|11/8]] | 500 | 540 | 450〜550 | 未記録 | **約1,490〜1,590** ※ |
| [[#2026-11-07\\|11/7]] | 500 | 600 | 500 | 361 | **1,961** |
## 日付別の詳細
| 2026-11-08 | a | b | c | d | 9999 |
"""
WEIGHT = """| 日付 | タイミング | 体重 (kg) |
| 2026-03-21 | 起床時 | 96.3 |
| 2026-03-21 | 就寝前 | 98.1 |
| 2026-06-20 | 就寝前 | 93.05 |
記憶では93〜95kg
"""


def snapshot(value, hour="08", day="2026-11-07"):
    return f'---\nkind: steps\ndate: {day}\nwindow_date: "{day}"\noccurred_at: 2026-11-07T{hour}:19:03+00:00\nvalue: {value}\n---\n'


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "ログ").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def note(self, name, body):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def test_canonical_meal_table_only(self):
        records = parse_meals(MEAL)
        self.assertEqual(len(records), 2)
        self.assertEqual((records[-1]["low"], records[-1]["high"]), (1490, 1590))
        self.assertTrue(records[-1]["partial"])
        self.assertFalse(records[0]["partial"])

    def test_same_day_correction_replaces_not_adds(self):
        body = MEAL.replace("## 日付別の詳細", "| [[#2026-11-08\\|11/8]] | a | b | c | d | 1400〜1500 |\n## 日付別の詳細")
        records = parse_meals(body)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[-1]["low"], 1400)

    def test_weight_conditions_and_nonmeasurement(self):
        records = parse_weights(WEIGHT)
        self.assertEqual(len(records), 3)
        self.assertEqual(len({r["condition"] for r in records}), 2)
        self.assertEqual(records[-1]["value"], 93.05)

    def test_weight_correction(self):
        records = parse_weights(WEIGHT + '| 2026-06-20 | 就寝前 | 93.1 |\n')
        self.assertEqual(len(records), 3)
        self.assertEqual(records[-1]["value"], 93.1)

    def test_latest_steps_not_sum_across_locations(self):
        self.note("ログ/2026-11-07_健康記録_0619_a.md", snapshot(9, "06"))
        self.note("Attachments/health/records/2026-11-07_健康記録_0719_b.md", snapshot(3382, "07"))
        self.note("Attachments/health/records/2026-11-07_健康記録_0819_c.md", snapshot(7025))
        self.assertEqual(load_steps(self.root)[0]["value"], 7025)

    def test_new_missing_is_not_old_value_or_zero(self):
        self.note("ログ/2026-11-07_健康記録_0619_a.md", snapshot(9, "06"))
        self.note("ログ/2026-11-07_健康記録_0819_c.md", snapshot("null"))
        self.assertIsNone(load_steps(self.root)[0]["value"])
        self.assertEqual(parse_snapshot(snapshot(0))["value"], 0)

    def test_same_time_conflict_is_unknown(self):
        self.note("ログ/2026-11-07_健康記録_0819_a.md", snapshot(9))
        self.note("ログ/2026-11-07_健康記録_0819_b.md", snapshot(10))
        self.assertIsNone(load_steps(self.root)[0]["value"])

    def test_invalid_steps_ignored(self):
        self.assertIsNone(parse_snapshot(snapshot("true")))
        self.assertIsNone(parse_snapshot(snapshot(-1)))
        self.assertIsNone(parse_snapshot(snapshot("NaN")))
        self.assertIsNone(parse_snapshot(snapshot(1).replace("+00:00", "")))

    def test_generation_is_idempotent_valid_svg_and_stale(self):
        self.note("ログ/食事ログ.md", MEAL)
        self.note("ログ/体重記録.md", WEIGHT)
        self.note("ログ/2026-11-08_健康記録_0819_a.md", snapshot("null", day="2026-11-08"))
        result = generate(self.root, today=date(2026, 11, 8))
        self.assertEqual(len(result["changed"]), 4)
        content = (self.root / "ログ/健康ダッシュボード.md").read_text(encoding="utf-8")
        self.assertIn("現在の体重ではありません", content)
        self.assertIn("欠測（0歩ではありません）", content)
        self.assertIn("1490〜1590", content)
        for path in (self.root / "Attachments/health").glob("*.svg"):
            ElementTree.fromstring(path.read_text(encoding="utf-8"))
        before = {p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(generate(self.root, today=date(2026, 11, 8))["changed"], [])
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()})

    def test_freshness_dates_navigation_and_stable_update(self):
        self.note("ログ/食事ログ.md", MEAL)
        self.note("ログ/体重記録.md", WEIGHT)
        self.note("ログ/2026-11-07_健康記録_0819_a.md", snapshot(7025))
        first = datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc)
        later = datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc)
        generate(self.root, now=first)
        path = self.root / "ログ/健康ダッシュボード.md"
        content = path.read_text(encoding="utf-8")
        self.assertIn("2026-11-07 17:19:03 JST", content)
        self.assertIn("**食事の最新記録日**：2026-11-08", content)
        self.assertIn("**体重の最新実測日**：2026-06-20", content)
        self.assertIn("[[健康方針|", content)
        self.assertIn("[[健診記録|", content)
        self.assertIn("updated_at: 2026-11-08T17:00:00+09:00", content)
        self.assertEqual(generate(self.root, now=later)["changed"], [])
        self.assertEqual(path.read_text(encoding="utf-8"), content)
        self.note("ログ/食事ログ.md", MEAL.replace("1,961", "1,962"))
        self.assertIn("ログ/健康ダッシュボード.md", generate(self.root, now=later)["changed"])
        self.assertIn("updated_at: 2026-11-08T18:00:00+09:00", path.read_text(encoding="utf-8"))

    def test_empty_fixture_supported(self):
        result = generate(self.root, today=date(2026, 11, 8))
        self.assertEqual(result["meal_days"], 0)
        self.assertEqual(result["weight_measurements"], 0)
        self.assertEqual(result["step_days"], 0)

    def test_traversal_and_absolute_denied(self):
        for path in ("../escape.md", str(self.root.parent / "escape.md")):
            with self.assertRaises(ValueError):
                safe_path(self.root, path)

    def test_symlink_output_denied(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.root / "Attachments").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlink権限なし")
        with self.assertRaises(ValueError):
            generate(self.root)


if __name__ == "__main__":
    unittest.main()
