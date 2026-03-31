"""
MCP Streamable HTTP JSON-RPC client with optional x402. Mirrors agent0-ts src/core/mcp-client.ts.
All methods are synchronous (blocking).
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .x402_request import request_with_x402
from .x402_types import X402RequiredResponse, isX402Required

from .mcp_types import (
    MCPAuthOptions,
    MCPClientInfo,
    MCPClientOptions,
    MCPInitializeResult,
    MCPPrompt,
    MCPPromptGetResult,
    MCPResource,
    MCPResourceTemplate,
    MCPTool,
)

if TYPE_CHECKING:
    from .x402_request import X402RequestDeps

DEFAULT_PROTOCOL_VERSION = "2025-06-18"
SESSION_HEADER = "Mcp-Session-Id"

_IDENTIFIER_SAFE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _is_identifier_safe(name: str) -> bool:
    return bool(_IDENTIFIER_SAFE.match(name))


def _normalize_bearer(credential: Optional[str]) -> Optional[str]:
    if not credential:
        return None
    trimmed = credential.strip()
    if not trimmed:
        return None
    if trimmed.lower().startswith("bearer "):
        return trimmed
    return f"Bearer {trimmed}"


def _parse_sse_json(text: str) -> Optional[Dict[str, Any]]:
    for line in text.split("\n"):
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            continue
    return None


def _extract_json_rpc_body(text: str, content_type: str) -> Dict[str, Any]:
    trimmed = text.strip()
    if not trimmed:
        raise RuntimeError("MCP server returned empty response")
    ct_lower = content_type.lower()
    if "text/event-stream" in ct_lower:
        parsed = _parse_sse_json(trimmed)
        if not parsed:
            raise RuntimeError("MCP server returned invalid SSE JSON-RPC response")
        return parsed
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        parsed = _parse_sse_json(trimmed)
        if parsed:
            return parsed
        raise RuntimeError("MCP server returned non-JSON response") from None


def _parse_json_rpc_result(data: Dict[str, Any], method: str) -> Any:
    err = data.get("error")
    if err and isinstance(err, dict):
        raise RuntimeError(f"MCP {method} failed: {err.get('message') or err.get('code') or 'unknown error'}")
    if "result" not in data:
        raise RuntimeError(f"MCP {method} failed: missing JSON-RPC result")
    return data["result"]


def _response_header(resp: Any, name: str) -> Optional[str]:
    h = getattr(resp, "headers", None)
    if not h:
        return None
    if hasattr(h, "get"):
        v = h.get(name)
        if v is not None:
            return str(v)
    try:
        for k, v in h.items():
            if str(k).lower() == name.lower():
                return str(v)
    except Exception:
        pass
    return None


def _response_status(resp: Any) -> int:
    return int(getattr(resp, "status_code", None) or getattr(resp, "status", None) or 0)


def _response_text(resp: Any) -> str:
    t = getattr(resp, "text", None)
    if t is not None:
        return str(t)
    content = getattr(resp, "content", None)
    if content is not None:
        return content.decode("utf-8", errors="replace")
    return ""


def _cast_x402(result: X402RequiredResponse) -> X402RequiredResponse:
    return result


class MCPClient:
    """MCP client over HTTP POST JSON-RPC."""

    def __init__(
        self,
        endpoint: str,
        options: Optional[MCPClientOptions] = None,
        x402_deps: Optional["X402RequestDeps"] = None,
    ):
        self._endpoint = endpoint
        self._options: Dict[str, Any] = dict(options or {})
        self._x402_deps = x402_deps
        self._initialized = False
        self._session_id: Optional[str] = self._options.get("sessionId")
        self._protocol_version: str = (
            self._options.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
        )
        self._server_caps: Optional[Dict[str, Any]] = None
        self._tools_cache: Optional[List[MCPTool]] = None
        self._dynamic_tools: Dict[str, Callable[..., Any]] = {}

    def _base_headers(self, auth: Optional[MCPAuthOptions] = None) -> Dict[str, str]:
        opts = self._options
        cred = None
        if auth and auth.get("credential"):
            cred = auth.get("credential")
        elif opts.get("credential"):
            cred = opts.get("credential")
        bearer = _normalize_bearer(cred)
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self._protocol_version,
        }
        headers.update(opts.get("headers") or {})
        if auth and auth.get("headers"):
            headers.update(auth["headers"])
        if bearer:
            headers["Authorization"] = bearer
        if self._session_id:
            headers[SESSION_HEADER] = self._session_id
        return headers

    def _post_json_rpc(
        self,
        method: str,
        params: Optional[Dict[str, Any]],
        auth: Optional[MCPAuthOptions] = None,
    ) -> Any:
        body: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": f"{method}-{uuid.uuid4().hex[:12]}",
            "method": method,
        }
        if params is not None:
            body["params"] = params
        headers = self._base_headers(auth)
        body_str = json.dumps(body)

        def parse_response(res: Any) -> Any:
            new_session = _response_header(res, SESSION_HEADER)
            if new_session:
                self._session_id = new_session
            status = _response_status(res)
            if self._session_id and status == 404:
                self._initialized = False
                self._session_id = None
                raise RuntimeError("MCP session expired")
            text = _response_text(res)
            ct = _response_header(res, "content-type") or ""
            data = _extract_json_rpc_body(text, ct)
            return _parse_json_rpc_result(data, method)

        if self._x402_deps is not None:
            result = request_with_x402(
                {
                    "url": self._endpoint,
                    "method": "POST",
                    "headers": headers,
                    "body": body_str,
                    "parseResponse": parse_response,
                },
                self._x402_deps,
            )
            if isX402Required(result):
                return result
            return result

        import requests

        res = requests.request("POST", self._endpoint, headers=headers, data=body_str)
        new_session = _response_header(res, SESSION_HEADER)
        if new_session:
            self._session_id = new_session
        status = _response_status(res)
        if self._session_id and status == 404:
            self._initialized = False
            self._session_id = None
            raise RuntimeError("MCP session expired")
        if not res.ok:
            raise RuntimeError(f"MCP {method} failed: HTTP {status}")
        text = _response_text(res)
        ct = _response_header(res, "content-type") or ""
        data = _extract_json_rpc_body(text, ct)
        return _parse_json_rpc_result(data, method)

    def _ensure_initialized(self, auth: Optional[MCPAuthOptions] = None) -> Optional[X402RequiredResponse]:
        if self._initialized:
            return None
        client_info: MCPClientInfo = self._options.get("clientInfo") or {
            "name": "agent0-py",
            "version": "1.0.0",
        }
        init_result = self._post_json_rpc(
            "initialize",
            {
                "protocolVersion": self._protocol_version,
                "capabilities": {},
                "clientInfo": client_info,
            },
            auth,
        )
        if isX402Required(init_result):
            return init_result  # type: ignore[return-value]
        initialized = init_result  # type: MCPInitializeResult
        pv = initialized.get("protocolVersion")
        if pv:
            self._protocol_version = str(pv)
        caps = initialized.get("capabilities")
        if caps is not None and isinstance(caps, dict):
            self._server_caps = caps
        else:
            self._server_caps = None

        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        notif_headers = self._base_headers(auth)
        notif_str = json.dumps(notif)

        def parse_notif(res: Any) -> Any:
            sid = _response_header(res, SESSION_HEADER)
            if sid:
                self._session_id = sid
            status = _response_status(res)
            if status != 202 and not (200 <= status < 300):
                raise RuntimeError(
                    f"MCP initialized notification failed: HTTP {status}"
                )
            return {}

        if self._x402_deps is not None:
            request_with_x402(
                {
                    "url": self._endpoint,
                    "method": "POST",
                    "headers": notif_headers,
                    "body": notif_str,
                    "parseResponse": parse_notif,
                },
                self._x402_deps,
            )
        else:
            import requests

            res = requests.request(
                "POST",
                self._endpoint,
                headers=notif_headers,
                data=notif_str,
            )
            sid = _response_header(res, SESSION_HEADER)
            if sid:
                self._session_id = sid
            status = _response_status(res)
            if status != 202 and not (200 <= status < 300):
                raise RuntimeError(
                    f"MCP initialized notification failed: HTTP {status}"
                )

        self._initialized = True
        return None

    def _advertises(self, feature: str) -> bool:
        if self._server_caps is None:
            return True
        return feature in self._server_caps

    def initialize(self, options: Optional[MCPAuthOptions] = None) -> Any:
        res = self._ensure_initialized(options)
        if res is not None and isX402Required(res):
            return _cast_x402(res)
        return {"protocolVersion": self._protocol_version}

    def listTools(self, options: Optional[MCPAuthOptions] = None) -> Any:
        init = self._ensure_initialized(options)
        if init is not None and isX402Required(init):
            return _cast_x402(init)
        if self._tools_cache is not None:
            return self._tools_cache
        out: List[MCPTool] = []
        cursor: Optional[str] = None
        while True:
            page = self._post_json_rpc(
                "tools/list",
                {"cursor": cursor} if cursor else {},
                options,
            )
            if isX402Required(page):
                return _cast_x402(page)  # type: ignore[arg-type]
            p = page  # type: Dict[str, Any]
            out.extend(p.get("tools") or [])
            cursor = p.get("nextCursor")
            if not cursor:
                break
        self._tools_cache = out
        self._rebuild_dynamic_tools(out)
        return out

    def _rebuild_dynamic_tools(self, tools: List[MCPTool]) -> None:
        self._dynamic_tools = {}
        for tool in tools:
            name = tool.get("name")
            if not name:
                continue

            def make_caller(
                n: str,
            ) -> Callable[..., Any]:
                def _fn(
                    args: Optional[Dict[str, Any]] = None,
                    opts: Optional[MCPAuthOptions] = None,
                ) -> Any:
                    return self.call(n, args, opts)

                return _fn

            self._dynamic_tools[str(name)] = make_caller(str(name))

    def call(
        self,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        options: Optional[MCPAuthOptions] = None,
    ) -> Any:
        init = self._ensure_initialized(options)
        if init is not None and isX402Required(init):
            return _cast_x402(init)
        return self._post_json_rpc(
            "tools/call",
            {"name": name, "arguments": args or {}},
            options,
        )

    @property
    def prompts(self) -> Any:
        return _MCPPromptsNamespace(self)

    @property
    def resources(self) -> Any:
        return _MCPResourcesNamespace(self)

    @property
    def tools(self) -> Dict[str, Callable[..., Any]]:
        return self._dynamic_tools

    def getSessionId(self) -> Optional[str]:
        return self._session_id

    def setSessionId(self, session_id: Optional[str] = None) -> None:
        self._session_id = session_id
        if session_id:
            self._initialized = True

    def resetSession(self) -> None:
        self._session_id = None
        self._initialized = False
        self._server_caps = None
        self._tools_cache = None


class _MCPPromptsNamespace:
    def __init__(self, client: MCPClient):
        self._c = client

    def list(self, options: Optional[MCPAuthOptions] = None) -> Any:
        init = self._c._ensure_initialized(options)
        if init is not None and isX402Required(init):
            return _cast_x402(init)
        if not self._c._advertises("prompts"):
            return []  # type: ignore[return-value]
        out: List[MCPPrompt] = []
        cursor: Optional[str] = None
        while True:
            page = self._c._post_json_rpc(
                "prompts/list",
                {"cursor": cursor} if cursor else {},
                options,
            )
            if isX402Required(page):
                return _cast_x402(page)  # type: ignore[arg-type]
            p = page  # type: Dict[str, Any]
            out.extend(p.get("prompts") or [])
            cursor = p.get("nextCursor")
            if not cursor:
                break
        return out

    def get(
        self,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        options: Optional[MCPAuthOptions] = None,
    ) -> Any:
        init = self._c._ensure_initialized(options)
        if init is not None and isX402Required(init):
            return _cast_x402(init)
        if not self._c._advertises("prompts"):
            raise RuntimeError("MCP server did not advertise prompts capability")
        return self._c._post_json_rpc(
            "prompts/get",
            {"name": name, "arguments": args or {}},
            options,
        )


class _MCPResourcesTemplates:
    def __init__(self, client: MCPClient):
        self._c = client

    def list(self, options: Optional[MCPAuthOptions] = None) -> Any:
        init = self._c._ensure_initialized(options)
        if init is not None and isX402Required(init):
            return _cast_x402(init)
        if not self._c._advertises("resources"):
            return []  # type: ignore[return-value]
        out: List[MCPResourceTemplate] = []
        cursor: Optional[str] = None
        while True:
            page = self._c._post_json_rpc(
                "resources/templates/list",
                {"cursor": cursor} if cursor else {},
                options,
            )
            if isX402Required(page):
                return _cast_x402(page)  # type: ignore[arg-type]
            p = page  # type: Dict[str, Any]
            out.extend(p.get("resourceTemplates") or [])
            cursor = p.get("nextCursor")
            if not cursor:
                break
        return out


class _MCPResourcesNamespace:
    def __init__(self, client: MCPClient):
        self._c = client
        self.templates = _MCPResourcesTemplates(client)

    def list(self, options: Optional[MCPAuthOptions] = None) -> Any:
        init = self._c._ensure_initialized(options)
        if init is not None and isX402Required(init):
            return _cast_x402(init)
        if not self._c._advertises("resources"):
            return []  # type: ignore[return-value]
        out: List[MCPResource] = []
        cursor: Optional[str] = None
        while True:
            page = self._c._post_json_rpc(
                "resources/list",
                {"cursor": cursor} if cursor else {},
                options,
            )
            if isX402Required(page):
                return _cast_x402(page)  # type: ignore[arg-type]
            p = page  # type: Dict[str, Any]
            out.extend(p.get("resources") or [])
            cursor = p.get("nextCursor")
            if not cursor:
                break
        return out

    def read(self, uri: str, options: Optional[MCPAuthOptions] = None) -> Any:
        init = self._c._ensure_initialized(options)
        if init is not None and isX402Required(init):
            return _cast_x402(init)
        if not self._c._advertises("resources"):
            raise RuntimeError("MCP server did not advertise resources capability")
        return self._c._post_json_rpc("resources/read", {"uri": uri}, options)


class _MCPHandleProxy:
    """Proxy unknown identifier-safe attributes to tools/call."""

    __slots__ = ("_client",)

    def __init__(self, client: MCPClient):
        object.__setattr__(self, "_client", client)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        client: MCPClient = object.__getattribute__(self, "_client")
        if _is_identifier_safe(name) and not hasattr(MCPClient, name):
            return lambda args=None, options=None: client.call(
                name, args or {}, options
            )
        return getattr(client, name)


def create_mcp_handle(
    endpoint: str,
    options: Optional[MCPClientOptions] = None,
    x402_deps: Optional["X402RequestDeps"] = None,
) -> Any:
    """Return MCP client with dynamic tool names as attributes (like TS Proxy)."""
    return _MCPHandleProxy(MCPClient(endpoint, options, x402_deps))
