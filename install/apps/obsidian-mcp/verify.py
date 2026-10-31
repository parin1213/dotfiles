"""実際のMCPクライアントから検索・保存・取得と入力制限を検証する。"""

import asyncio
import json
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def verify():
    with tempfile.TemporaryDirectory(prefix="obsidian-mcp-") as directory:
        root = Path(directory)
        (root / "ラズパイ確認.md").write_text("# SSH確認\nraspi4 はARM64 Linux。空きディスク39GB。\n", encoding="utf-8")
        (root / ".obsidian").mkdir()
        (root / ".obsidian" / "非公開設定.md").write_text("設定は検索対象外", encoding="utf-8")
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).with_name("server.py")), "--vault", str(root)])
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert {tool.name for tool in tools} == {"search", "fetch", "create_note"}
                assert next(t for t in tools if t.name == "search").annotations.readOnlyHint
                assert not next(t for t in tools if t.name == "create_note").annotations.readOnlyHint
                result = await session.call_tool("search", {"query": "39GB"})
                assert not result.isError and "ラズパイ確認.md" in str(result)
                created = await session.call_tool("create_note", {"path": "チャット保存.md", "content": "# 検証\nMCPからの保存を確認。\n"})
                assert not created.isError
                assert (root / "チャット保存.md").read_text(encoding="utf-8") == "# 検証\nMCPからの保存を確認。\n"
                fetched = await session.call_tool("fetch", {"id": "チャット保存.md"})
                assert not fetched.isError and "MCPからの保存を確認" in str(fetched)
                duplicate = await session.call_tool("create_note", {"path": "チャット保存.md", "content": "上書き"})
                assert duplicate.isError
                for path in ("../outside.md", ".obsidian/非公開設定.md", "note.txt", "C:/outside.md"):
                    rejected = await session.call_tool("fetch", {"id": path})
                    assert rejected.isError, path
                hidden = await session.call_tool("search", {"query": "設定は検索対象外"})
                assert not hidden.isError and "非公開設定.md" not in str(hidden)
                print(json.dumps({"検索": "成功", "新規保存": "成功", "実ファイル確認": "成功",
                    "取得": "成功", "上書き拒否": "成功", "vault外と隠しファイル拒否": "成功"}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(verify())
