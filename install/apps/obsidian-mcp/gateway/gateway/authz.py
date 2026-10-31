"""GitHub user ID に基づく認可チェック。"""

from __future__ import annotations

from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import AuthContext
from .diagnostics import logger


def require_github_user(github_user_id: int):
    """検証済みトークンの GitHub user ID が ``github_user_id`` と一致する場合のみ許可。

    GitHubTokenVerifier.verify_token は GitHub API 検証後、
    ``AccessToken.subject`` に ``str(user_data["id"])`` を設定する。
    ここではその検証済みの subject と設定値を比較する。
    """
    expected = str(github_user_id)

    def check(ctx: AuthContext) -> bool:
        logger.info("authorization token_present=%s subject_present=%s owner_match=%s", ctx.token is not None, bool(ctx.token and ctx.token.subject), bool(ctx.token and str(ctx.token.subject) == expected))
        if ctx.token is None:
            return False
        if str(ctx.token.subject) != expected:
            raise AuthorizationError("許可された GitHub user ID ではありません")
        return True

    return check
