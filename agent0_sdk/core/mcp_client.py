"""
MCP (Model Context Protocol) Client for agent execution.
Implements JSON-RPC over HTTP for calling MCP agent endpoints.
"""

import logging
import json
from typing import Any, Dict, List, Optional, Union
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for interacting with MCP (Model Context Protocol) endpoints."""

    def __init__(self, endpoint_url: str, timeout: int = 30):
        """
        Initialize MCP client.

        Args:
            endpoint_url: The MCP endpoint URL (must be http:// or https://)
            timeout: Request timeout in seconds (default: 30)
        """
        if not endpoint_url.startswith(('http://', 'https://')):
            raise ValueError(f"MCP endpoint must be HTTP/HTTPS, got: {endpoint_url}")

        self.endpoint_url = endpoint_url.rstrip('/')
        self.timeout = timeout
        self._request_id = 0

    def _get_next_request_id(self) -> int:
        """Get next request ID for JSON-RPC calls."""
        self._request_id += 1
        return self._request_id

    def _jsonrpc_call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a JSON-RPC 2.0 call to the MCP endpoint.

        Args:
            method: JSON-RPC method name
            params: Optional parameters for the method

        Returns:
            JSON-RPC result

        Raises:
            Exception: If the call fails or returns an error
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._get_next_request_id()
        }

        if params:
            payload["params"] = params

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream'
        }

        logger.debug(f"MCP call: {method} to {self.endpoint_url}")

        try:
            response = requests.post(
                self.endpoint_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                stream=True
            )

            response.raise_for_status()

            # Check if response is SSE format
            content_type = response.headers.get('content-type', '')
            if 'text/event-stream' in content_type:
                result = self._parse_sse_response(response.text)
            else:
                result = response.json()

            # Check for JSON-RPC error
            if 'error' in result:
                error = result['error']
                raise Exception(f"MCP error: {error.get('message', error)}")

            # Return the result
            return result.get('result', result)

        except requests.exceptions.RequestException as e:
            logger.error(f"MCP request failed: {e}")
            raise Exception(f"MCP request failed: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in MCP response: {e}")
            raise Exception(f"Invalid JSON response from MCP endpoint: {e}") from e

    def _parse_sse_response(self, sse_text: str) -> Dict[str, Any]:
        """Parse Server-Sent Events (SSE) format response."""
        try:
            for line in sse_text.split('\n'):
                if line.startswith('data: '):
                    json_str = line[6:]
                    data = json.loads(json_str)
                    return data
        except Exception as e:
            logger.debug(f"Failed to parse SSE response: {e}")

        # Fallback: try to parse as regular JSON
        try:
            return json.loads(sse_text)
        except:
            raise Exception(f"Could not parse MCP response: {sse_text[:200]}")

    # Tools methods
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all available tools.

        Returns:
            List of tool definitions with name, description, and input schema
        """
        result = self._jsonrpc_call("tools/list")
        return result.get('tools', [])

    def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Call a specific tool.

        Args:
            name: Tool name
            arguments: Tool arguments/parameters

        Returns:
            Tool execution result
        """
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments

        result = self._jsonrpc_call("tools/call", params)
        return result.get('content', result)

    # Prompts methods
    def list_prompts(self) -> List[Dict[str, Any]]:
        """
        List all available prompts.

        Returns:
            List of prompt definitions
        """
        result = self._jsonrpc_call("prompts/list")
        return result.get('prompts', [])

    def get_prompt(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get a specific prompt.

        Args:
            name: Prompt name
            arguments: Prompt arguments

        Returns:
            Prompt content
        """
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments

        return self._jsonrpc_call("prompts/get", params)

    # Resources methods
    def list_resources(self) -> List[Dict[str, Any]]:
        """
        List all available resources.

        Returns:
            List of resource definitions
        """
        result = self._jsonrpc_call("resources/list")
        return result.get('resources', [])

    def read_resource(self, uri: str) -> Dict[str, Any]:
        """
        Read a specific resource.

        Args:
            uri: Resource URI

        Returns:
            Resource content
        """
        params = {"uri": uri}
        return self._jsonrpc_call("resources/read", params)

    # Convenience methods
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get all agent capabilities (tools, prompts, resources).

        Returns:
            Dict with 'tools', 'prompts', 'resources' lists
        """
        capabilities = {
            'tools': [],
            'prompts': [],
            'resources': []
        }

        try:
            capabilities['tools'] = self.list_tools()
        except Exception as e:
            logger.warning(f"Could not fetch tools: {e}")

        try:
            capabilities['prompts'] = self.list_prompts()
        except Exception as e:
            logger.warning(f"Could not fetch prompts: {e}")

        try:
            capabilities['resources'] = self.list_resources()
        except Exception as e:
            logger.warning(f"Could not fetch resources: {e}")

        return capabilities

    def health_check(self) -> bool:
        """
        Check if the MCP endpoint is responsive.

        Returns:
            True if endpoint is healthy, False otherwise
        """
        try:
            self.list_tools()
            return True
        except:
            return False
