"""架空の一時Vaultで、stdioとHTTPの健康記録ツールを検証する。"""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from verify_http import free_port, wait_port, tool_payload, SERVER


@asynccontextmanager
async def connect(root, transport):
    if transport == "stdio":
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER), "--vault", str(root)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        port = free_port()
        process = subprocess.Popen([sys.executable, str(SERVER), "--vault", str(root), "--transport", "streamable-http", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            await wait_port(port)
            async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        finally:
            process.terminate()
            process.wait(timeout=10)


async def verify(transport):
    with tempfile.TemporaryDirectory(prefix="health-mcp-") as temporary:
        root = Path(temporary)
        (root / "ログ").mkdir()
        (root / ".git").mkdir()
        (root / "ログ/2026-11-06_既存の食事.md").write_text("# 既存の食事\n検証用の記録", encoding="utf-8")
        async with connect(root, transport) as session:
            async def call(name, arguments=None, error=False):
                result = await session.call_tool(name, arguments or {})
                assert bool(result.isError) == error, name
                return tool_payload(result) if not error else None

            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert tools["health_day"].annotations.readOnlyHint
            assert tools["health_status"].annotations.readOnlyHint
            assert not tools["health_record"].annotations.readOnlyHint
            assert tools["health_record"].annotations.idempotentHint
            assert (await call("health_status"))["automatic_steps"] is False
            assert (await call("health_day", {"date": "2026-11-06"}))["records"] == []
            base = {"record_id": str(uuid4()), "kind": "meal", "occurred_at": "2026-11-06T12:00:00+09:00", "text": "検証用の短文", "value": None}
            saved = await call("health_record", base)
            assert (root / saved["id"]).is_file()
            assert (await call("health_record", base))["id"] == saved["id"]
            assert len(list((root / "Attachments/health/records").glob("*_健康記録_*"))) == 1
            await call("health_record", base | {"text": "別の内容"}, error=True)
            fetched = await call("fetch", {"id": saved["id"]})
            assert "value: null" in fetched["text"]
            assert any(r["id"] == saved["id"] for r in (await call("search", {"query": base["record_id"]}))["results"])
            steps = base | {"record_id": str(uuid4()), "kind": "steps", "text": "", "value": 0}
            await call("health_record", steps)
            await call("health_record", steps | {"record_id": str(uuid4()), "occurred_at": "2026-11-06T18:00:00+09:00", "value": 400})
            daily = await call("health_day", {"date": "2026-11-06"})
            assert len(daily["records"]) == 3
            assert next(r for r in daily["records"] if r["kind"] == "meal")["value"] is None
            assert daily["latest_observations"]["steps"][0]["value"] == 400
            assert daily["complete_day"] is False
            for invalid in (base | {"record_id": "../escape"}, base | {"kind": "weight", "value": 0}, base | {"kind": "steps", "value": -1}, base | {"occurred_at": "2026-11-06T12:00:00"}):
                await call("health_record", invalid, error=True)
            await call("health_day", {"date": "../2026-11-06"}, error=True)
            (root / ".git/obsidian-vault-sync.lock").mkdir()
            await call("health_record", base | {"record_id": str(uuid4())}, error=True)
            assert (root / ".git/obsidian-vault-sync.lock").is_dir()
            (root / ".git/obsidian-vault-sync.lock").rmdir()
            invalid_path = root / f"ログ/2026-11-06_健康記録_1800_{uuid4()}.md"
            invalid_path.write_text("形式の違う記録", encoding="utf-8")
            daily = await call("health_day", {"date": "2026-11-06"})
            assert daily["skipped_invalid"] == 1
            assert len(daily["records"]) == 3
            # 同時刻の異なる観測を勝手に1つへ決めない。
            await call("health_record", steps | {"record_id": str(uuid4()), "occurred_at": "2026-11-06T18:00:00+09:00", "value": None, "text": "歩数不明"})
            assert len((await call("health_day", {"date": "2026-11-06"}))["latest_observations"]["steps"]) == 2
            # 別日のAPI観測は取得時刻と対象日を分け、Google Fit由来と偽らない。
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "health-log"))
            from datetime import date, datetime, timezone
            from google_steps import GoogleSteps, civil, sync_day
            import health
            def fixture(method, url, payload, token):
                if method == "GET": return {"healthUserId": "test-user"}
                return {"rollupDataPoints": [{"civilStartTime": civil(date(2026, 11, 5)), "civilEndTime": civil(date(2026, 11, 6)), "steps": {"countSum": "1234"}}]}
            client = GoogleSteps("fixture-token", "test-user", transport=fixture, now=lambda: datetime(2026, 11, 7, 1, tzinfo=timezone.utc))
            imported = sync_day(client, health.storage_module().Store(root), "2026-11-05")
            external = await call("health_day", {"date": "2026-11-05"})
            assert len(external["records"]) == 1, external
            observation = external["records"][0]
            assert observation["value"] == 1234 and observation["source"] == "google_health"
            assert observation["window_date"] == "2026-11-05" and observation["occurred_at"].startswith("2026-11-07")
            assert observation["fit_sync_verified"] is False
            assert (await call("health_status"))["automatic_steps"] is False
            assert "fixture-token" not in (await call("fetch", {"id": imported["path"]}))["text"]
        print(json.dumps({"transport": transport, "健康記録": "成功", "欠測と0": "区別", "再送": "重複なし", "歩数": "加算しない", "既存search/fetch": "成功", "入力と同期ロック": "拒否確認"}, ensure_ascii=False))


async def main():
    for transport in ("stdio", "http"):
        await verify(transport)


if __name__ == "__main__":
    asyncio.run(main())
