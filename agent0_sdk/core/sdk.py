"""
Main SDK class for Agent0.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Union, Literal
from datetime import datetime

logger = logging.getLogger(__name__)

from .data_uri import is_erc8004_json_data_uri, decode_erc8004_json_data_uri
from .models import (
    AgentId, ChainId, Address, URI, Timestamp, IdemKey,
    EndpointType, TrustModel, Endpoint, RegistrationFile,
    AgentSummary, Feedback, SearchFilters, SearchOptions, FeedbackFilters
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
from .transaction_handle import TransactionHandle
from .subgraph_client import SubgraphClient
from .telemetry import (
    TelemetryClient,
    DEFAULT_TELEMETRY_ENDPOINT,
    categorize_error,
)


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
        subgraphUrl: Optional[str] = None,  # Single default subgraph URL for current chain (e.g. for tests)
        # Telemetry
        api_key: Optional[str] = None,
        telemetry_endpoint: Optional[str] = None,
        registrationDataUriMaxBytes: int = 256 * 1024,
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
        self._subgraph_urls: Dict[ChainId, str] = {}
        if subgraphOverrides:
            self._subgraph_urls.update(subgraphOverrides)
        if subgraphUrl:
            self._subgraph_urls[chainId] = subgraphUrl

        # Get subgraph URL for current chain
        resolved_subgraph_url = (
            self._subgraph_urls.get(chainId)
            or DEFAULT_SUBGRAPH_URLS.get(chainId)
        )
        
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

        # Telemetry (fire-and-forget when api_key is set)
        if api_key and api_key.strip():
            self._telemetry = TelemetryClient(
                api_key=api_key.strip(),
                endpoint=telemetry_endpoint or DEFAULT_TELEMETRY_ENDPOINT,
            )
        else:
            self._telemetry = None

        # Max decoded bytes for ERC-8004 JSON base64 data URIs (on-chain registration files)
        self.registrationDataUriMaxBytes = int(registrationDataUriMaxBytes) if registrationDataUriMaxBytes else 256 * 1024

    def _emit_telemetry_event(self, event: Dict[str, Any]) -> None:
        """Emit a single telemetry event. No-op if telemetry is disabled."""
        if self._telemetry:
            self._telemetry.emit([event])

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
            # Default trust model: reputation (if caller doesn't set one explicitly).
            trustModels=[TrustModel.REPUTATION],
            updatedAt=int(time.time())
        )
        return Agent(sdk=self, registration_file=registration_file)

    def loadAgent(self, agentId: AgentId) -> Agent:
        """Load an existing agent (hydrates from registration file if registered).
        
        Note: Agents can be minted with an empty token URI (e.g. IPFS flow where publish fails).
        In that case we return a partially-hydrated Agent with an empty registration file so the
        caller can resume publishing and set the URI later.
        """
        start_ms = int(time.time() * 1000)
        agent_id_str = str(agentId)
        try:
            # Convert agentId to string if it's an integer
            agentId = agent_id_str

            # Parse agent ID
            if ":" in agentId:
                chain_id, token_id = agentId.split(":", 1)
                if int(chain_id) != self.chainId:
                    raise ValueError(f"Agent {agentId} is not on current chain {self.chainId}")
            else:
                token_id = agentId

            # Get token URI from contract
            try:
                agent_uri = self.web3_client.call_contract(
                    self.identity_registry, "tokenURI", int(token_id)  # tokenURI is ERC-721 standard, but represents agentURI
                )
            except Exception as e:
                raise ValueError(f"Failed to load agent {agentId}: {e}")

            # Load registration file (or fall back to a minimal file if agent URI is missing)
            registration_file = self._load_registration_file(agent_uri)
            registration_file.agentId = agentId
            registration_file.agentURI = agent_uri if agent_uri else None

            if not agent_uri or not str(agent_uri).strip():
                logger.warning(
                    f"Agent {agentId} has no agentURI set on-chain yet. "
                    "Returning a partial agent; update info and call registerIPFS() to publish and set URI."
                )

            # Store registry address for proper JSON generation
            registry_address = self._registries.get("IDENTITY")
            if registry_address:
                registration_file._registry_address = registry_address
                registration_file._chain_id = self.chainId

            # Hydrate on-chain data
            self._hydrate_agent_data(registration_file, int(token_id))

            self._emit_telemetry_event({
                "eventType": "agent.loaded",
                "success": True,
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {"chainId": self.chainId, "agentId": agent_id_str},
            })
            return Agent(sdk=self, registration_file=registration_file)
        except Exception as e:
            self._emit_telemetry_event({
                "eventType": "agent.loaded",
                "success": False,
                "errorType": categorize_error(e),
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {"chainId": self.chainId, "agentId": agent_id_str},
            })
            raise

    def _load_registration_file(self, uri: str) -> RegistrationFile:
        """Load registration file from URI.
        
        If uri is empty/None/whitespace, returns an empty RegistrationFile to allow resume flows.
        """
        if not uri or not str(uri).strip():
            return RegistrationFile()

        if is_erc8004_json_data_uri(uri):
            data = decode_erc8004_json_data_uri(uri, max_bytes=self.registrationDataUriMaxBytes)
            return RegistrationFile.from_dict(data)
        if uri.startswith("data:"):
            raise ValueError(
                "Unsupported data URI. Expected data:application/json;...;base64,... per ERC-8004."
            )

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
        
        # Hydrate agentWallet from on-chain (now uses getAgentWallet() instead of metadata)
        agent_id = token_id
        try:
            # Get agentWallet using the new dedicated function
            wallet_address = self.web3_client.call_contract(
                self.identity_registry, "getAgentWallet", agent_id
            )
            if wallet_address and wallet_address != "0x0000000000000000000000000000000000000000":
                registration_file.walletAddress = wallet_address
                # If wallet is read from on-chain, use current chain ID
                # (the chain ID from the registration file might be outdated)
                registration_file.walletChainId = self.chainId
        except Exception as e:
            # No on-chain wallet set, will fall back to registration file
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
        start_ms = int(time.time() * 1000)
        agent_id_str = str(agentId)
        try:
            result = self.indexer.get_agent(agentId)
            self._emit_telemetry_event({
                "eventType": "agent.fetched",
                "success": True,
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agent_id_str,
                    "found": result is not None,
                },
            })
            return result
        except Exception as e:
            self._emit_telemetry_event({
                "eventType": "agent.fetched",
                "success": False,
                "errorType": categorize_error(e),
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agent_id_str,
                    "found": False,
                },
            })
            raise

    def searchAgents(
        self,
        filters: Union[SearchFilters, Dict[str, Any], None] = None,
        options: Union[SearchOptions, Dict[str, Any], None] = None,
        **kwargs  # Accept search criteria as kwargs for better DX
    ) -> List[AgentSummary]:
        """Search for agents.
        
        Examples:
            # Simple kwargs for better developer experience
            sdk.searchAgents(name="Test")
            sdk.searchAgents(mcpTools=["code_generation"], active=True)
            
            # Explicit SearchParams (for complex queries or IDE autocomplete)
            sdk.searchAgents(SearchParams(name="Test", mcpTools=["code_generation"]))
        """
        # Allow kwargs to populate filters for better DX.
        if kwargs and filters is None:
            if isinstance(kwargs.get("feedback"), dict):
                kwargs["feedback"] = FeedbackFilters(**kwargs["feedback"])
            filters = SearchFilters(**kwargs)
        elif filters is None:
            filters = SearchFilters()
        elif isinstance(filters, dict):
            if isinstance(filters.get("feedback"), dict):
                filters["feedback"] = FeedbackFilters(**filters["feedback"])
            filters = SearchFilters(**filters)
        
        if options is None:
            options = SearchOptions()
        elif isinstance(options, dict):
            options = SearchOptions(**options)

        # Do not force a default sort here; the indexer chooses keyword-aware defaults.
        start_ms = int(time.time() * 1000)
        try:
            out = self.indexer.search_agents(filters, options)
            items = out.get("items") if isinstance(out, dict) else out
            items = items or []
            results = [
                getattr(a, "agentId", a.get("agentId") if isinstance(a, dict) else None)
                for a in (items[:100])
            ]
            payload = {
                "chainId": self.chainId,
                "results": results,
            }
            self._emit_telemetry_event({
                "eventType": "search.query",
                "success": True,
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": payload,
            })
            if isinstance(out, dict):
                return out.get("items") or []
            return out or []
        except Exception as e:
            self._emit_telemetry_event({
                "eventType": "search.query",
                "success": False,
                "errorType": categorize_error(e),
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {"chainId": self.chainId, "results": []},
            })
            raise

    # Feedback methods are defined later in this class (single authoritative API).
    
    # Feedback methods - delegate to feedback_manager
    def prepareFeedbackFile(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare an off-chain feedback file payload.
        
        This is intentionally off-chain-only; it does not attempt to represent
        the on-chain fields (value/tag1/tag2/endpoint-on-chain).
        """
        return self.feedback_manager.prepareFeedbackFile(input)
    
    def giveFeedback(
        self,
        agentId: "AgentId",
        value: Union[int, float, str],
        tag1: Optional[str] = None,
        tag2: Optional[str] = None,
        endpoint: Optional[str] = None,
        feedbackFile: Optional[Dict[str, Any]] = None,
    ) -> "TransactionHandle[Feedback]":
        """Give feedback (on-chain first; optional off-chain file upload).
        
        - If feedbackFile is None: submit on-chain only (no upload even if IPFS is configured).
        - If feedbackFile is provided: requires IPFS configured; uploads and commits URI/hash on-chain.
        """
        start_ms = int(time.time() * 1000)
        value_num = int(value) if isinstance(value, (int, float)) else int(str(value), 10)
        agent_id_str = str(agentId)
        try:
            result = self.feedback_manager.giveFeedback(
                agentId=agentId,
                value=value,
                tag1=tag1,
                tag2=tag2,
                endpoint=endpoint,
                feedbackFile=feedbackFile,
            )
            payload = {
                "chainId": self.chainId,
                "agentId": agent_id_str,
                "value": value_num,
                "tag1": tag1,
                "tag2": tag2,
                "hasEndpoint": bool(endpoint),
                "endpoint": endpoint,
                "hasOffchainFile": feedbackFile is not None,
                "hasText": bool(feedbackFile.get("text")) if feedbackFile else False,
                "hasContext": bool(feedbackFile.get("context")) if feedbackFile else False,
                "hasProofOfPayment": bool(feedbackFile.get("proofOfPayment")) if feedbackFile else False,
                "mcpTool": feedbackFile.get("mcpTool") if feedbackFile else None,
                "mcpPrompt": feedbackFile.get("mcpPrompt") if feedbackFile else None,
                "mcpResource": feedbackFile.get("mcpResource") if feedbackFile else None,
                "a2aSkills": feedbackFile.get("a2aSkills") if feedbackFile else None,
                "a2aContextId": feedbackFile.get("a2aContextId") if feedbackFile else None,
                "a2aTaskId": feedbackFile.get("a2aTaskId") if feedbackFile else None,
                "oasfSkills": feedbackFile.get("oasfSkills") if feedbackFile else None,
                "oasfDomains": feedbackFile.get("oasfDomains") if feedbackFile else None,
            }
            self._emit_telemetry_event({
                "eventType": "feedback.given",
                "success": True,
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": payload,
            })
            return result
        except Exception as e:
            self._emit_telemetry_event({
                "eventType": "feedback.given",
                "success": False,
                "errorType": categorize_error(e),
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agent_id_str,
                    "value": value_num,
                    "tag1": tag1,
                    "tag2": tag2,
                },
            })
            raise
    
    def getFeedback(
        self,
        agentId: "AgentId",
        clientAddress: "Address",
        feedbackIndex: int,
    ) -> "Feedback":
        """Get feedback (maps 8004 endpoint)."""
        start_ms = int(time.time() * 1000)
        try:
            result = self.feedback_manager.getFeedback(
                agentId, clientAddress, feedbackIndex
            )
            self._emit_telemetry_event({
                "eventType": "feedback.fetched",
                "success": True,
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": str(agentId),
                    "feedbackIndex": feedbackIndex,
                    "found": True,
                },
            })
            return result
        except Exception as e:
            self._emit_telemetry_event({
                "eventType": "feedback.fetched",
                "success": False,
                "errorType": categorize_error(e),
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": str(agentId),
                    "feedbackIndex": feedbackIndex,
                    "found": False,
                },
            })
            raise

    def searchFeedback(
        self,
        agentId: Optional["AgentId"] = None,
        reviewers: Optional[List["Address"]] = None,
        tags: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        tasks: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        minValue: Optional[float] = None,
        maxValue: Optional[float] = None,
        include_revoked: bool = False,
        agents: Optional[List["AgentId"]] = None,
    ) -> List["Feedback"]:
        """Search feedback.
        
        Backwards compatible:
        - Previously required `agentId`; it is now optional.
        
        New:
        - `agents` can be used to search feedback across multiple agents in one call.
        - `reviewers` can now be used without specifying any agent, enabling "all feedback given by a wallet".
        """
        has_any_filter = any([
            bool(agentId),
            bool(agents),
            bool(reviewers),
            bool(tags),
            bool(capabilities),
            bool(skills),
            bool(tasks),
            bool(names),
            minValue is not None,
            maxValue is not None,
        ])
        if not has_any_filter:
            raise ValueError(
                "searchFeedback requires at least one filter "
                "(agentId/agents/reviewers/tags/capabilities/skills/tasks/names/minValue/maxValue)."
            )

        start_ms = int(time.time() * 1000)
        agent_count = len(agents) if agents else (1 if agentId else 0)
        try:
            result = self.feedback_manager.searchFeedback(
                agentId=agentId,
                agents=agents,
                clientAddresses=reviewers,
                tags=tags,
                capabilities=capabilities,
                skills=skills,
                tasks=tasks,
                names=names,
                minValue=minValue,
                maxValue=maxValue,
                include_revoked=include_revoked,
            )
            self._emit_telemetry_event({
                "eventType": "feedback.searched",
                "success": True,
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agentId,
                    "agentCount": agent_count,
                    "tags": tags,
                    "reviewers": reviewers,
                    "capabilities": capabilities,
                    "skills": skills,
                    "tasks": tasks,
                    "names": names,
                    "minValue": minValue,
                    "maxValue": maxValue,
                    "includeRevoked": include_revoked,
                    "resultCount": len(result),
                    "isZeroResults": len(result) == 0,
                },
            })
            return result
        except Exception as e:
            self._emit_telemetry_event({
                "eventType": "feedback.searched",
                "success": False,
                "errorType": categorize_error(e),
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agentId,
                    "agentCount": agent_count,
                },
            })
            raise
    
    def revokeFeedback(
        self,
        agentId: "AgentId",
        feedbackIndex: int,
    ) -> "TransactionHandle[Feedback]":
        """Revoke feedback (submitted-by-default)."""
        start_ms = int(time.time() * 1000)
        agent_id_str = str(agentId)
        try:
            result = self.feedback_manager.revokeFeedback(agentId, feedbackIndex)
            self._emit_telemetry_event({
                "eventType": "feedback.revoked",
                "success": True,
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agent_id_str,
                    "feedbackIndex": feedbackIndex,
                },
            })
            return result
        except Exception as e:
            self._emit_telemetry_event({
                "eventType": "feedback.revoked",
                "success": False,
                "errorType": categorize_error(e),
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agent_id_str,
                    "feedbackIndex": feedbackIndex,
                },
            })
            raise

    def appendResponse(
        self,
        agentId: "AgentId",
        clientAddress: "Address",
        feedbackIndex: int,
        response: Dict[str, Any],
    ) -> "TransactionHandle[Feedback]":
        """Append a response/follow-up to existing feedback (submitted-by-default)."""
        start_ms = int(time.time() * 1000)
        agent_id_str = str(agentId)
        response_uri = response.get("uri") if response else None
        try:
            result = self.feedback_manager.appendResponse(
                agentId, clientAddress, feedbackIndex, response
            )
            self._emit_telemetry_event({
                "eventType": "feedback.response.appended",
                "success": True,
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agent_id_str,
                    "clientAddress": clientAddress,
                    "feedbackIndex": feedbackIndex,
                    "responseUri": response_uri,
                },
            })
            return result
        except Exception as e:
            self._emit_telemetry_event({
                "eventType": "feedback.response.appended",
                "success": False,
                "errorType": categorize_error(e),
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agent_id_str,
                    "clientAddress": clientAddress,
                    "feedbackIndex": feedbackIndex,
                },
            })
            raise
    
    def getReputationSummary(
        self,
        agentId: "AgentId",
    ) -> Dict[str, Any]:
        """Get reputation summary for an agent."""
        start_ms = int(time.time() * 1000)
        agent_id_str = str(agentId)
        try:
            result = self.feedback_manager.getReputationSummary(agentId)
            self._emit_telemetry_event({
                "eventType": "reputation.summary.fetched",
                "success": True,
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "chainId": self.chainId,
                    "agentId": agent_id_str,
                    "count": result.get("count", 0),
                    "averageValue": result.get("averageValue", 0.0),
                },
            })
            return result
        except Exception as e:
            self._emit_telemetry_event({
                "eventType": "reputation.summary.fetched",
                "success": False,
                "errorType": categorize_error(e),
                "durationMs": int(time.time() * 1000) - start_ms,
                "timestamp": int(time.time() * 1000),
                "payload": {"chainId": self.chainId, "agentId": agent_id_str},
            })
            raise
    
    def transferAgent(
        self,
        agentId: "AgentId",
        newOwnerAddress: str,
    ) -> "TransactionHandle[Dict[str, Any]]":
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
