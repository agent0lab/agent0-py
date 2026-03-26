"""
Tests for MCP client (agent0_sdk.core.mcp_client), summary wrapper, and SDK wiring.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from agent0_sdk.core.agent import Agent
from agent0_sdk.core.mcp_client import MCPClient, create_mcp_handle
from agent0_sdk.core.mcp_summary_client import MCPClientFromSummary
from agent0_sdk.core.models import AgentSummary, Endpoint, EndpointType, RegistrationFile, TrustModel
from agent0_sdk.core.sdk import SDK
from agent0_sdk.core.x402_request import X402RequestDeps
from agent0_sdk.core.x402_types import X402Accept, RequestSnapshot, isX402Required


def _json_resp(
    status: int,
    body: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    content_type: str = "application/json",
) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.ok = 200 <= status < 300
    h: Dict[str, str] = {"content-type": content_type}
    if headers:
        h.update(headers)

    class _Hdr:
        def get(self, name: str, default=None):
            for k, v in h.items():
                if k.lower() == name.lower():
                    return v
            return default

    r.headers = _Hdr()
    if body is None:
        r.text = ""
    elif isinstance(body, str):
        r.text = body
    else:
        r.text = json.dumps(body)
    return r


class TestMCPClient:
    def test_initialize_notification_then_list_tools_order(self):
        responses = [
            _json_resp(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                    },
                },
                headers={"Mcp-Session-Id": "sess-1"},
            ),
            _json_resp(202, ""),
            _json_resp(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "result": {"tools": [{"name": "get_weather"}]},
                },
            ),
        ]

        with patch("requests.request", side_effect=responses) as req:
            client = MCPClient("https://mcp.example.com/mcp")
            tools = client.listTools()

        assert tools == [{"name": "get_weather"}]
        assert req.call_count == 3
        methods: List[str] = []
        for call in req.call_args_list:
            data = call.kwargs.get("data")
            if data:
                methods.append(json.loads(data)["method"])
        assert methods == ["initialize", "notifications/initialized", "tools/list"]
        hdrs = req.call_args_list[2].kwargs["headers"]
        assert hdrs.get("Mcp-Session-Id") == "sess-1"

    def test_tool_call(self):
        responses = [
            _json_resp(
                200,
                {"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}},
            ),
            _json_resp(202, ""),
            _json_resp(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "result": {
                        "content": [{"type": "text", "text": "Sunny"}],
                        "isError": False,
                    },
                },
            ),
        ]
        with patch("requests.request", side_effect=responses):
            client = MCPClient("https://mcp.example.com/mcp")
            result = client.call("weather/get", {"location": "Paris"})
        assert result["content"][0]["text"] == "Sunny"

    def test_proxy_dynamic_tool(self):
        responses = [
            _json_resp(
                200,
                {"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}},
            ),
            _json_resp(202, ""),
            _json_resp(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "result": {"content": [{"type": "text", "text": "ok"}]},
                },
            ),
        ]
        with patch("requests.request", side_effect=responses):
            handle = create_mcp_handle("https://mcp.example.com/mcp")
            result = handle.get_weather({"location": "Rome"})
        assert result["content"][0]["text"] == "ok"

    def test_prompts_list_and_get(self):
        responses = [
            _json_resp(
                200,
                {"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}},
            ),
            _json_resp(202, ""),
            _json_resp(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "result": {"prompts": [{"name": "code_review"}]},
                },
            ),
            _json_resp(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "3",
                    "result": {
                        "messages": [
                            {"role": "user", "content": {"type": "text", "text": "review this"}}
                        ]
                    },
                },
            ),
        ]
        with patch("requests.request", side_effect=responses):
            client = MCPClient("https://mcp.example.com/mcp")
            prompts = client.prompts.list()
            got = client.prompts.get("code_review", {"code": "x"})
        assert prompts == [{"name": "code_review"}]
        assert got["messages"][0]["role"] == "user"

    def test_resources_list_read_templates(self):
        responses = [
            _json_resp(
                200,
                {"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}},
            ),
            _json_resp(202, ""),
            _json_resp(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "result": {"resources": [{"uri": "file:///a", "name": "a"}]},
                },
            ),
            _json_resp(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "3",
                    "result": {"contents": [{"uri": "file:///a", "text": "hello"}]},
                },
            ),
            _json_resp(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": "4",
                    "result": {
                        "resourceTemplates": [
                            {"uriTemplate": "file:///{path}", "name": "files"}
                        ]
                    },
                },
            ),
        ]
        with patch("requests.request", side_effect=responses):
            client = MCPClient("https://mcp.example.com/mcp")
            lst = client.resources.list()
            read = client.resources.read("file:///a")
            templates = client.resources.templates.list()
        assert lst == [{"uri": "file:///a", "name": "a"}]
        assert read["contents"][0]["text"] == "hello"
        assert templates == [{"uriTemplate": "file:///{path}", "name": "files"}]

    def test_bearer_from_credential(self):
        responses = [
            _json_resp(
                200,
                {"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}},
            ),
            _json_resp(202, ""),
            _json_resp(
                200,
                {"jsonrpc": "2.0", "id": "2", "result": {"tools": []}},
            ),
        ]
        with patch("requests.request", side_effect=responses) as req:
            client = MCPClient("https://mcp.example.com/mcp", {"credential": "token-123"})
            client.listTools()
        last = req.call_args_list[2].kwargs["headers"]
        assert last.get("Authorization") == "Bearer token-123"

    def test_initialize_402_pay_retry(self):
        accepts_payload = {
            "accepts": [
                {
                    "price": "100",
                    "token": "0x0000000000000000000000000000000000000001",
                    "network": "84532",
                    "destination": "0x0000000000000000000000000000000000000002",
                }
            ]
        }
        pay_header = base64.b64encode(json.dumps(accepts_payload).encode()).decode()
        r402 = _json_resp(402, headers={"payment-required": pay_header})
        r200 = _json_resp(
            200,
            {"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}},
        )
        n_calls: List[int] = []

        def fetch(url, method, headers, body, payment_header_name=None, payment_payload=None):
            n_calls.append(1)
            if len(n_calls) == 1:
                return r402
            return r200

        def build_payment(accept: X402Accept, snapshot: RequestSnapshot) -> str:
            return base64.b64encode(
                json.dumps(
                    {"x402Version": 1, "payload": {"signature": "0x" + "a" * 130, "authorization": {}}}
                ).encode()
            ).decode()

        deps = X402RequestDeps(fetch=fetch, build_payment=build_payment)
        client = MCPClient("https://mcp.example.com/mcp", {}, deps)
        init = client.initialize()
        assert isX402Required(init)
        init.x402Payment.pay()
        assert len(n_calls) == 2


class TestMCPSummaryAndSDK:
    def test_summary_raises_without_mcp_url(self):
        summary = AgentSummary(
            chainId=1,
            agentId="1:1",
            name="x",
            image=None,
            description="x",
            owners=[],
            operators=[],
            ens=None,
            did=None,
            walletAddress=None,
            supportedTrusts=[],
            a2aSkills=[],
            mcpTools=[],
            mcpPrompts=[],
            mcpResources=[],
            active=True,
            mcp=None,
        )
        client = MCPClientFromSummary(MagicMock(), summary)
        with pytest.raises(RuntimeError, match="no MCP endpoint"):
            client.listTools()

    def test_create_mcp_client_agent_same_as_property(self):
        with patch("agent0_sdk.core.sdk.Web3Client") as mock_web3:
            mock_web3.return_value.chain_id = 84532
            sdk = SDK(
                chainId=84532,
                rpcUrl="https://base-sepolia.drpc.org",
                signer="0x1234567890abcdef",
            )
        reg = RegistrationFile(
            name="x",
            description="x",
            endpoints=[
                Endpoint(
                    type=EndpointType.MCP,
                    value="https://mcp.example.com/mcp",
                    meta={"version": "2025-06-18"},
                )
            ],
            trustModels=[TrustModel.REPUTATION],
            owners=[],
            operators=[],
            active=True,
            x402support=False,
            metadata={},
            updatedAt=0,
        )
        agent = Agent(sdk, reg)
        assert sdk.create_mcp_client(agent) is agent.mcp

    def test_create_mcp_client_applies_session_id_option(self):
        with patch("agent0_sdk.core.sdk.Web3Client") as mock_web3:
            mock_web3.return_value.chain_id = 84532
            sdk = SDK(
                chainId=84532,
                rpcUrl="https://base-sepolia.drpc.org",
                signer="0x1234567890abcdef",
            )
        reg = RegistrationFile(
            name="x",
            description="x",
            endpoints=[
                Endpoint(
                    type=EndpointType.MCP,
                    value="https://mcp.example.com/mcp",
                    meta={"version": "2025-06-18"},
                )
            ],
            trustModels=[TrustModel.REPUTATION],
            owners=[],
            operators=[],
            active=True,
            x402support=False,
            metadata={},
            updatedAt=0,
        )
        agent = Agent(sdk, reg)
        sdk.create_mcp_client(agent, {"sessionId": "pre-set-session"})
        assert agent.mcp.getSessionId() == "pre-set-session"

    def test_create_mcp_client_summary_lazy(self):
        responses = [
            _json_resp(
                200,
                {"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}},
            ),
            _json_resp(202, ""),
            _json_resp(
                200,
                {"jsonrpc": "2.0", "id": "2", "result": {"tools": []}},
            ),
        ]
        with patch("agent0_sdk.core.sdk.Web3Client") as mock_web3:
            mock_web3.return_value.chain_id = 84532
            sdk = SDK(
                chainId=84532,
                rpcUrl="https://base-sepolia.drpc.org",
                signer="0x1234567890abcdef",
            )
        summary = AgentSummary(
            chainId=1,
            agentId="1:1",
            name="x",
            image=None,
            description="x",
            owners=[],
            operators=[],
            ens=None,
            did=None,
            walletAddress=None,
            supportedTrusts=[],
            a2aSkills=[],
            mcpTools=[],
            mcpPrompts=[],
            mcpResources=[],
            active=True,
            mcp="https://mcp.example.com/mcp",
        )
        with patch("requests.request", side_effect=responses) as req:
            client = sdk.create_mcp_client(summary)
            client.listTools()
        assert req.call_count == 3
