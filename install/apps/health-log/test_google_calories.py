"""総消費の形式・日付・重複・安全な同期を架空データで検証する。"""
from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from google_calories import GoogleCalories, FAMILY, ENDPOINT, request_calories_json, save_snapshot
from google_steps import BASE, StepsError, civil
from server import Store

class CaloriesTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,11,16,15,tzinfo=timezone.utc)
        self.calls=[]
        self.response={"rollupDataPoints":[{"civilStartTime":civil(date(2026,11,16)),
            "civilEndTime":civil(date(2026,11,17)), "totalCalories":{"kcalSum":2345.75}}]}
        def api(method,url,payload,token):
            self.calls.append((method,url,payload))
            return {"healthUserId":"fixture-user"} if method=="GET" else self.response
        self.client=GoogleCalories("fixture-token","fixture-user",transport=api,now=lambda:self.now)
    def test_snapshot_jst_and_units(self):
        snap=self.client.fetch_day("2026-11-16","Asia/Tokyo")
        self.assertTrue(snap.day_elapsed)
        self.assertEqual(snap.kcal,2345.75)
        self.assertEqual(self.calls[-1][2]["dataSourceFamily"],FAMILY)
        self.now=self.now.replace(hour=14)
        self.assertFalse(self.client.fetch_day("2026-11-16","Asia/Tokyo").day_elapsed)
    def test_missing_zero_and_invalid(self):
        point=self.response["rollupDataPoints"][0]
        point["totalCalories"]={"kcalSum":0}
        self.assertEqual(self.client.fetch_day("2026-11-16","Asia/Tokyo").kcal,0)
        point.pop("totalCalories")
        self.assertIsNone(self.client.fetch_day("2026-11-16","Asia/Tokyo").kcal)
        self.response={}
        self.assertEqual(self.client.fetch_day("2026-11-16","Asia/Tokyo").missing_state,"no_window")
    def test_bad_value(self):
        for value in [True,"2400",-1,20001,float("nan"),float("inf")]:
            self.response["rollupDataPoints"][0]["totalCalories"]["kcalSum"]=value
            with self.assertRaises(StepsError): self.client.fetch_day("2026-11-16","Asia/Tokyo")
    def test_wrong_account_window_pagination_future(self):
        other=GoogleCalories("fixture-token","other",transport=lambda *a:{"healthUserId":"fixture-user"},now=lambda:self.now)
        with self.assertRaises(StepsError): other.fetch_day("2026-11-16","Asia/Tokyo")
        self.response["nextPageToken"]="more"
        with self.assertRaises(StepsError): self.client.fetch_day("2026-11-16","Asia/Tokyo")
        self.response.pop("nextPageToken")
        with self.assertRaises(StepsError): self.client.fetch_day("2026-11-15","Asia/Tokyo")
        with self.assertRaises(StepsError): self.client.fetch_day("2026-11-18","Asia/Tokyo")
    def test_save_dedup_transition_and_no_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"ログ").mkdir(); store=Store(root)
            self.now=self.now.replace(hour=14)
            snap=self.client.fetch_day("2026-11-16","Asia/Tokyo")
            first=save_snapshot(store,snap)
            self.assertTrue(save_snapshot(store,replace(snap,observed_at="2026-11-16T14:30:00+00:00"))["unchanged"])
            self.now=self.now.replace(hour=15)
            save_snapshot(store,self.client.fetch_day("2026-11-16","Asia/Tokyo"))
            files=list(store.folder.glob("*.md"))
            self.assertEqual(len(files),2)
            text="".join(p.read_text() for p in files)
            self.assertNotIn("fixture-user",text);self.assertNotIn("fixture-token",text)
            self.assertIn('unit: "kcal"',text)
            with self.assertRaises(ValueError):
                store.save({"id":"9f768f05-6148-4371-834a-54c2b74b1b76","kind":"total_calories",
                    "occurred_at":"2026-11-16T14:00:00+00:00","value":2000})
    def test_network_errors_are_redacted_and_other_endpoints_blocked(self):
        with self.assertRaises(StepsError):
            request_calories_json("POST",BASE+"users/me/dataTypes/steps/dataPoints:dailyRollUp",{},"fixture-token")
        for status in [400,401,403,429,500]:
            with patch("google_calories.build_opener") as opener:
                opener.return_value.open.side_effect=HTTPError(ENDPOINT,status,"private fixture-token",{},None)
                with self.assertRaises(StepsError) as caught:
                    request_calories_json("POST",ENDPOINT,{},"fixture-token")
                self.assertNotIn("fixture-token",str(caught.exception))


class CaloriesSyncTests(unittest.TestCase):
    def setUp(self):
        import test_google_sync
        self.fixture=test_google_sync.SyncTests()
        self.fixture.setUp()
        # Synchronization is pinned to the user's Japanese date boundary.
        self.fixture.run_sync=lambda **kw: __import__("google_sync").run_sync(
            self.fixture.bundle,self.fixture.store,zone_name="Asia/Tokyo",
            expected_account="test@example.invalid",expected_project="test-health-project",
            now=self.fixture.bundle_time if hasattr(self.fixture,"bundle_time") else test_google_sync.NOW,
            grant=self.fixture.grant,api=self.fixture.api,**kw)
    def tearDown(self):
        self.fixture.tearDown()
    def api(self,method,url,body,token):
        if method=="GET": return {"healthUserId":"fixture-user"}
        return {"rollupDataPoints":[{"civilStartTime":body["range"]["start"],"civilEndTime":body["range"]["end"],"totalCalories":{"kcalSum":1800.25}}]}
    def test_sync_and_mcp_saved_value(self):
        result=self.fixture.run_sync(include_calories=True,calories_api=self.api)
        self.assertEqual(result["calories_status"],"success")
        self.assertEqual(result["calories_completed_day_count"],2)
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"obsidian-mcp"))
        import health
        from types import SimpleNamespace
        root=self.fixture.root
        vault=SimpleNamespace(root=root,read=lambda name:(root/name).read_text())
        data=health.day(vault,"2026-11-05")
        latest=data["latest_observations"]["total_calories"]
        self.assertEqual(len(latest),1)
        self.assertEqual(latest[0]["value"],1800.25)
        self.assertFalse(latest[0]["coverage_verified"])
        self.assertEqual(data["skipped_invalid"],0)
        self.fixture.run_sync(include_calories=True,calories_api=self.api)
        self.assertEqual(len(list(self.fixture.store.folder.glob("*.md"))),4)
    def test_calories_failure_preserves_steps(self):
        result=self.fixture.run_sync(include_calories=True,calories_api=lambda *a:{"healthUserId":"wrong"})
        self.assertEqual(result["status"],"error")
        self.assertEqual(result["steps_status"],"success")
        self.assertEqual(result["calories_status"],"error")
        self.assertEqual(len(list(self.fixture.store.folder.glob("*.md"))),2)
    def test_partial_response_does_not_save_any_calories(self):
        count=[0]
        def api(method,url,body,token):
            if method=="POST":
                count[0]+=1
                if count[0]==2: raise StepsError("fixture-private")
            return self.api(method,url,body,token)
        result=self.fixture.run_sync(include_calories=True,calories_api=api)
        self.assertEqual(result["calories_completed_day_count"],0)
        self.assertNotIn("fixture-private",str(result))
        self.assertEqual(len(list(self.fixture.store.folder.glob("*.md"))),2)
