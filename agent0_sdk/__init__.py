"""
Agent0 SDK - Python SDK for agent portability, discovery and trust based on ERC-8004.
"""

from .core.models import (
    AgentId,
    ChainId,
    Address,
    URI,
    CID,
    Timestamp,
    IdemKey,
    EndpointType,
    TrustModel,
    Endpoint,
    RegistrationFile,
    AgentSummary,
    Feedback,
    SearchFilters,
    SearchOptions,
    FeedbackFilters,
    SearchFeedbackParams,
)

# Try to import SDK and Agent (may fail if web3 is not installed)
try:
    from .core.sdk import SDK
    from .core.agent import Agent
    from .core.transaction_handle import TransactionHandle, TransactionMined
    from .core.x402_types import X402Payment, X402RequiredResponse, isX402Required
    from .core.a2a import (
        Part,
        MessageResponse,
        TaskResponse,
        TaskSummary,
        TaskState,
        AgentTask,
        A2APaymentRequired,
        MessageA2AOptions,
        ListTasksOptions,
        LoadTaskOptions,
        AgentCardAuth,
    )
    from .core.a2a_summary_client import A2AClientFromSummary
    from .core.a2a_summary_client import A2AClientFromUrl
    from .core.mcp_client import MCPClient, create_mcp_handle
    from .core.mcp_summary_client import MCPClientFromSummary
    from .core.mcp_types import (
        MCPAuthOptions,
        MCPClientInfo,
        MCPClientOptions,
        MCPInitializeResult,
        MCPTool,
        MCPPrompt,
        MCPPromptGetResult,
        MCPResource,
        MCPResourceTemplate,
        MCPPromptMessage,
    )
    _sdk_available = True
except ImportError:
    SDK = None
    Agent = None
    TransactionHandle = None
    TransactionMined = None
    X402Payment = None
    X402RequiredResponse = None
    isX402Required = None
    Part = None
    MessageResponse = None
    TaskResponse = None
    TaskSummary = None
    TaskState = None
    AgentTask = None
    A2APaymentRequired = None
    MessageA2AOptions = None
    ListTasksOptions = None
    LoadTaskOptions = None
    AgentCardAuth = None
    A2AClientFromSummary = None
    A2AClientFromUrl = None
    _sdk_available = False

__version__ = "1.7.1"
__all__ = [
    "SDK",
    "Agent",
    "TransactionHandle",
    "TransactionMined",
    "AgentId",
    "ChainId",
    "Address",
    "URI",
    "CID",
    "Timestamp",
    "IdemKey",
    "EndpointType",
    "TrustModel",
    "Endpoint",
    "RegistrationFile",
    "AgentSummary",
    "Feedback",
    "SearchFilters",
    "SearchOptions",
    "FeedbackFilters",
    "SearchFeedbackParams",
    "X402Payment",
    "X402RequiredResponse",
    "isX402Required",
    "Part",
    "MessageResponse",
    "TaskResponse",
    "TaskSummary",
    "TaskState",
    "AgentTask",
    "A2APaymentRequired",
    "MessageA2AOptions",
    "ListTasksOptions",
    "LoadTaskOptions",
    "AgentCardAuth",
    "A2AClientFromSummary",
    "A2AClientFromUrl",
    "MCPClient",
    "create_mcp_handle",
    "MCPClientFromSummary",
    "MCPAuthOptions",
    "MCPClientInfo",
    "MCPClientOptions",
    "MCPInitializeResult",
    "MCPTool",
    "MCPPrompt",
    "MCPPromptGetResult",
    "MCPResource",
    "MCPResourceTemplate",
    "MCPPromptMessage",
]
