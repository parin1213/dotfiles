"""実Vaultを変更せず、健康表示の集計・欠測・出力境界を確認。"""
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
from dashboard import generate, parse_meals, parse_weights, parse_snapshot, load_steps, load_sleep, safe_path

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


def sleep_snapshot(value, stamp="2026-11-08T08:00:00+00:00", day="2026-11-08", state="present"):
    return (f'---\nkind: sleep\ndate: {day}\nwindow_date: "{day}"\n'
            f'occurred_at: {stamp}\nsource: google_health\nvalue: {json.dumps(value)}\n'
            f'missing_state: {json.dumps(state)}\nsleep_sessions: []\n---\n')


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

    def test_single_calorie_value_display_preserves_ranges(self):
        self.note("ログ/食事ログ.md", MEAL)
        generate(self.root, today=date(2026, 11, 8))
        body = (self.root / "ログ/健康ダッシュボード.md").read_text(encoding="utf-8")
        self.assertIn("1961（記録分）", body)
        self.assertNotIn("1961〜1961", body)
        self.assertIn("1490〜1590", body)
        self.note("ログ/食事ログ.md", MEAL.replace("約1,490〜1,590", "2,029"))
        generate(self.root, today=date(2026, 11, 8))
        body = (self.root / "ログ/健康ダッシュボード.md").read_text(encoding="utf-8")
        self.assertIn("記録分 2029 kcal", body)
        self.assertIn("2029（部分記録）", body)
        self.assertNotIn("2029〜2029", body)

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

    def test_sleep_and_steps_are_independent(self):
        self.note("ログ/2026-11-08_健康記録_0800_steps.md", snapshot(7025, day="2026-11-08"))
        self.note("Attachments/health/records/2026-11-08_健康記録_0800_sleep.md", sleep_snapshot(450))
        self.assertEqual(load_steps(self.root)[0]["value"], 7025)
        self.assertEqual(load_sleep(self.root)[0]["value"], 450)
        self.assertIsNone(parse_snapshot(sleep_snapshot(450)))
        self.assertIsNone(parse_snapshot(snapshot(7025), "sleep"))

    def test_latest_sleep_replaces_not_sums_across_locations(self):
        self.note("ログ/2026-11-08_健康記録_0700_sleep.md", sleep_snapshot(420, stamp="2026-11-08T07:00:00+00:00"))
        self.note("Attachments/health/records/2026-11-08_健康記録_0800_sleep.md", sleep_snapshot(450))
        records = load_sleep(self.root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["value"], 450)

    def test_sleep_uses_wake_date_not_observation_date(self):
        body = sleep_snapshot(450, stamp="2026-11-09T08:00:00+00:00").replace("date: 2026-11-08", "date: 2026-11-09", 1)
        self.assertEqual(parse_snapshot(body, "sleep")["date"], date(2026, 11, 8))

    def test_sleep_missing_replaces_value_and_preserves_zero(self):
        self.note("ログ/2026-11-08_健康記録_0700_sleep.md", sleep_snapshot(420, stamp="2026-11-08T07:00:00+00:00"))
        self.note("ログ/2026-11-08_健康記録_0800_sleep.md", sleep_snapshot(None, state="no_sessions"))
        record = load_sleep(self.root)[0]
        self.assertIsNone(record["value"])
        self.assertEqual(record["missing_state"], "no_sessions")
        self.assertEqual(parse_snapshot(sleep_snapshot(0), "sleep")["value"], 0)
        for state in ("no_sessions", "summary_missing", "overlapping_sessions"):
            with self.subTest(state=state):
                item = parse_snapshot(sleep_snapshot(450, state=state), "sleep")
                self.assertIsNone(item["value"])
                self.assertEqual(item["missing_state"], state)

    def test_same_time_sleep_conflict_is_unknown(self):
        self.note("ログ/2026-11-08_健康記録_0800_a.md", sleep_snapshot(420))
        self.note("ログ/2026-11-08_健康記録_0800_b.md", sleep_snapshot(450))
        self.note("Attachments/health/records/2026-11-08_健康記録_0800_c.md", sleep_snapshot(450))
        record = load_sleep(self.root)[0]
        self.assertIsNone(record["value"])
        self.assertEqual(record["missing_state"], "conflict")

    def test_invalid_sleep_ignored(self):
        for value in (True, -1, float("nan"), float("inf"), "450"):
            with self.subTest(value=value):
                self.assertIsNone(parse_snapshot(sleep_snapshot(value), "sleep"))
        self.assertIsNone(parse_snapshot(sleep_snapshot(450).replace("+00:00", ""), "sleep"))
        self.assertIsNone(parse_snapshot(sleep_snapshot(None, state="unknown"), "sleep"))

    def test_sleep_hours_chart_table_freshness_and_missing(self):
        self.note("Attachments/health/records/2026-11-06_健康記録_0800_a.md", sleep_snapshot(450, day="2026-11-06"))
        self.note("Attachments/health/records/2026-11-07_健康記録_0800_b.md", sleep_snapshot(0, day="2026-11-07"))
        self.note("Attachments/health/records/2026-11-08_健康記録_0900_c.md", sleep_snapshot(None, stamp="2026-11-08T09:00:00+00:00", state="no_sessions"))
        result = generate(self.root, today=date(2026, 11, 8))
        self.assertEqual(result["sleep_days"], 3)
        content = (self.root / "ログ/健康ダッシュボード.md").read_text(encoding="utf-8")
        self.assertIn("**睡眠の最終取得日時**：2026-11-08 18:00:00 JST", content)
        self.assertIn("日付（睡眠は起床日）", content)
        self.assertIn("| 2026-11-06 | 未記録 | 未記録 | 7.5 |", content)
        self.assertIn("| 2026-11-07 | 未記録 | 未記録 | 0 |", content)
        self.assertIn("| 2026-11-08 | 未記録 | 未記録 | 欠測（睡眠記録なし） |", content)
        self.assertIn("0時間ではありません", content)
        self.assertIn("![[Attachments/health/sleep.svg]]", content)
        svg = (self.root / "Attachments/health/sleep.svg").read_text(encoding="utf-8")
        ElementTree.fromstring(svg)
        self.assertIn(">7.5</text>", svg)
        self.assertIn(">欠測</text>", svg)
        self.assertNotIn(">450</text>", svg)
        self.assertEqual(generate(self.root, today=date(2026, 11, 8))["changed"], [])

    def test_sleep_chart_only_uses_recent_dates(self):
        for day in ("2026-10-25", "2026-10-26", "2026-11-08", "2026-11-09"):
            self.note(f"Attachments/health/records/{day}_健康記録_0800_a.md", sleep_snapshot(450, day=day))
        generate(self.root, today=date(2026, 11, 8))
        svg = (self.root / "Attachments/health/sleep.svg").read_text(encoding="utf-8")
        self.assertIn(">10/26</text>", svg)
        self.assertIn(">11/08</text>", svg)
        self.assertNotIn(">10/25</text>", svg)
        self.assertNotIn(">11/09</text>", svg)

    def test_sleep_missing_reasons_are_visible(self):
        for day, state in (("2026-11-06", "summary_missing"), ("2026-11-07", "overlapping_sessions")):
            self.note(f"Attachments/health/records/{day}_健康記録_0800_a.md", sleep_snapshot(None, day=day, state=state))
        generate(self.root, today=date(2026, 11, 8))
        content = (self.root / "ログ/健康ダッシュボード.md").read_text(encoding="utf-8")
        self.assertIn("欠測（時間不明）", content)
        self.assertIn("欠測（記録の重複）", content)

    def test_generation_is_idempotent_valid_svg_and_stale(self):
        self.note("ログ/食事ログ.md", MEAL)
        self.note("ログ/体重記録.md", WEIGHT)
        self.note("ログ/2026-11-08_健康記録_0819_a.md", snapshot("null", day="2026-11-08"))
        result = generate(self.root, today=date(2026, 11, 8))
        self.assertEqual(len(result["changed"]), 5)
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
        self.assertEqual(result["sleep_days"], 0)

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




class SyncOutputCoverageTests(unittest.TestCase):
    def test_every_generated_file_is_staged_on_both_platforms(self):
        repo = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as tmp:
            result = generate(tmp)
            for name in ("obsidian-vault-sync.ps1", "executable_obsidian-vault-sync"):
                script = (repo / "home/dot_local/bin" / name).read_text(encoding="utf-8")
                for output in result["changed"]:
                    if output.endswith(".svg"):
                        self.assertIn('"' + output + '"', script, (name, output))


if __name__ == "__main__":
    unittest.main()
