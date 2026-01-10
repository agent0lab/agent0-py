"""
Core data models for the Agent0 SDK.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Literal
from datetime import datetime


# Type aliases
AgentId = str  # "chainId:tokenId" (e.g., "8453:1234") or just tokenId when chain is implicit
ChainId = int
Address = str  # 0x-hex
URI = str  # https://... or ipfs://...
CID = str  # IPFS CID (if used)
Timestamp = int  # unix seconds
IdemKey = str  # idempotency key for write ops


class EndpointType(Enum):
    """Types of endpoints that agents can advertise."""
    MCP = "MCP"
    A2A = "A2A"
    ENS = "ENS"
    DID = "DID"
    WALLET = "wallet"
    OASF = "OASF"


class TrustModel(Enum):
    """Trust models supported by the SDK."""
    REPUTATION = "reputation"
    CRYPTO_ECONOMIC = "crypto-economic"
    TEE_ATTESTATION = "tee-attestation"


@dataclass
class Endpoint:
    """Represents an agent endpoint."""
    type: EndpointType
    value: str  # endpoint value (URL, name, DID, ENS)
    meta: Dict[str, Any] = field(default_factory=dict)  # optional metadata


@dataclass
class RegistrationFile:
    """Agent registration file structure."""
    agentId: Optional[AgentId] = None  # None until minted
    agentURI: Optional[URI] = None  # where this file is (or will be) published
    name: str = ""
    description: str = ""
    image: Optional[URI] = None
    walletAddress: Optional[Address] = None
    walletChainId: Optional[int] = None  # Chain ID for the wallet address
    endpoints: List[Endpoint] = field(default_factory=list)
    trustModels: List[Union[TrustModel, str]] = field(default_factory=list)
    owners: List[Address] = field(default_factory=list)  # from chain (read-only, hydrated)
    operators: List[Address] = field(default_factory=list)  # from chain (read-only, hydrated)
    active: bool = False  # SDK extension flag
    x402support: bool = False  # Binary flag for x402 payment support
    metadata: Dict[str, Any] = field(default_factory=dict)  # arbitrary, SDK-managed
    updatedAt: Timestamp = field(default_factory=lambda: int(datetime.now().timestamp()))

    def __str__(self) -> str:
        """String representation as JSON."""
        # Use stored registry info if available
        chain_id = getattr(self, '_chain_id', None)
        registry_address = getattr(self, '_registry_address', None)
        return json.dumps(self.to_dict(chain_id, registry_address), indent=2, default=str)
    
    def __repr__(self) -> str:
        """Developer representation."""
        return f"RegistrationFile(agentId={self.agentId}, agentURI={self.agentURI}, name={self.name})"
    
    def to_dict(self, chain_id: Optional[int] = None, identity_registry_address: Optional[str] = None) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        # Build endpoints array
        endpoints = []
        for endpoint in self.endpoints:
            endpoint_dict = {
                "name": endpoint.type.value,
                "endpoint": endpoint.value,
                **endpoint.meta
            }
            endpoints.append(endpoint_dict)
        
        # Note: agentWallet is no longer included in endpoints array.
        # It's now a reserved on-chain metadata key managed via setAgentWallet().
        
        # Build registrations array
        registrations = []
        if self.agentId:
            agent_id_int = int(self.agentId.split(":")[-1]) if ":" in self.agentId else int(self.agentId)
            agent_registry = f"eip155:{chain_id}:{identity_registry_address}" if chain_id and identity_registry_address else f"eip155:1:{{identityRegistry}}"
            registrations.append({
                "agentId": agent_id_int,
                "agentRegistry": agent_registry
            })
        
        return {
            "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
            "name": self.name,
            "description": self.description,
            "image": self.image,
            "endpoints": endpoints,
            "registrations": registrations,
            "supportedTrust": [tm.value if isinstance(tm, TrustModel) else tm for tm in self.trustModels],
            "active": self.active,
            "x402Support": self.x402support,  # Use camelCase in JSON output per spec
            "updatedAt": self.updatedAt,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RegistrationFile:
        """Create from dictionary."""
        endpoints = []
        for ep_data in data.get("endpoints", []):
            name = ep_data["name"]
            # Special handling for agentWallet - it's not a standard endpoint type
            if name == "agentWallet":
                # Skip agentWallet endpoints as they're handled separately via walletAddress field
                continue
            
            ep_type = EndpointType(name)
            ep_value = ep_data["endpoint"]
            ep_meta = {k: v for k, v in ep_data.items() if k not in ["name", "endpoint"]}
            endpoints.append(Endpoint(type=ep_type, value=ep_value, meta=ep_meta))

        trust_models = []
        for tm in data.get("supportedTrust", []):
            try:
                trust_models.append(TrustModel(tm))
            except ValueError:
                trust_models.append(tm)  # custom string

        return cls(
            agentId=data.get("agentId"),
            agentURI=data.get("agentURI"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            image=data.get("image"),
            walletAddress=data.get("walletAddress"),
            walletChainId=data.get("walletChainId"),
            endpoints=endpoints,
            trustModels=trust_models,
            active=data.get("active", False),
            x402support=data.get("x402Support", data.get("x402support", False)),  # Handle both camelCase and lowercase
            metadata=data.get("metadata", {}),
            updatedAt=data.get("updatedAt", int(datetime.now().timestamp())),
        )


@dataclass
class AgentSummary:
    """Summary information for agent discovery and search."""
    chainId: ChainId
    agentId: AgentId
    name: str
    image: Optional[URI]
    description: str
    owners: List[Address]
    operators: List[Address]
    mcp: bool
    a2a: bool
    ens: Optional[str]
    did: Optional[str]
    walletAddress: Optional[Address]
    supportedTrusts: List[str]  # normalized string keys
    a2aSkills: List[str]
    mcpTools: List[str]
    mcpPrompts: List[str]
    mcpResources: List[str]
    active: bool
    x402support: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Feedback:
    """Feedback data structure."""
    id: tuple  # (agentId, clientAddress, feedbackIndex) - tuple for efficiency
    agentId: AgentId
    reviewer: Address
    score: Optional[int]  # 0-100
    tags: List[str] = field(default_factory=list)
    text: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    proofOfPayment: Optional[Dict[str, Any]] = None
    fileURI: Optional[URI] = None
    endpoint: Optional[str] = None  # Endpoint URI associated with feedback
    createdAt: Timestamp = field(default_factory=lambda: int(datetime.now().timestamp()))
    answers: List[Dict[str, Any]] = field(default_factory=list)
    isRevoked: bool = False
    
    # Off-chain only fields (not stored on blockchain)
    capability: Optional[str] = None  # MCP capability: "prompts", "resources", "tools", "completions"
    name: Optional[str] = None  # MCP tool/resource name
    skill: Optional[str] = None  # A2A skill
    task: Optional[str] = None  # A2A task
    
    def __post_init__(self):
        """Validate and set ID after initialization."""
        if isinstance(self.id, str):
            # Convert string ID to tuple
            parsed_id = self.from_id_string(self.id)
            self.id = parsed_id
        elif not isinstance(self.id, tuple) or len(self.id) != 3:
            raise ValueError(f"Feedback ID must be tuple of (agentId, clientAddress, feedbackIndex), got: {self.id}")
    
    @property
    def id_string(self) -> str:
        """Get string representation of ID for external APIs."""
        return f"{self.id[0]}:{self.id[1]}:{self.id[2]}"
    
    @classmethod
    def create_id(cls, agentId: AgentId, clientAddress: Address, feedbackIndex: int) -> tuple:
        """Create feedback ID tuple with normalized address."""
        # Normalize address to lowercase for consistency
        # Ethereum addresses are case-insensitive, but we store them in lowercase
        if isinstance(clientAddress, str) and (clientAddress.startswith("0x") or clientAddress.startswith("0X")):
            normalized_address = "0x" + clientAddress[2:].lower()
        else:
            normalized_address = clientAddress.lower() if isinstance(clientAddress, str) else str(clientAddress).lower()
        return (agentId, normalized_address, feedbackIndex)
    
    @classmethod
    def from_id_string(cls, id_string: str) -> tuple:
        """Parse feedback ID from string.
        
        Format: agentId:clientAddress:feedbackIndex
        Note: agentId may contain colons (e.g., "11155111:123"), so we need to split from the right.
        """
        parts = id_string.rsplit(":", 2)  # Split from right, max 2 splits
        if len(parts) != 3:
            raise ValueError(f"Invalid feedback ID format: {id_string}")
        
        try:
            feedback_index = int(parts[2])
        except ValueError:
            raise ValueError(f"Invalid feedback index: {parts[2]}")
        
        # Normalize address to lowercase for consistency
        client_address = parts[1]
        if isinstance(client_address, str) and (client_address.startswith("0x") or client_address.startswith("0X")):
            normalized_address = "0x" + client_address[2:].lower()
        else:
            normalized_address = client_address.lower() if isinstance(client_address, str) else str(client_address).lower()
        
        return (parts[0], normalized_address, feedback_index)


@dataclass
class SearchParams:
    """Parameters for agent search."""
    chains: Optional[Union[List[ChainId], Literal["all"]]] = None
    name: Optional[str] = None  # case-insensitive substring
    description: Optional[str] = None  # semantic; vector distance < threshold
    owners: Optional[List[Address]] = None
    operators: Optional[List[Address]] = None
    mcp: Optional[bool] = None
    a2a: Optional[bool] = None
    ens: Optional[str] = None  # exact, case-insensitive
    did: Optional[str] = None  # exact
    walletAddress: Optional[Address] = None
    supportedTrust: Optional[List[str]] = None
    a2aSkills: Optional[List[str]] = None
    mcpTools: Optional[List[str]] = None
    mcpPrompts: Optional[List[str]] = None
    mcpResources: Optional[List[str]] = None
    active: Optional[bool] = True
    x402support: Optional[bool] = None
    deduplicate_cross_chain: bool = False  # Deduplicate same agent across chains

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, filtering out None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class SearchFeedbackParams:
    """Parameters for feedback search."""
    agents: Optional[List[AgentId]] = None
    tags: Optional[List[str]] = None
    reviewers: Optional[List[Address]] = None
    capabilities: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    tasks: Optional[List[str]] = None
    names: Optional[List[str]] = None  # MCP tool/resource/prompt names
    endpoint: Optional[str] = None  # Filter by endpoint URI
    minScore: Optional[int] = None  # 0-100
    maxScore: Optional[int] = None  # 0-100
    includeRevoked: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, filtering out None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}
