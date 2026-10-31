"""HTTP経由の本人制限を確認する。GitHub APIだけを公開プロフィールのfixtureに置き換える。"""

import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import httpx2
from cryptography.fernet import Fernet
from fastmcp.server.auth.providers.github import GitHubProvider, GitHubTokenVerifier
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent / "gateway"))
from gateway.gateway import build_gateway


def main(protocol_version=None):
    # GitHub公式API users/parin1213 と users/octocat の公開値を2026-10-31に確認。
    profiles = {
        "dummy-owner": {"id": 1243997, "login": "parin1213"},
        "dummy-other": {"id": 583231, "login": "octocat"},
    }

    def github_api(request):
        identity = profiles.get(request.headers.get("authorization", "").removeprefix("Bearer "))
        if identity is None:
            return httpx2.Response(401)
        if request.url.path == "/user":
            return httpx2.Response(200, json=identity)
        return httpx2.Response(200, json=[], headers={"X-OAuth-Scopes": "read:user"})

    github_client = httpx2.AsyncClient(transport=httpx2.MockTransport(github_api))
    verifier = GitHubTokenVerifier(required_scopes=["read:user"], http_client=github_client)

    async def verify_dummy_token(self, token):
        return await verifier.verify_token(token)

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for name, value in (
            ("github-client-secret", "dummy-client-secret"),
            ("jwt-signing-key", "dummy-signing-key-not-production-long-value"),
            ("storage-encryption-key", Fernet.generate_key().decode()),
        ):
            (root / name).write_text(value)
        os.environ["CREDENTIALS_DIRECTORY"] = str(root)
        config = root / "config.toml"
        config.write_text('base_url="https://example.test"\ngithub_client_id="dummy-client"\ngithub_user_id=1243997\n')
        gateway = build_gateway(config, storage_dir=root / "store")
        with patch.object(GitHubProvider, "load_access_token", verify_dummy_token):
            with TestClient(gateway.http_app(stateless_http=True, json_response=True), base_url="https://example.test") as client:
                def request(token, method, params=None):
                    headers = {"Accept": "application/json, text/event-stream"}
                    if protocol_version:
                        headers["MCP-Protocol-Version"] = protocol_version
                        headers["mcp-method"] = method
                        if params and "name" in params:
                            headers["mcp-name"] = params["name"]
                        params = dict(params or {}, _meta={
                            "io.modelcontextprotocol/protocolVersion": protocol_version,
                            "io.modelcontextprotocol/clientCapabilities": {},
                        })
                    if token:
                        headers["Authorization"] = "Bearer " + token
                    return client.post("/mcp", headers=headers, json={
                        "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {},
                    })

                assert request(None, "tools/list").status_code == 401
                assert request("dummy-invalid", "tools/list").status_code == 401
                owner = request("dummy-owner", "tools/list")
                assert owner.status_code == 200, owner.text
                names = {tool["name"] for tool in owner.json()["result"]["tools"]}
                assert {"search", "fetch", "create_note"} <= names, names
                other = request("dummy-other", "tools/list")
                assert other.json()["result"]["tools"] == [], other.text
                denied = request("dummy-other", "tools/call", {
                    "name": "search", "arguments": {"query": "gateway-verification-no-match-20261031"},
                }).json()
                assert "error" in denied or denied.get("result", {}).get("isError"), denied
                allowed = request("dummy-owner", "tools/call", {
                    "name": "search", "arguments": {"query": "gateway-verification-no-match-20261031"},
                }).json()
                assert "error" not in allowed and not allowed.get("result", {}).get("isError"), allowed
    print("HTTP本人: 検索成功 / 別人: 一覧非表示・実行拒否 / 未認証と無効トークン: 401")


if __name__ == "__main__":
    main()
    main("2026-07-28")
