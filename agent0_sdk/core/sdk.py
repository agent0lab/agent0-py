"""
Main SDK class for Agent0.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

from .models import (
    AgentId, ChainId, Address, URI, Timestamp, IdemKey,
    EndpointType, TrustModel, Endpoint, RegistrationFile,
    AgentSummary, Feedback, SearchParams
)
from .web3_client import Web3Client
from .contracts import (
    IDENTITY_REGISTRY_ABI, REPUTATION_REGISTRY_ABI, VALIDATION_REGISTRY_ABI,
    DEFAULT_REGISTRIES, DEFAULT_SUBGRAPH_URLS
)
from .agent import Agent
from .indexer import AgentIndexer
from .ipfs_client import IPFSClient
from .feedback_manager import FeedbackManager
from .subgraph_client import SubgraphClient


class SDK:
    """Main SDK class for Agent0."""

    def __init__(
        self,
        chainId: ChainId,
        rpcUrl: str,
        signer: Optional[Any] = None,  # Optional for read-only operations
        registryOverrides: Optional[Dict[ChainId, Dict[str, Address]]] = None,
        indexingStore: Optional[Any] = None,  # optional (e.g., sqlite/postgres/duckdb)
        embeddings: Optional[Any] = None,  # optional vector backend
        # IPFS configuration
        ipfs: Optional[str] = None,  # "node", "filecoinPin", or "pinata"
        # Direct IPFS node config
        ipfsNodeUrl: Optional[str] = None,
        # Filecoin Pin config
        filecoinPrivateKey: Optional[str] = None,
        # Pinata config
        pinataJwt: Optional[str] = None,
        # Subgraph configuration
        subgraphOverrides: Optional[Dict[ChainId, str]] = None,  # Override subgraph URLs per chain
    ):
        """Initialize the SDK."""
        self.chainId = chainId
        self.rpcUrl = rpcUrl
        self.signer = signer
        
        # Initialize Web3 client (with or without signer for read-only operations)
        if signer:
            if isinstance(signer, str):
                self.web3_client = Web3Client(rpcUrl, private_key=signer)
            else:
                self.web3_client = Web3Client(rpcUrl, account=signer)
        else:
            # Read-only mode - no signer
            self.web3_client = Web3Client(rpcUrl)
        
        # Registry addresses
        self.registry_overrides = registryOverrides or {}
        self._registries = self._resolve_registries()
        
        # Initialize contract instances
        self._identity_registry = None
        self._reputation_registry = None
        self._validation_registry = None
        
        # Resolve subgraph URL (with fallback chain)
        self._subgraph_urls = {}
        if subgraphOverrides:
            self._subgraph_urls.update(subgraphOverrides)
        
        # Get subgraph URL for current chain
        resolved_subgraph_url = None
        
        # Priority 1: Chain-specific override
        if chainId in self._subgraph_urls:
            resolved_subgraph_url = self._subgraph_urls[chainId]
        # Priority 2: Default for chain
        elif chainId in DEFAULT_SUBGRAPH_URLS:
            resolved_subgraph_url = DEFAULT_SUBGRAPH_URLS[chainId]
        else:
            # No subgraph available - subgraph_client will be None
            resolved_subgraph_url = None
        
        # Initialize subgraph client if URL available
        if resolved_subgraph_url:
            self.subgraph_client = SubgraphClient(resolved_subgraph_url)
        else:
            self.subgraph_client = None
        
        # Initialize services
        self.indexer = AgentIndexer(
            web3_client=self.web3_client,
            store=indexingStore,
            embeddings=embeddings,
            subgraph_client=self.subgraph_client,
            subgraph_url_overrides=self._subgraph_urls
        )
        
        # Initialize IPFS client based on configuration
        self.ipfs_client = self._initialize_ipfs_client(
            ipfs, ipfsNodeUrl, filecoinPrivateKey, pinataJwt
        )
        
        # Load registries before passing to FeedbackManager
        identity_registry = self.identity_registry
        reputation_registry = self.reputation_registry
        
        self.feedback_manager = FeedbackManager(
            subgraph_client=self.subgraph_client,
            web3_client=self.web3_client,
            ipfs_client=self.ipfs_client,
            reputation_registry=reputation_registry,
            identity_registry=identity_registry,
            indexer=self.indexer  # Pass indexer for unified search interface
        )

    def _resolve_registries(self) -> Dict[str, Address]:
        """Resolve registry addresses for current chain."""
        # Start with defaults
        registries = DEFAULT_REGISTRIES.get(self.chainId, {}).copy()
        
        # Apply overrides
        if self.chainId in self.registry_overrides:
            registries.update(self.registry_overrides[self.chainId])
        
        return registries

    def _initialize_ipfs_client(
        self, 
        ipfs: Optional[str], 
        ipfsNodeUrl: Optional[str], 
        filecoinPrivateKey: Optional[str], 
        pinataJwt: Optional[str]
    ) -> Optional[IPFSClient]:
        """Initialize IPFS client based on configuration."""
        if not ipfs:
            return None
            
        if ipfs == "node":
            if not ipfsNodeUrl:
                raise ValueError("ipfsNodeUrl is required when ipfs='node'")
            return IPFSClient(url=ipfsNodeUrl, filecoin_pin_enabled=False)
            
        elif ipfs == "filecoinPin":
            if not filecoinPrivateKey:
                raise ValueError("filecoinPrivateKey is required when ipfs='filecoinPin'")
            return IPFSClient(
                url=None, 
                filecoin_pin_enabled=True, 
                filecoin_private_key=filecoinPrivateKey
            )
            
        elif ipfs == "pinata":
            if not pinataJwt:
                raise ValueError("pinataJwt is required when ipfs='pinata'")
            return IPFSClient(
                url=None,
                filecoin_pin_enabled=False,
                pinata_enabled=True,
                pinata_jwt=pinataJwt
            )
            
        else:
            raise ValueError(f"Invalid ipfs value: {ipfs}. Must be 'node', 'filecoinPin', or 'pinata'")

    @property
    def isReadOnly(self) -> bool:
        """Check if SDK is in read-only mode (no signer)."""
        return self.signer is None

    @property
    def identity_registry(self):
        """Get identity registry contract."""
        if self._identity_registry is None:
            address = self._registries.get("IDENTITY")
            if not address:
                raise ValueError(f"No identity registry address for chain {self.chainId}")
            self._identity_registry = self.web3_client.get_contract(
                address, IDENTITY_REGISTRY_ABI
            )
        return self._identity_registry

    @property
    def reputation_registry(self):
        """Get reputation registry contract."""
        if self._reputation_registry is None:
            address = self._registries.get("REPUTATION")
            if not address:
                raise ValueError(f"No reputation registry address for chain {self.chainId}")
            self._reputation_registry = self.web3_client.get_contract(
                address, REPUTATION_REGISTRY_ABI
            )
        return self._reputation_registry

    @property
    def validation_registry(self):
        """Get validation registry contract."""
        if self._validation_registry is None:
            address = self._registries.get("VALIDATION")
            if not address:
                raise ValueError(f"No validation registry address for chain {self.chainId}")
            self._validation_registry = self.web3_client.get_contract(
                address, VALIDATION_REGISTRY_ABI
            )
        return self._validation_registry

    def chain_id(self) -> ChainId:
        """Get current chain ID."""
        return self.chainId

    def registries(self) -> Dict[str, Address]:
        """Get resolved addresses for current chain."""
        return self._registries.copy()

    def get_subgraph_client(self, chain_id: Optional[ChainId] = None) -> Optional[SubgraphClient]:
        """
        Get subgraph client for a specific chain.
        
        Args:
            chain_id: Chain ID (defaults to current chain)
            
        Returns:
            SubgraphClient instance or None if no subgraph available
        """
        target_chain = chain_id if chain_id is not None else self.chainId
        
        # Check if we already have a client for this chain
        if target_chain == self.chainId and self.subgraph_client:
            return self.subgraph_client
        
        # Resolve URL for target chain
        url = None
        if target_chain in self._subgraph_urls:
            url = self._subgraph_urls[target_chain]
        elif target_chain in DEFAULT_SUBGRAPH_URLS:
            url = DEFAULT_SUBGRAPH_URLS[target_chain]
        
        if url:
            return SubgraphClient(url)
        return None

    def set_chain(self, chain_id: ChainId) -> None:
        """Switch chains (advanced)."""
        self.chainId = chain_id
        self._registries = self._resolve_registries()
        # Reset contract instances
        self._identity_registry = None
        self._reputation_registry = None
        self._validation_registry = None

    # Agent lifecycle methods
    def createAgent(
        self,
        name: str,
        description: str,
        image: Optional[URI] = None,
    ) -> Agent:
        """Create a new agent (off-chain object in memory)."""
        registration_file = RegistrationFile(
            name=name,
            description=description,
            image=image,
            updatedAt=int(time.time())
        )
        return Agent(sdk=self, registration_file=registration_file)

    def loadAgent(self, agentId: AgentId) -> Agent:
        """Load an existing agent (hydrates from registration file if registered)."""
        # Convert agentId to string if it's an integer
        agentId = str(agentId)
        
        # Parse agent ID
        if ":" in agentId:
            chain_id, token_id = agentId.split(":", 1)
            if int(chain_id) != self.chainId:
                raise ValueError(f"Agent {agentId} is not on current chain {self.chainId}")
        else:
            token_id = agentId
        
        # Get token URI from contract
        try:
            token_uri = self.web3_client.call_contract(
                self.identity_registry, "tokenURI", int(token_id)
            )
        except Exception as e:
            raise ValueError(f"Failed to load agent {agentId}: {e}")
        
        # Load registration file
        registration_file = self._load_registration_file(token_uri)
        registration_file.agentId = agentId
        registration_file.agentURI = token_uri if token_uri else None
        
        # Store registry address for proper JSON generation
        registry_address = self._registries.get("IDENTITY")
        if registry_address:
            registration_file._registry_address = registry_address
            registration_file._chain_id = self.chainId
        
        # Hydrate on-chain data
        self._hydrate_agent_data(registration_file, int(token_id))
        
        return Agent(sdk=self, registration_file=registration_file)

    def _load_registration_file(self, uri: str) -> RegistrationFile:
        """Load registration file from URI."""
        if uri.startswith("ipfs://"):
            if not self.ipfs_client:
                raise ValueError("IPFS client not configured")
            content = self.ipfs_client.get(uri)
        elif uri.startswith("http"):
            try:
                import requests
                response = requests.get(uri)
                response.raise_for_status()
                content = response.text
            except ImportError:
                raise ImportError("requests not installed. Install with: pip install requests")
        else:
            raise ValueError(f"Unsupported URI scheme: {uri}")
        
        data = json.loads(content)
        return RegistrationFile.from_dict(data)

    def _hydrate_agent_data(self, registration_file: RegistrationFile, token_id: int):
        """Hydrate agent data from on-chain sources."""
        # Get owner
        owner = self.web3_client.call_contract(
            self.identity_registry, "ownerOf", token_id
        )
        registration_file.owners = [owner]
        
        # Get operators (this would require additional contract calls)
        # For now, we'll leave it empty
        registration_file.operators = []
        
        # Hydrate metadata from on-chain (agentWallet, agentName, custom metadata)
        agent_id = token_id
        try:
            # Try to get agentWallet from on-chain metadata
            wallet_bytes = self.web3_client.call_contract(
                self.identity_registry, "getMetadata", agent_id, "agentWallet"
            )
            if wallet_bytes and len(wallet_bytes) > 0:
                wallet_address = "0x" + wallet_bytes.hex()
                registration_file.walletAddress = wallet_address
                # If wallet is read from on-chain, use current chain ID
                # (the chain ID from the registration file might be outdated)
                registration_file.walletChainId = self.chainId
        except Exception as e:
            # No on-chain wallet, will fall back to registration file
            pass
        
        try:
            # Try to get agentName (ENS) from on-chain metadata
            name_bytes = self.web3_client.call_contract(
                self.identity_registry, "getMetadata", agent_id, "agentName"
            )
            if name_bytes and len(name_bytes) > 0:
                ens_name = name_bytes.decode('utf-8')
                # Add ENS endpoint to registration file
                from .models import EndpointType, Endpoint
                # Remove existing ENS endpoints
                registration_file.endpoints = [
                    ep for ep in registration_file.endpoints
                    if ep.type != EndpointType.ENS
                ]
                # Add new ENS endpoint
                ens_endpoint = Endpoint(
                    type=EndpointType.ENS,
                    value=ens_name,
                    meta={"version": "1.0"}
                )
                registration_file.endpoints.append(ens_endpoint)
        except Exception as e:
            # No on-chain ENS name, will fall back to registration file
            pass
        
        # Try to get custom metadata keys from registration file and check on-chain
        # Note: We can't enumerate on-chain metadata keys, so we check each key from the registration file
        # Also check for common custom metadata keys that might exist on-chain
        keys_to_check = list(registration_file.metadata.keys())
        # Also check for known metadata keys that might have been set on-chain
        known_keys = ["testKey", "version", "timestamp", "customField", "anotherField", "numericField"]
        for key in known_keys:
            if key not in keys_to_check:
                keys_to_check.append(key)
        
        for key in keys_to_check:
            try:
                value_bytes = self.web3_client.call_contract(
                    self.identity_registry, "getMetadata", agent_id, key
                )
                if value_bytes and len(value_bytes) > 0:
                    value_str = value_bytes.decode('utf-8')
                    # Try to convert back to original type if possible
                    try:
                        # Try integer
                        value_int = int(value_str)
                        # Check if it's actually stored as integer in metadata or if it was originally a string
                        registration_file.metadata[key] = value_str  # Keep as string for now
                    except ValueError:
                        # Try float
                        try:
                            value_float = float(value_str)
                            registration_file.metadata[key] = value_str  # Keep as string for now
                        except ValueError:
                            registration_file.metadata[key] = value_str
            except Exception as e:
                # Keep registration file value if on-chain not found
                pass

    # Discovery and indexing
    def refreshAgentIndex(self, agentId: AgentId, deep: bool = False) -> AgentSummary:
        """Refresh index for a single agent."""
        return asyncio.run(self.indexer.refresh_agent(agentId, deep=deep))

    def refreshIndex(
        self,
        agentIds: Optional[List[AgentId]] = None,
        concurrency: int = 8,
    ) -> List[AgentSummary]:
        """Refresh index for multiple agents."""
        return asyncio.run(self.indexer.refresh_agents(agentIds, concurrency))

    def getAgent(self, agentId: AgentId) -> AgentSummary:
        """Get agent summary from index."""
        return self.indexer.get_agent(agentId)

    def searchAgents(
        self,
        params: Union[SearchParams, Dict[str, Any], None] = None,
        sort: Union[str, List[str], None] = None,
        page_size: int = 50,
        cursor: Optional[str] = None,
        **kwargs  # Accept search criteria as kwargs for better DX
    ) -> Dict[str, Any]:
        """Search for agents.
        
        Examples:
            # Simple kwargs for better developer experience
            sdk.searchAgents(name="Test")
            sdk.searchAgents(mcpTools=["code_generation"], active=True)
            
            # Explicit SearchParams (for complex queries or IDE autocomplete)
            sdk.searchAgents(SearchParams(name="Test", mcpTools=["code_generation"]))
            
            # With pagination
            sdk.searchAgents(name="Test", page_size=10)
        """
        # If kwargs provided, use them instead of params
        if kwargs and params is None:
            params = SearchParams(**kwargs)
        elif params is None:
            params = SearchParams()
        elif isinstance(params, dict):
            params = SearchParams(**params)
        
        if sort is None:
            sort = ["updatedAt:desc"]
        elif isinstance(sort, str):
            sort = [sort]

        return self.indexer.search_agents(params, sort, page_size, cursor)

    # Feedback methods
    def prepareFeedback(
        self,
        agentId: AgentId,
        score: Optional[int] = None,  # 0-100
        tags: List[str] = None,
        text: Optional[str] = None,
        capability: Optional[str] = None,
        name: Optional[str] = None,
        skill: Optional[str] = None,
        task: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        proofOfPayment: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Prepare feedback file (local file/object)."""
        return self.feedback_manager.prepareFeedback(
            agentId=agentId,
            score=score,
            tags=tags,
            text=text,
            capability=capability,
            name=name,
            skill=skill,
            task=task,
            context=context,
            proofOfPayment=proofOfPayment,
            extra=extra
        )

    def giveFeedback(
        self,
        agentId: AgentId,
        feedbackFile: Dict[str, Any],
        idem: Optional[IdemKey] = None,
        feedback_auth: Optional[bytes] = None,
    ) -> Feedback:
        """Give feedback (maps 8004 endpoint)."""
        return self.feedback_manager.giveFeedback(
            agentId=agentId,
            feedbackFile=feedbackFile,
            idem=idem,
            feedback_auth=feedback_auth
        )

    def getFeedback(self, feedbackId: str) -> Feedback:
        """Get single feedback by ID string."""
        # Parse feedback ID
        agentId, clientAddress, feedbackIndex = Feedback.from_id_string(feedbackId)
        return self.feedback_manager.getFeedback(agentId, clientAddress, feedbackIndex)

    def searchFeedback(
        self,
        agentId: AgentId,
        reviewers: Optional[List[Address]] = None,
        tags: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        tasks: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        minScore: Optional[int] = None,
        maxScore: Optional[int] = None,
        include_revoked: bool = False,
        first: int = 100,
        skip: int = 0,
    ) -> List[Feedback]:
        """Search feedback for an agent."""
        return self.feedback_manager.searchFeedback(
            agentId=agentId,
            clientAddresses=reviewers,
            tags=tags,
            capabilities=capabilities,
            skills=skills,
            tasks=tasks,
            names=names,
            minScore=minScore,
            maxScore=maxScore,
            include_revoked=include_revoked,
            first=first,
            skip=skip
        )

    def revokeFeedback(
        self,
        feedbackId: str,
        reason: Optional[str] = None,
        idem: Optional[IdemKey] = None,
    ) -> Dict[str, Any]:
        """Revoke feedback."""
        # Parse feedback ID
        agentId, clientAddress, feedbackIndex = Feedback.from_id_string(feedbackId)
        return self.feedback_manager.revokeFeedback(agentId, feedbackIndex)

    def appendResponse(
        self,
        feedbackId: str,
        response: Dict[str, Any],
        idem: Optional[IdemKey] = None,
    ) -> Feedback:
        """Append a response/follow-up to existing feedback."""
        # Parse feedback ID
        agentId, clientAddress, feedbackIndex = Feedback.from_id_string(feedbackId)
        return self.feedback_manager.appendResponse(agentId, clientAddress, feedbackIndex, response)

    
    def searchAgentsByReputation(
        self,
        agents: Optional[List[AgentId]] = None,
        tags: Optional[List[str]] = None,
        reviewers: Optional[List[Address]] = None,
        capabilities: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        tasks: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        minAverageScore: Optional[int] = None,  # 0-100
        includeRevoked: bool = False,
        page_size: int = 50,
        cursor: Optional[str] = None,
        sort: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Search agents filtered by reputation criteria."""
        if not self.subgraph_client:
            raise ValueError("Subgraph client required for searchAgentsByReputation")
        
        if sort is None:
            sort = ["createdAt:desc"]
        
        skip = 0
        if cursor:
            try:
                skip = int(cursor)
            except ValueError:
                skip = 0
        
        order_by = "createdAt"
        order_direction = "desc"
        if sort and len(sort) > 0:
            sort_field = sort[0].split(":")
            order_by = sort_field[0] if len(sort_field) >= 1 else order_by
            order_direction = sort_field[1] if len(sort_field) >= 2 else order_direction
        
        try:
            agents_data = self.subgraph_client.search_agents_by_reputation(
                agents=agents,
                tags=tags,
                reviewers=reviewers,
                capabilities=capabilities,
                skills=skills,
                tasks=tasks,
                names=names,
                minAverageScore=minAverageScore,
                includeRevoked=includeRevoked,
                first=page_size,
                skip=skip,
                order_by=order_by,
                order_direction=order_direction
            )
            
            from .models import AgentSummary
            results = []
            for agent_data in agents_data:
                reg_file = agent_data.get('registrationFile') or {}
                if not isinstance(reg_file, dict):
                    reg_file = {}
                
                agent_summary = AgentSummary(
                    chainId=int(agent_data.get('chainId', 0)),
                    agentId=agent_data.get('id'),
                    name=reg_file.get('name', f"Agent {agent_data.get('id')}"),
                    image=reg_file.get('image'),
                    description=reg_file.get('description', ''),
                    owners=[agent_data.get('owner', '')],
                    operators=agent_data.get('operators', []),
                    mcp=reg_file.get('mcpEndpoint') is not None,
                    a2a=reg_file.get('a2aEndpoint') is not None,
                    ens=reg_file.get('ens'),
                    did=reg_file.get('did'),
                    walletAddress=reg_file.get('agentWallet'),
                    supportedTrusts=reg_file.get('supportedTrusts', []),
                    a2aSkills=reg_file.get('a2aSkills', []),
                    mcpTools=reg_file.get('mcpTools', []),
                    mcpPrompts=reg_file.get('mcpPrompts', []),
                    mcpResources=reg_file.get('mcpResources', []),
                    active=reg_file.get('active', True),
                    x402support=reg_file.get('x402support', False),
                    extras={'averageScore': agent_data.get('averageScore')}
                )
                results.append(agent_summary)
            
            next_cursor = str(skip + len(results)) if len(results) == page_size else None
            return {"items": results, "nextCursor": next_cursor}
            
        except Exception as e:
            raise ValueError(f"Failed to search agents by reputation: {e}")
    
    # Feedback methods - delegate to feedback_manager
    def signFeedbackAuth(
        self,
        agentId: "AgentId",
        clientAddress: "Address",
        indexLimit: Optional[int] = None,
        expiryHours: int = 24,
    ) -> bytes:
        """Sign feedback authorization for a client."""
        return self.feedback_manager.signFeedbackAuth(
            agentId, clientAddress, indexLimit, expiryHours
        )
    
    def prepareFeedback(
        self,
        agentId: "AgentId",
        score: Optional[int] = None,  # 0-100
        tags: List[str] = None,
        text: Optional[str] = None,
        capability: Optional[str] = None,
        name: Optional[str] = None,
        skill: Optional[str] = None,
        task: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        proofOfPayment: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Prepare feedback file (local file/object) according to spec."""
        return self.feedback_manager.prepareFeedback(
            agentId, score, tags, text, capability, name, skill, task, context, proofOfPayment, extra
        )
    
    def giveFeedback(
        self,
        agentId: "AgentId",
        feedbackFile: Dict[str, Any],
        idem: Optional["IdemKey"] = None,
        feedbackAuth: Optional[bytes] = None,
    ) -> "Feedback":
        """Give feedback (maps 8004 endpoint)."""
        return self.feedback_manager.giveFeedback(
            agentId, feedbackFile, idem, feedbackAuth
        )
    
    def getFeedback(
        self,
        agentId: "AgentId",
        clientAddress: "Address",
        feedbackIndex: int,
    ) -> "Feedback":
        """Get feedback (maps 8004 endpoint)."""
        return self.feedback_manager.getFeedback(
            agentId, clientAddress, feedbackIndex
        )
    
    def revokeFeedback(
        self,
        agentId: "AgentId",
        clientAddress: "Address",
        feedbackIndex: int,
    ) -> "Feedback":
        """Revoke feedback."""
        return self.feedback_manager.revokeFeedback(
            agentId, clientAddress, feedbackIndex
        )
    
    def appendResponse(
        self,
        agentId: "AgentId",
        clientAddress: "Address",
        feedbackIndex: int,
        response: Dict[str, Any],
    ) -> "Feedback":
        """Append a response/follow-up to existing feedback."""
        return self.feedback_manager.appendResponse(
            agentId, clientAddress, feedbackIndex, response
        )
    
    def getReputationSummary(
        self,
        agentId: "AgentId",
    ) -> Dict[str, Any]:
        """Get reputation summary for an agent."""
        return self.feedback_manager.getReputationSummary(
            agentId
        )
    
    def transferAgent(
        self,
        agentId: "AgentId",
        newOwnerAddress: str,
    ) -> Dict[str, Any]:
        """Transfer agent ownership to a new address.
        
        Convenience method that loads the agent and calls transfer().
        
        Args:
            agentId: The agent ID to transfer
            newOwnerAddress: Ethereum address of the new owner
            
        Returns:
            Transaction receipt
            
        Raises:
            ValueError: If agent not found or transfer not allowed
        """
        # Load the agent
        agent = self.loadAgent(agentId)
        
        # Call the transfer method
        return agent.transfer(newOwnerAddress)
    
    # Utility methods for owner operations
    def getAgentOwner(self, agentId: AgentId) -> str:
        """Get the current owner of an agent.
        
        Args:
            agentId: The agent ID to check (can be "chainId:tokenId" or just tokenId)
            
        Returns:
            The current owner's Ethereum address
            
        Raises:
            ValueError: If agent ID is invalid or agent doesn't exist
        """
        try:
            # Parse agentId to extract tokenId
            if ":" in str(agentId):
                tokenId = int(str(agentId).split(":")[-1])
            else:
                tokenId = int(agentId)
            
            owner = self.web3_client.call_contract(
                self.identity_registry,
                "ownerOf",
                tokenId
            )
            return owner
        except Exception as e:
            raise ValueError(f"Failed to get owner for agent {agentId}: {e}")
    
    def isAgentOwner(self, agentId: AgentId, address: Optional[str] = None) -> bool:
        """Check if an address is the owner of an agent.
        
        Args:
            agentId: The agent ID to check
            address: Address to check (defaults to SDK's signer address)
            
        Returns:
            True if the address is the owner, False otherwise
            
        Raises:
            ValueError: If agent ID is invalid or agent doesn't exist
        """
        if address is None:
            if not self.signer:
                raise ValueError("No signer available and no address provided")
            address = self.web3_client.account.address
        
        try:
            owner = self.getAgentOwner(agentId)
            return owner.lower() == address.lower()
        except ValueError:
            return False
    
    def canTransferAgent(self, agentId: AgentId, address: Optional[str] = None) -> bool:
        """Check if an address can transfer an agent (i.e., is the owner).
        
        Args:
            agentId: The agent ID to check
            address: Address to check (defaults to SDK's signer address)
            
        Returns:
            True if the address can transfer the agent, False otherwise
        """
        return self.isAgentOwner(agentId, address)
