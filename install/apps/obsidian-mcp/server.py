"""ObsidianのMarkdownを検索・取得し、会話から新しいノートを保存する。"""

import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


MAX_BYTES = 256 * 1024


class Vault:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("vaultには既存のディレクトリを指定してください")

    def path(self, relative: str) -> Path:
        parts = relative.replace("\\", "/").split("/")
        if not parts or any(p in ("", ".", "..") or p.startswith(".") or ":" in p for p in parts):
            raise ValueError("隠しファイルや上位ディレクトリを含まない相対パスを指定してください")
        result = self.root.joinpath(*parts)
        if result.suffix.lower() != ".md":
            raise ValueError("対象は.mdファイルです")
        for parent in (result, *result.parents):
            if parent == self.root:
                break
            if parent.is_symlink():
                raise ValueError("シンボリックリンクは対象外です")
        if not result.resolve().is_relative_to(self.root):
            raise ValueError("vault外のファイルは対象外です")
        return result

    def read(self, relative: str) -> str:
        target = self.path(relative)
        if not target.is_file():
            raise ValueError("ノートがありません。searchで相対パスを確認してください")
        if target.stat().st_size > MAX_BYTES:
            raise ValueError("ノートが256KiBを超えています")
        return target.read_text(encoding="utf-8")

    def search(self, query: str, limit: int = 20) -> list[dict]:
        if not query.strip() or not 1 <= limit <= 50:
            raise ValueError("検索語を指定し、件数は1〜50にしてください")
        result = []
        for target in sorted(self.root.rglob("*")):
            if target.suffix.lower() != ".md" or not target.is_file():
                continue
            relative = target.relative_to(self.root).as_posix()
            try:
                text = self.read(relative)
            except (ValueError, OSError, UnicodeError):
                continue
            index = text.casefold().find(query.casefold())
            if index < 0 and query.casefold() not in relative.casefold():
                continue
            start = max(index - 80, 0)
            result.append({"id": relative, "title": target.stem, "excerpt": text[start:start + 320]})
            if len(result) >= limit:
                break
        return result

    def create(self, relative: str, text: str) -> dict:
        target = self.path(relative)
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise ValueError("保存内容は256KiB以下にしてください")
        if not target.parent.is_dir():
            raise ValueError("保存先フォルダがありません。既存のフォルダを指定してください")
        try:
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except FileExistsError:
            raise ValueError("同名ノートがあります。別名で新規保存してください") from None
        return {"id": relative, "bytes": target.stat().st_size}


def build_server(root: Path, port: int = 8765) -> FastMCP:
    vault = Vault(root)
    mcp = FastMCP("obsidian_mcp", host="127.0.0.1", port=port,
                  stateless_http=True, json_response=True)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def search(query: str, limit: int = 20) -> dict:
        """ノートの名前と本文を部分一致で検索する。queryは検索語、limitは1〜50件。"""
        return {"results": vault.search(query, limit)}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def fetch(id: str) -> dict:
        """searchで取得した相対パスidのMarkdown本文を読む。"""
        return {"id": id, "text": vault.read(id)}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                        idempotentHint=False, openWorldHint=False))
    def create_note(path: str, content: str) -> dict:
        """会話の要点を新しい.mdノートとして保存する。pathは既存フォルダ内の相対パス。"""
        return vault.create(path, content)

    return mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    build_server(args.vault, args.port).run(transport=args.transport)
