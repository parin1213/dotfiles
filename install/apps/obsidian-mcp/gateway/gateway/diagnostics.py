"""秘密値やノート本文を含めず、ツール一覧の成否だけを記録する。"""
import logging
from pathlib import Path
from fastmcp.server.middleware import Middleware
from fastmcp.server.auth.providers.github import GitHubProvider

logger = logging.getLogger("obsidian_gateway_diagnostics")


class DiagnosticGitHubProvider(GitHubProvider):
    async def load_access_token(self, token):
        result = await super().load_access_token(token)
        logger.info("bearer_verification accepted=%s subject_present=%s", result is not None, bool(result and result.subject))
        return result


def configure():
    directory = Path.home() / ".local/state/obsidian-mcp"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    handler = logging.FileHandler(directory / "gateway-diagnostics.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class ToolDiagnostics(Middleware):
    async def on_list_tools(self, context, call_next):
        try:
            tools = await call_next(context)
        except Exception as error:
            logger.info("tools_list_error class=%s", type(error).__name__)
            raise
        logger.info("tools_list count=%d", len(tools))
        return tools
