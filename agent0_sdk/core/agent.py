"""
Agent class for managing individual agents.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Union

from typing import TYPE_CHECKING
from .models import (
    AgentId, Address, URI, Timestamp, IdemKey,
    EndpointType, TrustModel, Endpoint, RegistrationFile
)
from .web3_client import Web3Client
from .endpoint_crawler import EndpointCrawler
from .oasf_validator import validate_skill, validate_domain

if TYPE_CHECKING:
    from .sdk import SDK

logger = logging.getLogger(__name__)


class Agent:
    """Represents an individual agent with its registration data."""

    def __init__(self, sdk: "SDK", registration_file: RegistrationFile):
        """Initialize agent with SDK and registration file."""
        self.sdk = sdk
        self.registration_file = registration_file
        # Track which metadata has changed since last registration to avoid sending unchanged data
        self._dirty_metadata = set()
        self._last_registered_wallet = None
        self._last_registered_ens = None
        # Initialize endpoint crawler for fetching capabilities
        self._endpoint_crawler = EndpointCrawler(timeout=5)

    # Read-only properties for direct access
    @property
    def agentId(self) -> Optional[AgentId]:
        """Get agent ID (read-only)."""
        return self.registration_file.agentId

    @property
    def agentURI(self) -> Optional[URI]:
        """Get agent URI (read-only)."""
        return self.registration_file.agentURI

    @property
    def name(self) -> str:
        """Get agent name (read-only)."""
        return self.registration_file.name

    @property
    def description(self) -> str:
        """Get agent description (read-only)."""
        return self.registration_file.description

    @property
    def image(self) -> Optional[URI]:
        """Get agent image URI (read-only)."""
        return self.registration_file.image

    @property
    def active(self) -> bool:
        """Get agent active status (read-only)."""
        return self.registration_file.active

    @property
    def x402support(self) -> bool:
        """Get agent x402 support status (read-only)."""
        return self.registration_file.x402support

    @property
    def walletAddress(self) -> Optional[Address]:
        """Get agent wallet address (read-only)."""
        return self.registration_file.walletAddress

    @property
    def walletChainId(self) -> Optional[int]:
        """Get agent wallet chain ID (read-only)."""
        return self.registration_file.walletChainId

    @property
    def endpoints(self) -> List[Endpoint]:
        """Get agent endpoints list (read-only - use setter methods to modify)."""
        return self.registration_file.endpoints

    @property
    def trustModels(self) -> List[Union[TrustModel, str]]:
        """Get agent trust models list (read-only - use setter methods to modify)."""
        return self.registration_file.trustModels

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get agent metadata dict (read-only - use setter methods to modify)."""
        return self.registration_file.metadata

    @property
    def updatedAt(self) -> Timestamp:
        """Get last update timestamp (read-only)."""
        return self.registration_file.updatedAt

    @property
    def owners(self) -> List[Address]:
        """Get agent owners list (read-only)."""
        return self.registration_file.owners

    @property
    def operators(self) -> List[Address]:
        """Get agent operators list (read-only)."""
        return self.registration_file.operators

    # Derived endpoint properties (convenience)
    @property
    def mcpEndpoint(self) -> Optional[str]:
        """Get MCP endpoint value (read-only)."""
        for endpoint in self.registration_file.endpoints:
            if endpoint.type == EndpointType.MCP:
                return endpoint.value
        return None

    @property
    def a2aEndpoint(self) -> Optional[str]:
        """Get A2A endpoint value (read-only)."""
        for endpoint in self.registration_file.endpoints:
            if endpoint.type == EndpointType.A2A:
                return endpoint.value
        return None

    @property
    def ensEndpoint(self) -> Optional[str]:
        """Get ENS endpoint value (read-only)."""
        for endpoint in self.registration_file.endpoints:
            if endpoint.type == EndpointType.ENS:
                return endpoint.value
        return None
    
    @property
    def mcpTools(self) -> Optional[List[str]]:
        """Get MCP tools list (read-only)."""
        for endpoint in self.registration_file.endpoints:
            if endpoint.type == EndpointType.MCP:
                return endpoint.meta.get('mcpTools')
        return None
    
    @property
    def mcpPrompts(self) -> Optional[List[str]]:
        """Get MCP prompts list (read-only)."""
        for endpoint in self.registration_file.endpoints:
            if endpoint.type == EndpointType.MCP:
                return endpoint.meta.get('mcpPrompts')
        return None
    
    @property
    def mcpResources(self) -> Optional[List[str]]:
        """Get MCP resources list (read-only)."""
        for endpoint in self.registration_file.endpoints:
            if endpoint.type == EndpointType.MCP:
                return endpoint.meta.get('mcpResources')
        return None
    
    @property
    def a2aSkills(self) -> Optional[List[str]]:
        """Get A2A skills list (read-only)."""
        for endpoint in self.registration_file.endpoints:
            if endpoint.type == EndpointType.A2A:
                return endpoint.meta.get('a2aSkills')
        return None

    def registrationFile(self) -> RegistrationFile:
        """Get the compiled registration file."""
        return self.registration_file

    def _collectMetadataForRegistration(self) -> List[Dict[str, Any]]:
        """Collect all metadata entries for registration.
        
        Note: agentWallet is now a reserved metadata key and cannot be set via setMetadata().
        It must be set separately using setAgentWallet() with EIP-712 signature verification.
        """
        metadata_entries = []
        
        # Note: agentWallet is no longer set via metadata - it's now reserved and managed via setAgentWallet()
        
        # Add ENS name metadata
        if self.ensEndpoint:
            name_bytes = self.ensEndpoint.encode('utf-8')
            metadata_entries.append({
                "key": "agentName", 
                "value": name_bytes
            })
        
        # Add custom metadata
        for key, value in self.metadata.items():
            if isinstance(value, str):
                value_bytes = value.encode('utf-8')
            elif isinstance(value, (int, float)):
                value_bytes = str(value).encode('utf-8')
            else:
                value_bytes = str(value).encode('utf-8')
            
            metadata_entries.append({
                "key": key,
                "value": value_bytes
            })
        
        return metadata_entries

    # Endpoint management
    def setMCP(self, endpoint: str, version: str = "2025-06-18", auto_fetch: bool = True) -> 'Agent':
        """
        Set MCP endpoint with version.
        
        Args:
            endpoint: MCP endpoint URL
            version: MCP version
            auto_fetch: If True, automatically fetch capabilities from the endpoint (default: True)
        """
        # Remove existing MCP endpoint if any
        self.registration_file.endpoints = [
            ep for ep in self.registration_file.endpoints 
            if ep.type != EndpointType.MCP
        ]
        
        # Try to fetch capabilities from the endpoint (soft fail)
        meta = {"version": version}
        if auto_fetch:
            try:
                capabilities = self._endpoint_crawler.fetch_mcp_capabilities(endpoint)
                if capabilities:
                    meta.update(capabilities)
                    logger.debug(
                        f"Fetched MCP capabilities: {len(capabilities.get('mcpTools', []))} tools, "
                        f"{len(capabilities.get('mcpPrompts', []))} prompts, "
                        f"{len(capabilities.get('mcpResources', []))} resources"
                    )
            except Exception as e:
                # Soft fail - continue without capabilities
                logger.debug(f"Could not fetch MCP capabilities (non-blocking): {e}")
        
        # Add new MCP endpoint
        mcp_endpoint = Endpoint(
            type=EndpointType.MCP,
            value=endpoint,
            meta=meta
        )
        self.registration_file.endpoints.append(mcp_endpoint)
        self.registration_file.updatedAt = int(time.time())
        return self

    def setA2A(self, agentcard: str, version: str = "0.30", auto_fetch: bool = True) -> 'Agent':
        """
        Set A2A endpoint with version.
        
        Args:
            agentcard: A2A endpoint URL
            version: A2A version
            auto_fetch: If True, automatically fetch skills from the endpoint (default: True)
        """
        # Remove existing A2A endpoint if any
        self.registration_file.endpoints = [
            ep for ep in self.registration_file.endpoints 
            if ep.type != EndpointType.A2A
        ]
        
        # Try to fetch capabilities from the endpoint (soft fail)
        meta = {"version": version}
        if auto_fetch:
            try:
                capabilities = self._endpoint_crawler.fetch_a2a_capabilities(agentcard)
                if capabilities:
                    meta.update(capabilities)
                    skills_count = len(capabilities.get('a2aSkills', []))
                    logger.debug(f"Fetched A2A capabilities: {skills_count} skills")
            except Exception as e:
                # Soft fail - continue without capabilities
                logger.debug(f"Could not fetch A2A capabilities (non-blocking): {e}")
        
        # Add new A2A endpoint
        a2a_endpoint = Endpoint(
            type=EndpointType.A2A,
            value=agentcard,
            meta=meta
        )
        self.registration_file.endpoints.append(a2a_endpoint)
        self.registration_file.updatedAt = int(time.time())
        return self

    def removeEndpoint(
        self,
        type: Optional[EndpointType] = None,
        value: Optional[str] = None
    ) -> 'Agent':
        """Remove endpoint(s) with wildcard semantics."""
        if type is None and value is None:
            # Remove all endpoints
            self.registration_file.endpoints.clear()
        else:
            # Remove matching endpoints
            self.registration_file.endpoints = [
                ep for ep in self.registration_file.endpoints
                if not (
                    (type is None or ep.type == type) and
                    (value is None or ep.value == value)
                )
            ]
        
        self.registration_file.updatedAt = int(time.time())
        return self

    def removeEndpoints(self) -> 'Agent':
        """Remove all endpoints."""
        return self.removeEndpoint()

    # OASF endpoint management
    def _get_or_create_oasf_endpoint(self) -> Endpoint:
        """Get existing OASF endpoint or create a new one with default values."""
        # Find existing OASF endpoint
        for ep in self.registration_file.endpoints:
            if ep.type == EndpointType.OASF:
                return ep
        
        # Create new OASF endpoint with default values
        oasf_endpoint = Endpoint(
            type=EndpointType.OASF,
            value="https://github.com/agntcy/oasf/",
            meta={"version": "v0.8.0", "skills": [], "domains": []}
        )
        self.registration_file.endpoints.append(oasf_endpoint)
        return oasf_endpoint

    def addSkill(self, slug: str, validate_oasf: bool = False) -> 'Agent':
        """
        Add a skill to the OASF endpoint.
        
        Args:
            slug: The skill slug to add (e.g., "natural_language_processing/natural_language_generation/summarization")
            validate_oasf: If True, validate the slug against the OASF taxonomy (default: False)
        
        Returns:
            self for method chaining
        
        Raises:
            ValueError: If validate_oasf=True and the slug is not valid
        """
        if validate_oasf:
            if not validate_skill(slug):
                raise ValueError(
                    f"Invalid OASF skill slug: {slug}. "
                    "Use validate_oasf=False to skip validation."
                )
        
        oasf_endpoint = self._get_or_create_oasf_endpoint()
        
        # Initialize skills array if missing
        if "skills" not in oasf_endpoint.meta:
            oasf_endpoint.meta["skills"] = []
        
        # Add slug if not already present (avoid duplicates)
        skills = oasf_endpoint.meta["skills"]
        if slug not in skills:
            skills.append(slug)
        
        self.registration_file.updatedAt = int(time.time())
        return self

    def removeSkill(self, slug: str) -> 'Agent':
        """
        Remove a skill from the OASF endpoint.
        
        Args:
            slug: The skill slug to remove
        
        Returns:
            self for method chaining
        """
        # Find OASF endpoint
        for ep in self.registration_file.endpoints:
            if ep.type == EndpointType.OASF:
                if "skills" in ep.meta and isinstance(ep.meta["skills"], list):
                    skills = ep.meta["skills"]
                    if slug in skills:
                        skills.remove(slug)
                self.registration_file.updatedAt = int(time.time())
                break
        
        return self

    def addDomain(self, slug: str, validate_oasf: bool = False) -> 'Agent':
        """
        Add a domain to the OASF endpoint.
        
        Args:
            slug: The domain slug to add (e.g., "finance_and_business/investment_services")
            validate_oasf: If True, validate the slug against the OASF taxonomy (default: False)
        
        Returns:
            self for method chaining
        
        Raises:
            ValueError: If validate_oasf=True and the slug is not valid
        """
        if validate_oasf:
            if not validate_domain(slug):
                raise ValueError(
                    f"Invalid OASF domain slug: {slug}. "
                    "Use validate_oasf=False to skip validation."
                )
        
        oasf_endpoint = self._get_or_create_oasf_endpoint()
        
        # Initialize domains array if missing
        if "domains" not in oasf_endpoint.meta:
            oasf_endpoint.meta["domains"] = []
        
        # Add slug if not already present (avoid duplicates)
        domains = oasf_endpoint.meta["domains"]
        if slug not in domains:
            domains.append(slug)
        
        self.registration_file.updatedAt = int(time.time())
        return self

    def removeDomain(self, slug: str) -> 'Agent':
        """
        Remove a domain from the OASF endpoint.
        
        Args:
            slug: The domain slug to remove
        
        Returns:
            self for method chaining
        """
        # Find OASF endpoint
        for ep in self.registration_file.endpoints:
            if ep.type == EndpointType.OASF:
                if "domains" in ep.meta and isinstance(ep.meta["domains"], list):
                    domains = ep.meta["domains"]
                    if slug in domains:
                        domains.remove(slug)
                self.registration_file.updatedAt = int(time.time())
                break
        
        return self

    # Trust models
    def setTrust(
        self,
        reputation: bool = False,
        cryptoEconomic: bool = False,
        teeAttestation: bool = False
    ) -> 'Agent':
        """Set trust models using keyword arguments."""
        trust_models = []
        if reputation:
            trust_models.append(TrustModel.REPUTATION)
        if cryptoEconomic:
            trust_models.append(TrustModel.CRYPTO_ECONOMIC)
        if teeAttestation:
            trust_models.append(TrustModel.TEE_ATTESTATION)
        
        self.registration_file.trustModels = trust_models
        self.registration_file.updatedAt = int(time.time())
        return self

    def trustModels(self, models: List[Union[TrustModel, str]]) -> 'Agent':
        """Set trust models (replace set)."""
        self.registration_file.trustModels = models
        self.registration_file.updatedAt = int(time.time())
        return self

    # Basic info
    def updateInfo(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        image: Optional[URI] = None
    ) -> 'Agent':
        """Update basic agent information."""
        if name is not None:
            self.registration_file.name = name
        if description is not None:
            self.registration_file.description = description
        if image is not None:
            self.registration_file.image = image
        
        self.registration_file.updatedAt = int(time.time())
        return self

    def setAgentWallet(
        self,
        new_wallet: Address,
        chainId: Optional[int] = None,
        *,
        new_wallet_signer: Optional[Union[str, Any]] = None,
        deadline: Optional[int] = None,
        signature: Optional[bytes] = None,
    ) -> 'Agent':
        """Set agent wallet address on-chain (ERC-8004 agentWallet).

        This method is **on-chain only**. The `agentWallet` is a verified attribute and must be set via
        the IdentityRegistry `setAgentWallet` function.

        EOAs: provide `new_wallet_signer` (private key string or eth-account account) OR ensure the SDK
        signer address matches `new_wallet` so the SDK can auto-sign.\n
        Contract wallets (ERC-1271): provide `signature` bytes produced by the wallet’s signing mechanism.
        The SDK will build the correct EIP-712 typed data internally, but cannot produce the wallet signature.

        Args:
            new_wallet: New wallet address (must be controlled by the signer that produces the signature)
            chainId: Optional local bookkeeping for registration file (walletChainId). Defaults to agent chain.
            new_wallet_signer: EOA signer used to sign the EIP-712 message (private key string or eth-account account)
            deadline: Signature deadline timestamp. Defaults to now+60s (must be <= now+5min per contract).
            signature: Raw signature bytes (intended for ERC-1271 / external signing only)
        """
        # Breaking/clean: this API is only meaningful for already-registered agents.
        if not self.agentId:
            raise ValueError(
                "Cannot set agent wallet before the agent is registered on-chain. "
                "Call agent.register(...) / agent.registerIPFS() first to obtain agentId."
            )

        addr = new_wallet

        if not addr:
            raise ValueError("Wallet address cannot be empty. Use a non-zero address.")
        
        # Validate address format
        if not addr.startswith("0x") or len(addr) != 42:
            raise ValueError(f"Invalid Ethereum address format: {addr}. Must be 42 characters starting with '0x'")
        
        # Validate hexadecimal characters
        try:
            int(addr[2:], 16)
        except ValueError:
            raise ValueError(f"Invalid hexadecimal characters in address: {addr}")
        
        # Determine chain ID to use (local bookkeeping)
        if chainId is None:
            # Extract chain ID from agentId if available, otherwise use SDK's chain ID
            if self.agentId and ":" in self.agentId:
                try:
                    chainId = int(self.agentId.split(":")[0])  # First part is chainId
                except (ValueError, IndexError):
                    chainId = self.sdk.chainId  # Use SDK's chain ID as fallback
            else:
                chainId = self.sdk.chainId  # Use SDK's chain ID as fallback
        
        # Parse agent ID
        agent_id_int = int(self.agentId.split(":")[-1]) if ":" in self.agentId else int(self.agentId)

        # Check if wallet is already set to this address (skip if same)
        try:
            current_wallet = self.sdk.web3_client.call_contract(
                self.sdk.identity_registry,
                "getAgentWallet",
                agent_id_int
            )
            if current_wallet and current_wallet.lower() == addr.lower():
                logger.debug(f"Agent wallet is already set to {addr}, skipping on-chain update")
                # Still update local registration file
                self.registration_file.walletAddress = addr
                self.registration_file.walletChainId = chainId
                self.registration_file.updatedAt = int(time.time())
                return self
        except Exception as e:
            logger.debug(f"Could not check current agent wallet: {e}, proceeding with update")
        
        # Set deadline (default to 60 seconds from now; contract max is now+5min)
        if deadline is None:
            deadline = int(time.time()) + 60
        
        # Resolve typed data + signature
        identity_registry_address = self.sdk.identity_registry.address
        owner_address = self.sdk.web3_client.call_contract(self.sdk.identity_registry, "ownerOf", agent_id_int)

        full_message = self.sdk.web3_client.build_agent_wallet_set_typed_data(
            agent_id=agent_id_int,
            new_wallet=addr,
            owner=owner_address,
            deadline=deadline,
            verifying_contract=identity_registry_address,
            chain_id=self.sdk.web3_client.chain_id,
        )

        if signature is None:
            # EOA signing paths
            if new_wallet_signer is not None:
                # Validate signer address matches addr (fail fast)
                try:
                    from eth_account import Account as _Account
                    if isinstance(new_wallet_signer, str):
                        signer_addr = _Account.from_key(new_wallet_signer).address
                    else:
                        signer_addr = getattr(new_wallet_signer, "address", None)
                except Exception:
                    signer_addr = getattr(new_wallet_signer, "address", None)

                if not signer_addr or signer_addr.lower() != addr.lower():
                    raise ValueError(
                        f"new_wallet_signer address ({signer_addr}) does not match new_wallet ({addr})."
                    )

                signature = self.sdk.web3_client.sign_typed_data(full_message, new_wallet_signer)  # type: ignore[arg-type]
            else:
                # Auto-sign only if SDK signer == new wallet
                current_address = self.sdk.web3_client.account.address if self.sdk.web3_client.account else None
                if current_address and current_address.lower() == addr.lower():
                    signature = self.sdk.web3_client.sign_typed_data(full_message, self.sdk.web3_client.account)
                else:
                    raise ValueError(
                        f"New wallet must sign. Provide new_wallet_signer (EOA) or signature (ERC-1271/external). "
                        f"SDK signer is {current_address}, new_wallet is {addr}."
                    )

            # Optional: verify recover matches addr for EOA signatures
            recovered = self.sdk.web3_client.w3.eth.account.recover_message(
                __import__("eth_account.messages").messages.encode_typed_data(full_message=full_message),
                signature=signature,
            )
            if recovered.lower() != addr.lower():
                raise ValueError(f"Signature verification failed: recovered {recovered} but expected {addr}")
        
        # Call setAgentWallet on the contract
        try:
            txHash = self.sdk.web3_client.transact_contract(
                self.sdk.identity_registry,
                "setAgentWallet",
                agent_id_int,
                addr,
                deadline,
                signature
            )
            
            # Wait for transaction
            receipt = self.sdk.web3_client.wait_for_transaction(txHash)
            logger.debug(f"Agent wallet set on-chain: {txHash}")
            
        except Exception as e:
            raise ValueError(f"Failed to set agent wallet on-chain: {e}")
        
        # Update local registration file
        self.registration_file.walletAddress = addr
        self.registration_file.walletChainId = chainId
        self.registration_file.updatedAt = int(time.time())
        self._last_registered_wallet = addr
        
        return self

    def setENS(self, name: str, version: str = "1.0") -> 'Agent':
        """Set ENS name both on-chain and in registration file."""
        # Remove existing ENS endpoints
        self.registration_file.endpoints = [
            ep for ep in self.registration_file.endpoints
            if ep.type != EndpointType.ENS
        ]
        
        # Check if ENS changed
        if name != self._last_registered_ens:
            self._dirty_metadata.add("agentName")
        
        # Add new ENS endpoint
        ens_endpoint = Endpoint(
            type=EndpointType.ENS,
            value=name,
            meta={"version": version}
        )
        self.registration_file.endpoints.append(ens_endpoint)
        self.registration_file.updatedAt = int(time.time())
        
        return self

    def setActive(self, active: bool) -> 'Agent':
        """Set agent active status."""
        self.registration_file.active = active
        self.registration_file.updatedAt = int(time.time())
        return self

    def setX402Support(self, x402Support: bool) -> 'Agent':
        """Set agent x402 payment support."""
        self.registration_file.x402support = x402Support
        self.registration_file.updatedAt = int(time.time())
        return self

    # Metadata management
    def setMetadata(self, kv: Dict[str, Any]) -> 'Agent':
        """Set metadata (SDK-managed bag)."""
        # Mark all provided keys as dirty
        for key in kv.keys():
            self._dirty_metadata.add(key)
        
        self.registration_file.metadata.update(kv)
        self.registration_file.updatedAt = int(time.time())
        return self

    def getMetadata(self) -> Dict[str, Any]:
        """Get metadata."""
        return self.registration_file.metadata.copy()

    def delMetadata(self, key: str) -> 'Agent':
        """Delete a metadata key."""
        if key in self.registration_file.metadata:
            del self.registration_file.metadata[key]
            # Mark this key as dirty for tracking
            self._dirty_metadata.discard(key)  # Remove from dirty set since it's being deleted
            self.registration_file.updatedAt = int(time.time())
        return self

    # Local inspection
    def getRegistrationFile(self) -> RegistrationFile:
        """Get current in-memory file (not necessarily published yet)."""
        return self.registration_file

    # Registration (on-chain)
    def registerIPFS(self) -> RegistrationFile:
        """Register agent on-chain with IPFS flow (mint -> pin -> set URI) or update existing registration."""
        # Validate basic info
        if not self.registration_file.name or not self.registration_file.description:
            raise ValueError("Agent must have name and description before registration")
        
        if self.registration_file.agentId:
            # Agent already registered - update registration file and redeploy
            logger.debug("Agent already registered, updating registration file")
            
            # Upload updated registration file to IPFS
            ipfsCid = self.sdk.ipfs_client.addRegistrationFile(
                self.registration_file,
                chainId=self.sdk.chain_id(),
                identityRegistryAddress=self.sdk.identity_registry.address
            )
            
            # Update metadata on-chain if agent is already registered
            # Only send transactions for dirty (changed) metadata to save gas
            if self._dirty_metadata:
                metadata_entries = self._collectMetadataForRegistration()
                agentId = int(self.agentId.split(":")[-1])
                for entry in metadata_entries:
                    # Only send transaction if this metadata key is dirty
                    if entry["key"] in self._dirty_metadata:
                        txHash = self.sdk.web3_client.transact_contract(
                            self.sdk.identity_registry,
                            "setMetadata",
                            agentId,
                            entry["key"],
                            entry["value"]
                        )
                        try:
                            self.sdk.web3_client.wait_for_transaction(txHash, timeout=30)
                        except Exception as e:
                            logger.warning(f"Transaction timeout for {entry['key']}: {e}")
                        logger.debug(f"Updated metadata on-chain: {entry['key']}")
            else:
                logger.debug("No metadata changes detected, skipping metadata updates")
            
            # Update agent URI on-chain
            agentId = int(self.agentId.split(":")[-1])
            txHash = self.sdk.web3_client.transact_contract(
                self.sdk.identity_registry,
                "setAgentURI",
                agentId,
                f"ipfs://{ipfsCid}"
            )
            try:
                self.sdk.web3_client.wait_for_transaction(txHash, timeout=30)
                logger.debug(f"Updated agent URI on-chain: {txHash}")
            except Exception as e:
                logger.warning(f"URI update timeout (transaction sent: {txHash}): {e}")
            
            # Clear dirty flags after successful registration
            self._last_registered_wallet = self.walletAddress
            self._last_registered_ens = self.ensEndpoint
            self._dirty_metadata.clear()
            
            return self.registration_file
        else:
            # First time registration
            logger.debug("Registering agent for the first time")
            
            # Step 1: Register on-chain without URI
            self._registerWithoutUri()
            
            # Step 2: Prepare registration file with agent ID (already set by _registerWithoutUri)
            # No need to modify agentId as it's already set correctly
            
            # Step 3: Upload to IPFS
            ipfsCid = self.sdk.ipfs_client.addRegistrationFile(
                self.registration_file,
                chainId=self.sdk.chain_id(),
                identityRegistryAddress=self.sdk.identity_registry.address
            )
            
            # Step 4: Set agent URI on-chain
            agentId = int(self.agentId.split(":")[-1])
            txHash = self.sdk.web3_client.transact_contract(
                self.sdk.identity_registry,
                "setAgentURI",
                agentId,
                f"ipfs://{ipfsCid}"
            )
            try:
                self.sdk.web3_client.wait_for_transaction(txHash, timeout=30)
                logger.debug(f"Set agent URI on-chain: {txHash}")
            except Exception as e:
                logger.warning(f"URI set timeout (transaction sent: {txHash}): {e}")
            
            # Clear dirty flags after successful registration
            self._last_registered_wallet = self.walletAddress
            self._last_registered_ens = self.ensEndpoint
            self._dirty_metadata.clear()
            
            return self.registration_file

    def register(self, agentUri: str) -> RegistrationFile:
        """Register agent on-chain with direct URI or update existing registration."""
        # Validate basic info
        if not self.registration_file.name or not self.registration_file.description:
            raise ValueError("Agent must have name and description before registration")
        
        if self.registration_file.agentId:
            # Agent already registered - update agent URI
            logger.debug("Agent already registered, updating agent URI")
            self.setAgentUri(agentUri)
            return self.registration_file
        else:
            # First time registration
            logger.debug("Registering agent for the first time")
            return self._registerWithUri(agentUri)

    def _registerWithoutUri(self, idem: Optional[IdemKey] = None) -> RegistrationFile:
        """Register without URI (IPFS flow step 1) with metadata."""
        # Collect metadata for registration
        metadata_entries = self._collectMetadataForRegistration()
        
        # Mint agent with metadata
        txHash = self.sdk.web3_client.transact_contract(
            self.sdk.identity_registry,
            "register",
            "",  # Empty agentURI for now
            metadata_entries
        )
        
        # Wait for transaction
        receipt = self.sdk.web3_client.wait_for_transaction(txHash)
        
        # Get agent ID from events
        agentId = self._extractAgentIdFromReceipt(receipt)
        
        # Update registration file
        self.registration_file.agentId = f"{self.sdk.chain_id()}:{agentId}"
        self.registration_file.updatedAt = int(time.time())
        
        return self.registration_file

    def _registerWithUri(self, agentURI: URI, idem: Optional[IdemKey] = None) -> RegistrationFile:
        """Register with direct URI and metadata."""
        # Update registration file
        self.registration_file.agentURI = agentURI
        self.registration_file.updatedAt = int(time.time())
        
        # Collect metadata for registration
        metadata_entries = self._collectMetadataForRegistration()
        
        # Mint agent with URI and metadata
        txHash = self.sdk.web3_client.transact_contract(
            self.sdk.identity_registry,
            "register",
            agentURI,
            metadata_entries
        )
        
        # Wait for transaction
        receipt = self.sdk.web3_client.wait_for_transaction(txHash)
        
        # Get agent ID from events
        agentId = self._extractAgentIdFromReceipt(receipt)
        
        # Update registration file
        self.registration_file.agentId = f"{self.sdk.chain_id()}:{agentId}"
        self.registration_file.updatedAt = int(time.time())
        
        return self.registration_file

    def _extractAgentIdFromReceipt(self, receipt: Dict[str, Any]) -> int:
        """Extract agent ID from transaction receipt."""
        # Look for Transfer event (ERC-721)
        for i, log in enumerate(receipt.get('logs', [])):
            try:
                topics = log.get('topics', [])
                if len(topics) >= 4:
                    topic0 = topics[0].hex()
                    # Check if this is a Transfer event (ERC-721) by looking at the topic
                    if topic0 == 'ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
                        # The fourth topic should contain the token ID
                        agentId_hex = topics[3].hex()
                        agentId = int(agentId_hex, 16)
                        return agentId
            except Exception:
                continue
        
        # If no Transfer event found, try to get the token ID from the transaction
        # This is a fallback for cases where the event might not be properly indexed
        try:
            # Get the transaction details
            tx = self.sdk.web3_client.w3.eth.get_transaction(receipt['transactionHash'])
            
            # Try to call the contract to get the latest token ID
            # This assumes the contract has a method to get the total supply or latest ID
            try:
                total_supply = self.sdk.identity_registry.functions.totalSupply().call()
                if total_supply > 0:
                    # Return the latest token ID (total supply - 1, since it's 0-indexed)
                    agentId = total_supply - 1
                    return agentId
            except Exception:
                pass
                
        except Exception:
            pass
        
        raise ValueError("Could not extract agent ID from transaction receipt")

    def updateRegistration(
        self,
        agentURI: Optional[URI] = None,
        idem: Optional[IdemKey] = None,
    ) -> RegistrationFile:
        """Update registration after edits."""
        if not self.registration_file.agentId:
            raise ValueError("Agent must be registered before updating")
        
        # Update URI if provided
        if agentURI is not None:
            self.registration_file.agentURI = agentURI
        
        # Update timestamp
        self.registration_file.updatedAt = int(time.time())
        
        # Update on-chain URI if needed
        if agentURI is not None:
            agentId = int(self.registration_file.agentId.split(":")[-1])
            txHash = self.sdk.web3_client.transact_contract(
                self.sdk.identity_registry,
                "setAgentURI",
                agentId,
                agentURI
            )
            self.sdk.web3_client.wait_for_transaction(txHash)
        
        return self.registration_file

    def setAgentUri(self, uri: str) -> 'Agent':
        """Set the agent URI in registration file (will be saved on-chain during next register call)."""
        if not self.registration_file.agentId:
            raise ValueError("Agent must be registered before setting URI")
        
        # Update local registration file
        self.registration_file.agentURI = uri
        self.registration_file.updatedAt = int(time.time())
        
        return self

    # Ownership and lifecycle controls
    def transfer(
        self,
        to: Address,
        approve_operator: bool = False,
        idem: Optional[IdemKey] = None,
    ) -> Dict[str, Any]:
        """Transfer agent ownership.
        
        Note: When an agent is transferred, the agentWallet is automatically reset
        to the zero address on-chain. The new owner must call setAgentWallet() to
        set a new wallet address with EIP-712 signature verification.
        """
        if not self.registration_file.agentId:
            raise ValueError("Agent must be registered before transferring")
        
        agentId = int(self.registration_file.agentId.split(":")[-1])
        
        # Transfer ownership
        txHash = self.sdk.web3_client.transact_contract(
            self.sdk.identity_registry,
            "transferFrom",
            self.sdk.web3_client.account.address,
            to,
            agentId
        )
        
        receipt = self.sdk.web3_client.wait_for_transaction(txHash)
        
        # Note: agentWallet will be reset to zero address by the contract
        # Update local state to reflect this
        self.registration_file.walletAddress = None
        self._last_registered_wallet = None
        
        return {
            "txHash": txHash,
            "agentId": self.registration_file.agentId,
            "from": self.sdk.web3_client.account.address,
            "to": to
        }

    def addOperator(self, operator: Address, idem: Optional[IdemKey] = None) -> Dict[str, Any]:
        """Add operator (setApprovalForAll)."""
        if not self.registration_file.agentId:
            raise ValueError("Agent must be registered before adding operators")
        
        txHash = self.sdk.web3_client.transact_contract(
            self.sdk.identity_registry,
            "setApprovalForAll",
            operator,
            True
        )
        
        receipt = self.sdk.web3_client.wait_for_transaction(txHash)
        
        return {"txHash": txHash, "operator": operator}

    def removeOperator(self, operator: Address, idem: Optional[IdemKey] = None) -> Dict[str, Any]:
        """Remove operator."""
        if not self.registration_file.agentId:
            raise ValueError("Agent must be registered before removing operators")
        
        txHash = self.sdk.web3_client.transact_contract(
            self.sdk.identity_registry,
            "setApprovalForAll",
            operator,
            False
        )
        
        receipt = self.sdk.web3_client.wait_for_transaction(txHash)
        
        return {"txHash": txHash, "operator": operator}

    def transfer(self, newOwnerAddress: str) -> Dict[str, Any]:
        """Transfer agent ownership to a new address.
        
        Only the current owner can transfer the agent.
        
        Note: When an agent is transferred, the agentWallet is automatically reset
        to the zero address on-chain. The new owner must call setAgentWallet() to
        set a new wallet address with EIP-712 signature verification.
        
        Args:
            newOwnerAddress: Ethereum address of the new owner
            
        Returns:
            Transaction receipt
            
        Raises:
            ValueError: If address is invalid or transfer not allowed
        """
        if not self.registration_file.agentId:
            raise ValueError("Agent must be registered before transfer")
        
        # Validate new owner address
        if not newOwnerAddress or newOwnerAddress == "0x0000000000000000000000000000000000000000":
            raise ValueError("New owner address cannot be zero address")
        
        # Get current owner using SDK utility
        currentOwner = self.sdk.getAgentOwner(self.registration_file.agentId)
        
        # Check if caller is the current owner
        callerAddress = self.sdk.web3_client.account.address
        if callerAddress.lower() != currentOwner.lower():
            raise ValueError(f"Only the current owner ({currentOwner}) can transfer the agent")
        
        # Prevent self-transfer
        if newOwnerAddress.lower() == currentOwner.lower():
            raise ValueError("Cannot transfer to the same owner")
        
        # Validate address format (basic checksum validation)
        try:
            # Convert to checksum format for validation
            checksum_address = self.sdk.web3_client.w3.to_checksum_address(newOwnerAddress)
        except Exception as e:
            raise ValueError(f"Invalid address format: {e}")
        
        logger.debug(f"Transferring agent {self.registration_file.agentId} from {currentOwner} to {checksum_address}")
        
        # Parse agentId to extract tokenId for contract call
        agent_id_str = str(self.registration_file.agentId)
        if ":" in agent_id_str:
            token_id = int(agent_id_str.split(":")[-1])
        else:
            token_id = int(agent_id_str)
        
        # Call transferFrom on the IdentityRegistry contract
        txHash = self.sdk.web3_client.transact_contract(
            self.sdk.identity_registry,
            "transferFrom",
            currentOwner,
            checksum_address,
            token_id
        )
        
        receipt = self.sdk.web3_client.wait_for_transaction(txHash)
        
        logger.debug(f"Agent {self.registration_file.agentId} successfully transferred to {checksum_address}")
        
        # Note: agentWallet will be reset to zero address by the contract
        # Update local state to reflect this
        self.registration_file.walletAddress = None
        self._last_registered_wallet = None
        
        return {"txHash": txHash, "from": currentOwner, "to": checksum_address, "agentId": self.registration_file.agentId}

    def activate(self, idem: Optional[IdemKey] = None) -> RegistrationFile:
        """Activate agent (soft "undelete")."""
        self.registration_file.active = True
        self.registration_file.updatedAt = int(time.time())
        return self.registration_file

    def deactivate(self, idem: Optional[IdemKey] = None) -> RegistrationFile:
        """Deactivate agent (soft "delete")."""
        self.registration_file.active = False
        self.registration_file.updatedAt = int(time.time())
        return self.registration_file

    # Utility methods
    def toJson(self) -> str:
        """Convert registration file to JSON."""
        return json.dumps(self.registration_file.to_dict(
            chain_id=self.sdk.chain_id(),
            identity_registry_address=self.sdk.identity_registry.address if self.sdk.identity_registry else None
        ), indent=2)

    def saveToFile(self, filePath: str) -> None:
        """Save registration file to local file."""
        with open(filePath, 'w') as f:
            f.write(self.to_json())
