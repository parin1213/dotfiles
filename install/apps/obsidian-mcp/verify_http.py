"""実際のMCPクライアント（streamable HTTP）から検索・保存・取得と入力制限を検証する。"""

import asyncio
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


SERVER = Path(__file__).with_name("server.py")
TOOL_NAMES = {"search", "fetch", "create_note"}
MAX_BYTES = 256 * 1024


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.1)


def tool_payload(result) -> dict:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for block in result.content or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError(f"ツール結果をJSONとして解析できない: {result!r}")


async def verify() -> None:
    with tempfile.TemporaryDirectory(prefix="obsidian-mcp-verify-") as directory:
        root = Path(directory)
        (root / "ラズパイ実測メモ.md").write_text(
            "# ラズパイ実測メモ\nARM64 Linux。空きディスク39GB。\n",
            encoding="utf-8",
        )
        (root / ".obsidian").mkdir()
        (root / ".obsidian" / "非公開設定.md").write_text("設定は検索対象外", encoding="utf-8")

        port = free_port()
        proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--vault", str(root),
             "--transport", "streamable-http", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            await wait_port(port)
            async with streamablehttp_client(url=f"http://127.0.0.1:{port}/mcp") as stream:
                read, write = stream[0], stream[1]
                async with ClientSession(read, write) as session:
                    init = await session.initialize()
                    assert init.serverInfo.name == "obsidian_mcp"

                    tools = (await session.list_tools()).tools
                    assert {tool.name for tool in tools} == TOOL_NAMES, f"tools={tools}"
                    by_name = {tool.name: tool for tool in tools}
                    assert by_name["search"].annotations.readOnlyHint
                    assert not by_name["create_note"].annotations.readOnlyHint

                    search = await session.call_tool("search", {"query": "39GB"})
                    assert not search.isError
                    found = tool_payload(search)["results"]
                    assert len(found) >= 1
                    assert found[0]["id"] == "ラズパイ実測メモ.md"
                    assert found[0]["title"] == "ラズパイ実測メモ"
                    assert "39GB" in found[0]["excerpt"]
                    assert (root / "ラズパイ実測メモ.md").is_file()
                    assert "39GB" in (root / "ラズパイ実測メモ.md").read_text(encoding="utf-8")

                    content = "# 検証\nMCPからの保存を確認。\n"
                    created = await session.call_tool("create_note", {"path": "チャット保存.md", "content": content})
                    assert not created.isError
                    created_payload = tool_payload(created)
                    assert created_payload["id"] == "チャット保存.md"
                    assert created_payload["bytes"] == len(content.encode("utf-8"))
                    real_file = root / "チャット保存.md"
                    assert real_file.is_file()
                    assert real_file.read_text(encoding="utf-8") == content

                    fetched = await session.call_tool("fetch", {"id": "チャット保存.md"})
                    assert not fetched.isError
                    fetched_payload = tool_payload(fetched)
                    assert fetched_payload["id"] == "チャット保存.md"
                    assert fetched_payload["text"] == content

                    duplicate = await session.call_tool("create_note", {"path": "チャット保存.md", "content": "上書き"})
                    assert duplicate.isError
                    assert real_file.read_text(encoding="utf-8") == content

                    oversized = await session.call_tool(
                        "create_note",
                        {"path": "オーバーノート.md", "content": "# オーバー\n" + "a" * (MAX_BYTES + 1)},
                    )
                    assert oversized.isError
                    assert not (root / "オーバーノート.md").exists()
                    (root / "大きなノート.md").write_bytes(b"a" * (MAX_BYTES + 1))
                    too_large = await session.call_tool("fetch", {"id": "大きなノート.md"})
                    assert too_large.isError

                    outside_dir = Path(tempfile.mkdtemp(prefix="obsidian-mcp-outside-"))
                    linked = None
                    try:
                        (outside_dir / "outside.md").write_text("外部ノート", encoding="utf-8")
                        linked = root / "外部リンク.md"
                        linked.symlink_to(outside_dir / "outside.md")
                        rejected = await session.call_tool("fetch", {"id": "外部リンク.md"})
                        assert rejected.isError
                        (root / "external").symlink_to(outside_dir, target_is_directory=True)
                        rejected_write = await session.call_tool("create_note", {"path": "external/new.md", "content": "外部"})
                        assert rejected_write.isError
                        assert not (outside_dir / "new.md").exists()
                    finally:
                        if linked is not None and (linked.is_symlink() or linked.exists()):
                            linked.unlink()
                        shutil.rmtree(outside_dir, ignore_errors=True)

                    rejections = [
                        ("create_note", {"path": "../outside.md", "content": "外部"}, "../外部パス"),
                        ("create_note", {"path": ".obsidian/隠し.md", "content": "隠し"}, "隠しパス"),
                        ("create_note", {"path": "note.txt", "content": "拡張子"}, "拡張子"),
                        ("fetch", {"id": "../outside.md"}, "../外部パス(fetch)"),
                        ("fetch", {"id": ".obsidian/非公開設定.md"}, "隠しパス(fetch)"),
                        ("fetch", {"id": "note.txt"}, "拡張子(fetch)"),
                    ]
                    for tool_name, args, label in rejections:
                        rejected = await session.call_tool(tool_name, args)
                        assert rejected.isError, f"{label}: {rejected!r}"
                    hidden = await session.call_tool("search", {"query": "設定は検索対象外"})
                    assert not hidden.isError and tool_payload(hidden)["results"] == []
                    print(json.dumps({"HTTP初期化": "成功", "検索": "成功", "新規保存と実ファイル": "成功",
                        "取得": "成功", "上書きとサイズ制限": "成功", "隠しパスと外部リンク拒否": "成功"}, ensure_ascii=False))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)


if __name__ == "__main__":
    asyncio.run(verify())
