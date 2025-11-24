"""
Tests for MCPClient - Model Context Protocol (MCP) client.
"""

import pytest
from unittest.mock import Mock, patch
import json

from agent0_sdk.core.mcp_client import MCPClient


class TestMCPClientInitialization:
    """Test MCPClient initialization."""

    def test_init_http_endpoint(self):
        """Test initialization with HTTP endpoint."""
        client = MCPClient(endpoint_url="http://localhost:3000")

        assert client.endpoint_url == "http://localhost:3000"
        assert client.timeout == 30

    def test_init_https_endpoint(self):
        """Test initialization with HTTPS endpoint."""
        client = MCPClient(endpoint_url="https://example.com/mcp")

        assert client.endpoint_url == "https://example.com/mcp"

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is removed."""
        client = MCPClient(endpoint_url="http://localhost:3000/")

        assert client.endpoint_url == "http://localhost:3000"

    def test_init_custom_timeout(self):
        """Test initialization with custom timeout."""
        client = MCPClient(endpoint_url="http://localhost:3000", timeout=60)

        assert client.timeout == 60

    def test_init_invalid_protocol_raises_error(self):
        """Test that non-HTTP protocols raise error."""
        with pytest.raises(Exception, match="MCP endpoint must be HTTP/HTTPS"):
            MCPClient(endpoint_url="ws://localhost:3000")

        with pytest.raises(ValueError, match="MCP endpoint must be HTTP/HTTPS"):
            MCPClient(endpoint_url="file:///path/to/file")


class TestMCPRequestIdManagement:
    """Test JSON-RPC request ID management."""

    def test_request_id_increments(self):
        """Test that request IDs increment."""
        client = MCPClient(endpoint_url="http://localhost:3000")

        id1 = client._get_next_request_id()
        id2 = client._get_next_request_id()
        id3 = client._get_next_request_id()

        assert id2 == id1 + 1
        assert id3 == id2 + 1

    def test_request_id_starts_at_one(self):
        """Test that first request ID is 1."""
        client = MCPClient(endpoint_url="http://localhost:3000")

        first_id = client._get_next_request_id()

        assert first_id == 1


class TestMCPJSONRPCCalls:
    """Test JSON-RPC 2.0 call mechanism."""

    @patch('requests.post')
    def test_jsonrpc_call_basic(self, mock_post):
        """Test basic JSON-RPC call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"data": "test"}
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        result = client._jsonrpc_call("test_method")

        assert result["data"] == "test"

        # Verify request structure
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "test_method"
        assert payload["id"] == 1

    @patch('requests.post')
    def test_jsonrpc_call_with_params(self, mock_post):
        """Test JSON-RPC call with parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"success": True}
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        params = {"arg1": "value1", "arg2": 42}
        result = client._jsonrpc_call("test_method", params)

        # Verify params were included
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["params"] == params

    @patch('requests.post')
    def test_jsonrpc_call_error_response(self, mock_post):
        """Test handling of JSON-RPC error response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")

        with pytest.raises(Exception, match="Method not found"):
            client._jsonrpc_call("unknown_method")

    @patch('requests.post')
    def test_jsonrpc_call_network_error(self, mock_post):
        """Test handling of network errors."""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

        client = MCPClient(endpoint_url="http://localhost:3000")

        with pytest.raises(Exception, match="MCP request failed"):
            client._jsonrpc_call("test_method")




class TestMCPToolMethods:
    """Test MCP tool-related methods."""

    @patch('requests.post')
    def test_list_tools(self, mock_post):
        """Test listing available tools."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {"name": "search", "description": "Search tool"},
                    {"name": "calculate", "description": "Calculator tool"}
                ]
            }
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        tools = client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "search"
        assert tools[1]["name"] == "calculate"

        # Verify correct method was called
        call_args = mock_post.call_args
        assert call_args[1]["json"]["method"] == "tools/list"

    @patch('requests.post')
    def test_call_tool_without_arguments(self, mock_post):
        """Test calling tool without arguments."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {"type": "text", "text": "Tool result"}
                ]
            }
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        result = client.call_tool("test_tool")

        assert result[0]["text"] == "Tool result"

        # Verify request
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["method"] == "tools/call"
        assert payload["params"]["name"] == "test_tool"

    @patch('requests.post')
    def test_call_tool_with_arguments(self, mock_post):
        """Test calling tool with arguments."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "42"}]
            }
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        result = client.call_tool("calculate", {"expression": "6*7"})

        # Verify arguments were passed
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["params"]["arguments"] == {"expression": "6*7"}


class TestMCPPromptMethods:
    """Test MCP prompt-related methods."""

    @patch('requests.post')
    def test_list_prompts(self, mock_post):
        """Test listing available prompts."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "prompts": [
                    {"name": "greeting", "description": "Greeting prompt"},
                    {"name": "summary", "description": "Summary prompt"}
                ]
            }
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        prompts = client.list_prompts()

        assert len(prompts) == 2
        assert prompts[0]["name"] == "greeting"

        # Verify method
        call_args = mock_post.call_args
        assert call_args[1]["json"]["method"] == "prompts/list"

    @patch('requests.post')
    def test_get_prompt(self, mock_post):
        """Test getting specific prompt."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": "Hello!"}}
                ]
            }
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        prompt = client.get_prompt("greeting")

        assert len(prompt["messages"]) == 1
        assert prompt["messages"][0]["role"] == "user"

        # Verify method
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["method"] == "prompts/get"
        assert payload["params"]["name"] == "greeting"

    @patch('requests.post')
    def test_get_prompt_with_arguments(self, mock_post):
        """Test getting prompt with arguments."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": "Hello, Alice!"}}
                ]
            }
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        prompt = client.get_prompt("greeting", {"name": "Alice"})

        # Verify arguments
        call_args = mock_post.call_args
        assert call_args[1]["json"]["params"]["arguments"] == {"name": "Alice"}


class TestMCPResourceMethods:
    """Test MCP resource-related methods."""

    @patch('requests.post')
    def test_list_resources(self, mock_post):
        """Test listing available resources."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "resources": [
                    {"uri": "file:///data.txt", "name": "data.txt"},
                    {"uri": "file:///config.json", "name": "config.json"}
                ]
            }
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        resources = client.list_resources()

        assert len(resources) == 2
        assert resources[0]["name"] == "data.txt"

        # Verify method
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["method"] == "resources/list"


class TestMCPSSEHandling:
    """Test SSE response handling in requests."""

    @patch('requests.post')
    def test_handles_sse_content_type(self, mock_post):
        """Test that SSE content-type triggers SSE parsing."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'text/event-stream'}
        mock_response.text = """data: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}

"""
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        result = client.list_tools()

        # Should successfully parse SSE response
        assert result == []

    @patch('requests.post')
    def test_handles_json_content_type(self, mock_post):
        """Test that JSON content-type uses JSON parsing."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []}
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000")
        result = client.list_tools()

        assert result == []


class TestMCPEndpointConstruction:
    """Test MCP endpoint URL construction."""

    @patch('requests.post')
    def test_endpoint_url_used_correctly(self, mock_post):
        """Test that endpoint URL is used for requests."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []}
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000/mcp")
        client.list_tools()

        # Verify correct URL was called
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://localhost:3000/mcp"

    @patch('requests.post')
    def test_timeout_applied_to_requests(self, mock_post):
        """Test that timeout is applied to HTTP requests."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []}
        }
        mock_post.return_value = mock_response

        client = MCPClient(endpoint_url="http://localhost:3000", timeout=45)
        client.list_tools()

        # Verify timeout was used
        call_args = mock_post.call_args
        assert call_args[1]["timeout"] == 45
