"""
Lazy MCP client from AgentSummary only. Mirrors agent0-ts mcp-summary-client.ts.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, TYPE_CHECKING, Union

from .mcp_client import create_mcp_handle

if TYPE_CHECKING:
    from .mcp_types import MCPAuthOptions, MCPClientOptions
    from .models import AgentSummary


class SDKLikeMCP(Protocol):
    """Minimal SDK surface for x402 deps."""

    def getX402RequestDeps(self):  # noqa: N802
        ...


class MCPClientFromSummary:
    """Resolve MCP endpoint from AgentSummary.mcp on first use."""

    def __init__(
        self,
        sdk: SDKLikeMCP,
        summary: "AgentSummary",
        options: Optional[Dict[str, Any]] = None,
    ):
        self._sdk = sdk
        self._summary = summary
        self._options: Dict[str, Any] = dict(options or {})
        self._client: Optional[Any] = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        endpoint = getattr(self._summary, "mcp", None)
        if not endpoint or not (
            str(endpoint).startswith("http://") or str(endpoint).startswith("https://")
        ):
            raise RuntimeError("Agent summary has no MCP endpoint")
        self._client = create_mcp_handle(
            str(endpoint),
            self._options,
            getattr(self._sdk, "getX402RequestDeps", lambda: None)(),
        )
        return self._client

    @property
    def prompts(self) -> Any:
        return self._ensure_client().prompts

    @property
    def resources(self) -> Any:
        return self._ensure_client().resources

    @property
    def tools(self) -> Any:
        return self._ensure_client().tools

    def listTools(self, options: Optional["MCPAuthOptions"] = None) -> Any:
        return self._ensure_client().listTools(options)

    def call(
        self,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        options: Optional["MCPAuthOptions"] = None,
    ) -> Any:
        return self._ensure_client().call(name, args, options)