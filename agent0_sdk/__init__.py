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
    SearchParams,
    SearchFeedbackParams,
)

# Try to import SDK and Agent (may fail if web3 is not installed)
try:
    from .core.sdk import SDK
    from .core.agent import Agent
    _sdk_available = True
except ImportError:
    SDK = None
    Agent = None
    _sdk_available = False

__version__ = "1.0.1"
__all__ = [
    "SDK",
    "Agent",
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
    "SearchParams",
    "SearchFeedbackParams",
]
