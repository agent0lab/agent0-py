"""
MCP client types (Streamable HTTP JSON-RPC). Mirrors agent0-ts src/models/mcp.ts.
"""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class MCPClientInfo(TypedDict, total=False):
    name: str
    title: str
    version: str


class MCPAuthOptions(TypedDict, total=False):
    credential: str
    headers: Dict[str, str]


class MCPClientOptions(TypedDict, total=False):
    credential: str
    headers: Dict[str, str]
    protocolVersion: str
    sessionId: str
    clientInfo: MCPClientInfo


class MCPInitializeResult(TypedDict, total=False):
    protocolVersion: str
    capabilities: Dict[str, Any]
    serverInfo: Dict[str, Any]
    instructions: str


class MCPTool(TypedDict, total=False):
    name: str
    title: str
    description: str
    inputSchema: Dict[str, Any]
    outputSchema: Dict[str, Any]
    annotations: Dict[str, Any]


class MCPPrompt(TypedDict, total=False):
    name: str
    title: str
    description: str
    arguments: List[Dict[str, Any]]


class MCPPromptMessage(TypedDict, total=False):
    role: str
    content: Dict[str, Any]


class MCPPromptGetResult(TypedDict, total=False):
    description: str
    messages: List[MCPPromptMessage]


class MCPResource(TypedDict, total=False):
    uri: str
    name: str
    title: str
    description: str
    mimeType: str
    size: int
    annotations: Dict[str, Any]


class MCPResourceTemplate(TypedDict, total=False):
    uriTemplate: str
    name: str
    title: str
    description: str
    mimeType: str
    annotations: Dict[str, Any]


class MCPResourceContent(TypedDict, total=False):
    uri: str
    mimeType: str
    text: str
    blob: str


MCPOptions = MCPAuthOptions  # alias for call sites
