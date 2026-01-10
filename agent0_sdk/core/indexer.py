"""
Agent indexer for discovery and search functionality.

ARCHITECTURAL PURPOSE:
======================

The indexer serves as the unified entry point for all discovery and search operations
(agents AND feedback), not merely a thin wrapper around SubgraphClient. While currently
it delegates most queries to the subgraph, it is designed to be the foundation for:

1. SEMANTIC/VECTOR SEARCH: Future integration with embeddings and vector databases
   for semantic search across agent descriptions, feedback text, and capabilities.

2. HYBRID SEARCH: Combining subgraph queries (structured data) with vector similarity
   (semantic understanding) for richer discovery experiences.

3. LOCAL INDEXING: Optional local caching and indexing for offline-capable applications
   or performance optimization.

4. SEARCH OPTIMIZATION: Advanced filtering, ranking, and relevance scoring that goes
   beyond simple subgraph queries.

5. MULTI-SOURCE AGGREGATION: Combining data from subgraph, blockchain direct queries,
   and IPFS to provide complete agent/feedback information.

"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import aiohttp
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

from .models import (
    AgentId, ChainId, Address, URI, Timestamp,
    AgentSummary, Feedback, SearchParams, SearchFeedbackParams
)
from .web3_client import Web3Client

logger = logging.getLogger(__name__)


class AgentIndexer:
    """Indexer for agent discovery and search."""

    def __init__(
        self,
        web3_client: Web3Client,
        store: Optional[Any] = None,
        embeddings: Optional[Any] = None,
        subgraph_client: Optional[Any] = None,
        identity_registry: Optional[Any] = None,
        subgraph_url_overrides: Optional[Dict[int, str]] = None,
    ):
        """Initialize indexer with optional subgraph URL overrides for multiple chains."""
        self.web3_client = web3_client
        self.store = store or self._create_default_store()
        self.embeddings = embeddings or self._create_default_embeddings()
        self.subgraph_client = subgraph_client
        self.identity_registry = identity_registry
        self.subgraph_url_overrides = subgraph_url_overrides or {}
        self._agent_cache = {}  # Cache for agent data
        self._cache_timestamp = 0
        self._cache_ttl = 7 * 24 * 60 * 60  # 1 week cache TTL (604800 seconds)
        self._http_cache = {}  # Cache for HTTP content
        self._http_cache_ttl = 60 * 60  # 1 hour cache TTL for HTTP content

        # Cache for subgraph clients (one per chain)
        self._subgraph_client_cache: Dict[int, Any] = {}

        # If default subgraph_client provided, cache it for current chain
        if self.subgraph_client:
            self._subgraph_client_cache[self.web3_client.chain_id] = self.subgraph_client

    def _create_default_store(self) -> Dict[str, Any]:
        """Create default in-memory store."""
        return {
            "agents": {},
            "feedback": {},
            "embeddings": {},
        }

    def _create_default_embeddings(self):
        """Create default embeddings model."""
        try:
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer('all-MiniLM-L6-v2')
        except ImportError:
            # Return None if sentence-transformers is not available
            return None

    async def _fetch_http_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch content from HTTP/HTTPS URL with caching."""
        # Check cache first
        current_time = time.time()
        if url in self._http_cache:
            cached_data, timestamp = self._http_cache[url]
            if current_time - timestamp < self._http_cache_ttl:
                return cached_data
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        content = await response.json()
                        # Cache the result
                        self._http_cache[url] = (content, current_time)
                        return content
                    else:
                        logger.warning(f"Failed to fetch {url}: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.warning(f"Error fetching HTTPS content from {url}: {e}")
            return None

    def _detect_uri_type(self, uri: str) -> str:
        """Detect URI type (ipfs, https, http, unknown)."""
        if uri.startswith("ipfs://"):
            return "ipfs"
        elif uri.startswith("https://"):
            return "https"
        elif uri.startswith("http://"):
            return "http"
        elif self._is_ipfs_cid(uri):
            return "ipfs"
        else:
            return "unknown"

    def _is_ipfs_cid(self, uri: str) -> bool:
        """Check if string is an IPFS CID (without ipfs:// prefix)."""
        # Basic IPFS CID patterns
        # Qm... (CIDv0, 46 characters)
        # bafy... (CIDv1, starts with bafy)
        # bafk... (CIDv1, starts with bafk)
        # bafg... (CIDv1, starts with bafg)
        # bafh... (CIDv1, starts with bafh)
        # bafq... (CIDv1, starts with bafq)
        # bafr... (CIDv1, starts with bafr)
        # bafs... (CIDv1, starts with bafs)
        # baft... (CIDv1, starts with baft)
        # bafu... (CIDv1, starts with bafu)
        # bafv... (CIDv1, starts with bafv)
        # bafw... (CIDv1, starts with bafw)
        # bafx... (CIDv1, starts with bafx)
        # bafy... (CIDv1, starts with bafy)
        # bafz... (CIDv1, starts with bafz)
        
        if not uri:
            return False
            
        # Check for CIDv0 (Qm...)
        if uri.startswith("Qm") and len(uri) == 46:
            return True
            
        # Check for CIDv1 (baf...)
        # CIDv1 has variable length but typically 50+ characters
        # We'll be more lenient for shorter CIDs that start with baf
        if uri.startswith("baf") and len(uri) >= 8:
            return True
            
        return False

    def _is_ipfs_gateway_url(self, url: str) -> bool:
        """Check if URL is an IPFS gateway URL."""
        ipfs_gateways = [
            "ipfs.io",
            "gateway.pinata.cloud",
            "cloudflare-ipfs.com",
            "dweb.link",
            "ipfs.fleek.co"
        ]
        return any(gateway in url for gateway in ipfs_gateways)

    def _convert_gateway_to_ipfs(self, url: str) -> Optional[str]:
        """Convert IPFS gateway URL to ipfs:// format."""
        if "/ipfs/" in url:
            # Extract hash from gateway URL
            parts = url.split("/ipfs/")
            if len(parts) == 2:
                hash_part = parts[1].split("/")[0]  # Remove any path after hash
                return f"ipfs://{hash_part}"
        return None

    async def _fetch_registration_file(self, uri: str) -> Optional[Dict[str, Any]]:
        """Fetch registration file from IPFS or HTTPS."""
        uri_type = self._detect_uri_type(uri)
        
        if uri_type == "ipfs":
            # Normalize bare CID to ipfs:// format
            if not uri.startswith("ipfs://"):
                uri = f"ipfs://{uri}"
            
            # Use existing IPFS client (if available)
            # For now, return None as IPFS fetching is handled by subgraph
            return None
        elif uri_type in ["https", "http"]:
            # Check if it's an IPFS gateway URL
            if self._is_ipfs_gateway_url(uri):
                ipfs_uri = self._convert_gateway_to_ipfs(uri)
                if ipfs_uri:
                    # Try to fetch as IPFS first
                    return await self._fetch_registration_file(ipfs_uri)
            
            # Fetch directly from HTTPS
            return await self._fetch_http_content(uri)
        else:
            logger.warning(f"Unsupported URI type: {uri}")
            return None

    async def _fetch_feedback_file(self, uri: str) -> Optional[Dict[str, Any]]:
        """Fetch feedback file from IPFS or HTTPS."""
        uri_type = self._detect_uri_type(uri)
        
        if uri_type == "ipfs":
            # Normalize bare CID to ipfs:// format
            if not uri.startswith("ipfs://"):
                uri = f"ipfs://{uri}"
            
            # Use existing IPFS client (if available)
            # For now, return None as IPFS fetching is handled by subgraph
            return None
        elif uri_type in ["https", "http"]:
            # Check if it's an IPFS gateway URL
            if self._is_ipfs_gateway_url(uri):
                ipfs_uri = self._convert_gateway_to_ipfs(uri)
                if ipfs_uri:
                    # Try to fetch as IPFS first
                    return await self._fetch_feedback_file(ipfs_uri)
            
            # Fetch directly from HTTPS
            return await self._fetch_http_content(uri)
        else:
            logger.warning(f"Unsupported URI type: {uri}")
            return None

    async def refresh_agent(self, agent_id: AgentId, deep: bool = False) -> AgentSummary:
        """Refresh index for a single agent."""
        # Parse agent ID
        if ":" in agent_id:
            chain_id, token_id = agent_id.split(":", 1)
        else:
            chain_id = self.web3_client.chain_id
            token_id = agent_id

        # Get basic agent data from contract
        try:
            if self.identity_registry:
                agent_uri = self.web3_client.call_contract(
                    self.identity_registry,
                    "tokenURI",  # ERC-721 standard function name, but represents agentURI
                    int(token_id)
                )
            else:
                raise ValueError("Identity registry not available")
        except Exception as e:
            raise ValueError(f"Failed to get agent data: {e}")

        # Load registration file
        registration_data = await self._load_registration_data(token_uri)
        
        # Create agent summary
        summary = self._create_agent_summary(
            chain_id=int(chain_id),
            agent_id=agent_id,
            registration_data=registration_data
        )

        # Store in index
        self.store["agents"][agent_id] = summary

        # Deep refresh if requested
        if deep:
            await self._deep_refresh_agent(summary)

        return summary

    async def refresh_agents(
        self,
        agent_ids: Optional[List[AgentId]] = None,
        concurrency: int = 8,
    ) -> List[AgentSummary]:
        """Refresh index for multiple agents."""
        if agent_ids is None:
            # Get all known agents (this would need to be implemented)
            agent_ids = list(self.store["agents"].keys())

        # Use semaphore to limit concurrency
        semaphore = asyncio.Semaphore(concurrency)

        async def refresh_single(agent_id: AgentId) -> AgentSummary:
            async with semaphore:
                return await self.refresh_agent(agent_id)

        # Execute all refreshes concurrently
        tasks = [refresh_single(agent_id) for agent_id in agent_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        summaries = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Error refreshing agent: {result}")
            else:
                summaries.append(result)

        return summaries

    async def _load_registration_data(self, uri: str) -> Dict[str, Any]:
        """Load registration data from URI."""
        registration_file = await self._fetch_registration_file(uri)
        if registration_file is None:
            raise ValueError(f"Failed to load registration data from: {uri}")
        return registration_file

    def _create_agent_summary(
        self,
        chain_id: int,
        agent_id: AgentId,
        registration_data: Dict[str, Any]
    ) -> AgentSummary:
        """Create agent summary from registration data."""
        # Extract endpoints
        endpoints = registration_data.get("endpoints", [])
        mcp = any(ep.get("name") == "MCP" for ep in endpoints)
        a2a = any(ep.get("name") == "A2A" for ep in endpoints)
        
        ens = None
        did = None
        for ep in endpoints:
            if ep.get("name") == "ENS":
                ens = ep.get("endpoint")
            elif ep.get("name") == "DID":
                did = ep.get("endpoint")

        # Extract capabilities (would need MCP/A2A crawling)
        a2a_skills = []
        mcp_tools = []
        mcp_prompts = []
        mcp_resources = []

        return AgentSummary(
            chainId=chain_id,
            agentId=agent_id,
            name=registration_data.get("name", ""),
            image=registration_data.get("image"),
            description=registration_data.get("description", ""),
            owners=[],  # Would be populated from contract
            operators=[],  # Would be populated from contract
            mcp=mcp,
            a2a=a2a,
            ens=ens,
            did=did,
            walletAddress=registration_data.get("walletAddress"),
            supportedTrusts=registration_data.get("supportedTrust", []),
            a2aSkills=a2a_skills,
            mcpTools=mcp_tools,
            mcpPrompts=mcp_prompts,
            mcpResources=mcp_resources,
            active=registration_data.get("active", True),
            extras={}
        )

    async def _deep_refresh_agent(self, summary: AgentSummary):
        """Perform deep refresh of agent capabilities."""
        # This would crawl MCP/A2A endpoints to extract capabilities
        # For now, it's a placeholder
        pass

    def get_agent(self, agent_id: AgentId) -> AgentSummary:
        """Get agent summary from index."""
        # Parse chainId from agentId
        chain_id, token_id = self._parse_agent_id(agent_id)
        
        # Get subgraph client for the chain
        subgraph_client = None
        full_agent_id = agent_id
        
        if chain_id is not None:
            subgraph_client = self._get_subgraph_client_for_chain(chain_id)
        else:
            # No chainId in agentId, use SDK's default
            # Construct full agentId format for subgraph query
            default_chain_id = self.web3_client.chain_id
            full_agent_id = f"{default_chain_id}:{token_id}"
            subgraph_client = self.subgraph_client
        
        # Use subgraph if available (preferred)
        if subgraph_client:
            return self._get_agent_from_subgraph(full_agent_id, subgraph_client)
        
        # Fallback to local cache
        if agent_id not in self.store["agents"]:
            raise ValueError(f"Agent {agent_id} not found in index")
        return self.store["agents"][agent_id]
    
    def _get_agent_from_subgraph(self, agent_id: AgentId, subgraph_client: Optional[Any] = None) -> AgentSummary:
        """Get agent summary from subgraph."""
        # Use provided client or default
        client = subgraph_client or self.subgraph_client
        if not client:
            raise ValueError("No subgraph client available")
        
        try:
            agent_data = client.get_agent_by_id(agent_id)
            
            if agent_data is None:
                raise ValueError(f"Agent {agent_id} not found in subgraph")
            
            reg_file = agent_data.get('registrationFile') or {}
            if not isinstance(reg_file, dict):
                reg_file = {}
            
            return AgentSummary(
                chainId=int(agent_data.get('chainId', 0)),
                agentId=agent_data.get('id', agent_id),
                name=reg_file.get('name', f"Agent {agent_id}"),
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
                extras={}
            )
            
        except Exception as e:
            raise ValueError(f"Failed to get agent from subgraph: {e}")

    def search_agents(
        self,
        params: SearchParams,
        sort: List[str],
        page_size: int,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search for agents by querying the subgraph or blockchain."""
        # Handle "all" chains shorthand
        if params.chains == "all":
            params.chains = self._get_all_configured_chains()
            logger.info(f"Expanding 'all' to configured chains: {params.chains}")

        # If chains are explicitly specified (even a single chain), use multi-chain path
        # This ensures the correct subgraph client is used for the requested chain(s)
        if params.chains and len(params.chains) > 0:
            # Validate chains are configured
            available_chains = set(self._get_all_configured_chains())
            requested_chains = set(params.chains)
            invalid_chains = requested_chains - available_chains

            if invalid_chains:
                logger.warning(
                    f"Requested chains not configured: {invalid_chains}. "
                    f"Available chains: {available_chains}"
                )
                # Filter to valid chains only
                valid_chains = list(requested_chains & available_chains)
                if not valid_chains:
                    return {
                        "items": [],
                        "nextCursor": None,
                        "meta": {
                            "chains": list(requested_chains),
                            "successfulChains": [],
                            "failedChains": list(requested_chains),
                            "error": f"No valid chains configured. Available: {list(available_chains)}"
                        }
                    }
                params.chains = valid_chains

            return asyncio.run(
                self._search_agents_across_chains(params, sort, page_size, cursor)
            )

        # Use subgraph if available (preferred)
        if self.subgraph_client:
            return self._search_agents_via_subgraph(params, sort, page_size, cursor)

        # Fallback to blockchain queries
        return self._search_agents_via_blockchain(params, sort, page_size, cursor)

    async def _search_agents_across_chains(
        self,
        params: SearchParams,
        sort: List[str],
        page_size: int,
        cursor: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Search agents across multiple chains in parallel.

        This method is called when params.chains contains 2+ chain IDs.
        It executes one subgraph query per chain, all in parallel using asyncio.

        Args:
            params: Search parameters
            sort: Sort specification
            page_size: Number of results per page
            cursor: Pagination cursor
            timeout: Maximum time in seconds for all chain queries (default: 30.0)

        Returns:
            {
                "items": [agent_dict, ...],
                "nextCursor": str or None,
                "meta": {
                    "chains": [chainId, ...],
                    "successfulChains": [chainId, ...],
                    "failedChains": [chainId, ...],
                    "totalResults": int,
                    "timing": {"totalMs": int}
                }
            }
        """
        import time
        start_time = time.time()
        # Step 1: Determine which chains to query
        chains_to_query = params.chains if params.chains else self._get_all_configured_chains()

        if not chains_to_query or len(chains_to_query) == 0:
            logger.warning("No chains specified or configured for multi-chain query")
            return {"items": [], "nextCursor": None, "meta": {"chains": [], "successfulChains": [], "failedChains": []}}

        # Step 2: Parse pagination cursor (if any)
        chain_cursors = self._parse_multi_chain_cursor(cursor)
        global_offset = chain_cursors.get("_global_offset", 0)

        # Step 3: Define async function for querying a single chain
        async def query_single_chain(chain_id: int) -> Dict[str, Any]:
            """Query one chain and return its results with metadata."""
            try:
                # Get subgraph client for this chain
                subgraph_client = self._get_subgraph_client_for_chain(chain_id)

                if subgraph_client is None:
                    logger.warning(f"No subgraph client available for chain {chain_id}")
                    return {
                        "chainId": chain_id,
                        "status": "unavailable",
                        "agents": [],
                        "error": f"No subgraph configured for chain {chain_id}"
                    }

                # Build WHERE clause for this chain's query
                # (reuse existing logic from _search_agents_via_subgraph)
                where_clause = {}
                reg_file_where = {}

                if params.name is not None:
                    reg_file_where["name_contains"] = params.name
                if params.active is not None:
                    reg_file_where["active"] = params.active
                if params.x402support is not None:
                    reg_file_where["x402support"] = params.x402support
                if params.mcp is not None:
                    if params.mcp:
                        reg_file_where["mcpEndpoint_not"] = None
                    else:
                        reg_file_where["mcpEndpoint"] = None
                if params.a2a is not None:
                    if params.a2a:
                        reg_file_where["a2aEndpoint_not"] = None
                    else:
                        reg_file_where["a2aEndpoint"] = None
                if params.ens is not None:
                    reg_file_where["ens"] = params.ens
                if params.did is not None:
                    reg_file_where["did"] = params.did
                if params.walletAddress is not None:
                    reg_file_where["agentWallet"] = params.walletAddress

                if reg_file_where:
                    where_clause["registrationFile_"] = reg_file_where

                # Owner filtering
                if params.owners is not None and len(params.owners) > 0:
                    normalized_owners = [owner.lower() for owner in params.owners]
                    if len(normalized_owners) == 1:
                        where_clause["owner"] = normalized_owners[0]
                    else:
                        where_clause["owner_in"] = normalized_owners

                # Operator filtering
                if params.operators is not None and len(params.operators) > 0:
                    normalized_operators = [op.lower() for op in params.operators]
                    where_clause["operators_contains"] = normalized_operators

                # Get pagination offset for this chain (not used in multi-chain, fetch all)
                skip = 0

                # Execute subgraph query
                agents = subgraph_client.get_agents(
                    where=where_clause if where_clause else None,
                    first=page_size * 3,  # Fetch extra to allow for filtering/sorting
                    skip=skip,
                    order_by=self._extract_order_by(sort),
                    order_direction=self._extract_order_direction(sort)
                )

                logger.info(f"Chain {chain_id}: fetched {len(agents)} agents")

                return {
                    "chainId": chain_id,
                    "status": "success",
                    "agents": agents,
                    "count": len(agents),
                }

            except Exception as e:
                logger.error(f"Error querying chain {chain_id}: {e}", exc_info=True)
                return {
                    "chainId": chain_id,
                    "status": "error",
                    "agents": [],
                    "error": str(e)
                }

        # Step 4: Execute all chain queries in parallel with timeout
        logger.info(f"Querying {len(chains_to_query)} chains in parallel: {chains_to_query}")
        tasks = [query_single_chain(chain_id) for chain_id in chains_to_query]

        try:
            chain_results = await asyncio.wait_for(
                asyncio.gather(*tasks),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Multi-chain query timed out after {timeout}s")
            # Collect results from completed tasks
            chain_results = []
            for task in tasks:
                if task.done():
                    try:
                        chain_results.append(task.result())
                    except Exception as e:
                        logger.warning(f"Task failed: {e}")
                else:
                    # Task didn't complete - mark as timeout
                    chain_results.append({
                        "chainId": None,
                        "status": "timeout",
                        "agents": [],
                        "error": f"Query timed out after {timeout}s"
                    })

        # Step 5: Extract successful results and track failures
        all_agents = []
        successful_chains = []
        failed_chains = []

        for result in chain_results:
            chain_id = result["chainId"]

            if result["status"] == "success":
                successful_chains.append(chain_id)
                all_agents.extend(result["agents"])
            else:
                failed_chains.append(chain_id)
                logger.warning(
                    f"Chain {chain_id} query failed: {result.get('error', 'Unknown error')}"
                )

        logger.info(f"Multi-chain query: {len(successful_chains)} successful, {len(failed_chains)} failed, {len(all_agents)} total agents")

        # If ALL chains failed, raise error
        if len(successful_chains) == 0:
            raise ConnectionError(
                f"All chains failed: {', '.join(str(c) for c in failed_chains)}"
            )

        # Step 6: Apply cross-chain filtering (for fields not supported by subgraph WHERE clause)
        filtered_agents = self._apply_cross_chain_filters(all_agents, params)
        logger.info(f"After cross-chain filters: {len(filtered_agents)} agents")

        # Step 7: Deduplicate if requested
        deduplicated_agents = self._deduplicate_agents_cross_chain(filtered_agents, params)
        logger.info(f"After deduplication: {len(deduplicated_agents)} agents")

        # Step 8: Sort across chains
        sorted_agents = self._sort_agents_cross_chain(deduplicated_agents, sort)
        logger.info(f"After sorting: {len(sorted_agents)} agents")

        # Step 9: Apply pagination
        start_idx = global_offset
        paginated_agents = sorted_agents[start_idx:start_idx + page_size]

        # Step 10: Convert to result format (keep as dicts, SDK will convert to AgentSummary)
        results = []
        for agent_data in paginated_agents:
            reg_file = agent_data.get('registrationFile') or {}
            if not isinstance(reg_file, dict):
                reg_file = {}

            result_agent = {
                "agentId": agent_data.get('id'),
                "chainId": agent_data.get('chainId'),
                "name": reg_file.get('name', f"Agent {agent_data.get('agentId')}"),
                "description": reg_file.get('description', ''),
                "image": reg_file.get('image'),
                "owner": agent_data.get('owner'),
                "operators": agent_data.get('operators', []),
                "mcp": reg_file.get('mcpEndpoint') is not None,
                "a2a": reg_file.get('a2aEndpoint') is not None,
                "ens": reg_file.get('ens'),
                "did": reg_file.get('did'),
                "walletAddress": reg_file.get('agentWallet'),
                "supportedTrusts": reg_file.get('supportedTrusts', []),
                "a2aSkills": reg_file.get('a2aSkills', []),
                "mcpTools": reg_file.get('mcpTools', []),
                "mcpPrompts": reg_file.get('mcpPrompts', []),
                "mcpResources": reg_file.get('mcpResources', []),
                "active": reg_file.get('active', True),
                "x402support": reg_file.get('x402support', False),
                "totalFeedback": agent_data.get('totalFeedback', 0),
                "lastActivity": agent_data.get('lastActivity'),
                "updatedAt": agent_data.get('updatedAt'),
                "extras": {}
            }

            # Add deployedOn if deduplication was used
            if 'deployedOn' in agent_data:
                result_agent['extras']['deployedOn'] = agent_data['deployedOn']

            results.append(result_agent)

        # Step 11: Calculate next cursor
        next_cursor = None
        if len(sorted_agents) > start_idx + page_size:
            # More results available
            next_cursor = self._create_multi_chain_cursor(
                global_offset=start_idx + page_size
            )

        # Step 12: Build response with metadata
        query_time = time.time() - start_time

        return {
            "items": results,
            "nextCursor": next_cursor,
            "meta": {
                "chains": chains_to_query,
                "successfulChains": successful_chains,
                "failedChains": failed_chains,
                "totalResults": len(sorted_agents),
                "pageResults": len(results),
                "timing": {
                    "totalMs": int(query_time * 1000),
                    "averagePerChainMs": int(query_time * 1000 / len(chains_to_query)) if chains_to_query else 0,
                }
            }
        }

    def _search_agents_via_subgraph(
        self,
        params: SearchParams,
        sort: List[str],
        page_size: int,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search for agents using the subgraph."""
        # Build subgraph query filters
        where_clause = {}
        reg_file_where = {}
        
        if params.name is not None:
            reg_file_where["name_contains"] = params.name
        if params.active is not None:
            reg_file_where["active"] = params.active
        if params.x402support is not None:
            reg_file_where["x402support"] = params.x402support
        if params.mcp is not None:
            if params.mcp:
                reg_file_where["mcpEndpoint_not"] = None
            else:
                reg_file_where["mcpEndpoint"] = None
        if params.a2a is not None:
            if params.a2a:
                reg_file_where["a2aEndpoint_not"] = None
            else:
                reg_file_where["a2aEndpoint"] = None
        if params.ens is not None:
            reg_file_where["ens"] = params.ens
        if params.did is not None:
            reg_file_where["did"] = params.did
        if params.walletAddress is not None:
            reg_file_where["agentWallet"] = params.walletAddress

        if reg_file_where:
            where_clause["registrationFile_"] = reg_file_where

        # Owner filtering
        if params.owners is not None and len(params.owners) > 0:
            # Normalize addresses to lowercase for case-insensitive matching
            normalized_owners = [owner.lower() for owner in params.owners]
            if len(normalized_owners) == 1:
                where_clause["owner"] = normalized_owners[0]
            else:
                where_clause["owner_in"] = normalized_owners

        # Operator filtering 
        if params.operators is not None and len(params.operators) > 0:
            # Normalize addresses to lowercase for case-insensitive matching
            normalized_operators = [op.lower() for op in params.operators]
            # For operators (array field), use contains to check if any operator matches
            where_clause["operators_contains"] = normalized_operators
        
        # Calculate pagination
        skip = 0
        if cursor:
            try:
                skip = int(cursor)
            except ValueError:
                skip = 0
        
        # Determine sort
        order_by = "createdAt"
        order_direction = "desc"
        if sort and len(sort) > 0:
            sort_field = sort[0].split(":")
            if len(sort_field) >= 1:
                order_by = sort_field[0]
            if len(sort_field) >= 2:
                order_direction = sort_field[1]
        
        try:
            agents = self.subgraph_client.get_agents(
                where=where_clause if where_clause else None,
                first=page_size,
                skip=skip,
                order_by=order_by,
                order_direction=order_direction
            )
            
            results = []
            for agent in agents:
                reg_file = agent.get('registrationFile') or {}
                # Ensure reg_file is a dict
                if not isinstance(reg_file, dict):
                    reg_file = {}
                    
                agent_data = {
                    "agentId": agent.get('id'),
                    "chainId": agent.get('chainId'),
                    "name": reg_file.get('name', f"Agent {agent.get('agentId')}"),
                    "description": reg_file.get('description', ''),
                    "image": reg_file.get('image'),
                    "owner": agent.get('owner'),
                    "operators": agent.get('operators', []),
                    "mcp": reg_file.get('mcpEndpoint') is not None,
                    "a2a": reg_file.get('a2aEndpoint') is not None,
                    "ens": reg_file.get('ens'),
                    "did": reg_file.get('did'),
                    "walletAddress": reg_file.get('agentWallet'),
                    "supportedTrusts": reg_file.get('supportedTrusts', []),
                    "a2aSkills": reg_file.get('a2aSkills', []),
                    "mcpTools": reg_file.get('mcpTools', []),
                    "mcpPrompts": reg_file.get('mcpPrompts', []),
                    "mcpResources": reg_file.get('mcpResources', []),
                    "active": reg_file.get('active', True),
                    "x402support": reg_file.get('x402support', False),
                    "totalFeedback": agent.get('totalFeedback', 0),
                    "lastActivity": agent.get('lastActivity'),
                    "updatedAt": agent.get('updatedAt'),
                    "extras": {}
                }
                
                if params.chains is not None:
                    if agent_data["chainId"] not in params.chains:
                        continue
                if params.supportedTrust is not None:
                    if not any(trust in agent_data["supportedTrusts"] for trust in params.supportedTrust):
                        continue
                
                results.append(agent_data)
            
            next_cursor = str(skip + len(results)) if len(results) == page_size else None
            return {"items": results, "nextCursor": next_cursor}
            
        except Exception as e:
            logger.warning(f"Subgraph search failed: {e}")
            return {"items": [], "nextCursor": None}
    
    def _search_agents_via_blockchain(
        self,
        params: SearchParams,
        sort: List[str],
        page_size: int,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search for agents by querying the blockchain (fallback)."""
        return {"items": [], "nextCursor": None}

    def _apply_filters(self, agents: List[Dict[str, Any]], params: SearchParams) -> List[Dict[str, Any]]:
        """Apply search filters to agents."""
        filtered = agents
        
        if params.chains is not None:
            filtered = [a for a in filtered if a.get("chainId") in params.chains]
        
        if params.name is not None:
            filtered = [a for a in filtered if params.name.lower() in a.get("name", "").lower()]
        
        if params.description is not None:
            # This would use semantic search with embeddings
            filtered = [a for a in filtered if params.description.lower() in a.get("description", "").lower()]
        
        if params.owners is not None:
            filtered = [a for a in filtered if any(owner in params.owners for owner in a.get("owners", []))]
        
        if params.operators is not None:
            filtered = [a for a in filtered if any(op in params.operators for op in a.get("operators", []))]
        
        if params.mcp is not None:
            filtered = [a for a in filtered if a.get("mcp") == params.mcp]
        
        if params.a2a is not None:
            filtered = [a for a in filtered if a.get("a2a") == params.a2a]
        
        if params.ens is not None:
            filtered = [a for a in filtered if a.get("ens") and params.ens.lower() in a.get("ens", "").lower()]
        
        if params.did is not None:
            filtered = [a for a in filtered if a.get("did") == params.did]
        
        if params.walletAddress is not None:
            filtered = [a for a in filtered if a.get("walletAddress") == params.walletAddress]
        
        if params.supportedTrust is not None:
            filtered = [a for a in filtered if any(trust in params.supportedTrust for trust in a.get("supportedTrusts", []))]
        
        if params.a2aSkills is not None:
            filtered = [a for a in filtered if any(skill in params.a2aSkills for skill in a.get("a2aSkills", []))]
        
        if params.mcpTools is not None:
            filtered = [a for a in filtered if any(tool in params.mcpTools for tool in a.get("mcpTools", []))]
        
        if params.mcpPrompts is not None:
            filtered = [a for a in filtered if any(prompt in params.mcpPrompts for prompt in a.get("mcpPrompts", []))]
        
        if params.mcpResources is not None:
            filtered = [a for a in filtered if any(resource in params.mcpResources for resource in a.get("mcpResources", []))]
        
        if params.active is not None:
            filtered = [a for a in filtered if a.get("active") == params.active]
        
        if params.x402support is not None:
            filtered = [a for a in filtered if a.get("x402support") == params.x402support]
        
        return filtered

    def _apply_sorting(self, agents: List[AgentSummary], sort: List[str]) -> List[AgentSummary]:
        """Apply sorting to agents."""
        def sort_key(agent):
            key_values = []
            for sort_field in sort:
                field, direction = sort_field.split(":", 1)
                if hasattr(agent, field):
                    value = getattr(agent, field)
                    if direction == "desc":
                        value = -value if isinstance(value, (int, float)) else value
                    key_values.append(value)
            return key_values
        
        return sorted(agents, key=sort_key)

    def get_feedback(
        self,
        agentId: AgentId,
        clientAddress: Address,
        feedbackIndex: int,
    ) -> Feedback:
        """Get single feedback by agent ID, client address, and index."""
        # Use subgraph if available (preferred)
        if self.subgraph_client:
            return self._get_feedback_from_subgraph(agentId, clientAddress, feedbackIndex)
        
        # Fallback to local store (if populated in future)
        # For now, raise error if subgraph unavailable
        feedback_id = Feedback.create_id(agentId, clientAddress, feedbackIndex)
        if feedback_id not in self.store["feedback"]:
            raise ValueError(f"Feedback {feedback_id} not found (subgraph required)")
        return self.store["feedback"][feedback_id]
    
    def _get_feedback_from_subgraph(
        self,
        agentId: AgentId,
        clientAddress: Address,
        feedbackIndex: int,
    ) -> Feedback:
        """Get feedback from subgraph."""
        # Normalize addresses to lowercase for consistent storage
        normalized_client_address = self.web3_client.normalize_address(clientAddress)
        
        # Build feedback ID in format: chainId:agentId:clientAddress:feedbackIndex
        if ":" in agentId:
            feedback_id = f"{agentId}:{normalized_client_address}:{feedbackIndex}"
        else:
            chain_id = str(self.web3_client.chain_id)
            feedback_id = f"{chain_id}:{agentId}:{normalized_client_address}:{feedbackIndex}"
        
        try:
            feedback_data = self.subgraph_client.get_feedback_by_id(feedback_id)
            
            if feedback_data is None:
                raise ValueError(f"Feedback {feedback_id} not found in subgraph")
            
            return self._map_subgraph_feedback_to_model(feedback_data, agentId, clientAddress, feedbackIndex)
            
        except Exception as e:
            raise ValueError(f"Failed to get feedback from subgraph: {e}")
    
    def _map_subgraph_feedback_to_model(
        self,
        feedback_data: Dict[str, Any],
        agentId: AgentId,
        clientAddress: Address,
        feedbackIndex: int,
    ) -> Feedback:
        """Map subgraph feedback data to Feedback model."""
        feedback_file = feedback_data.get('feedbackFile') or {}
        if not isinstance(feedback_file, dict):
            feedback_file = {}
        
        # Map responses
        responses_data = feedback_data.get('responses', [])
        answers = []
        for resp in responses_data:
            answers.append({
                'responder': resp.get('responder'),
                'responseURI': resp.get('responseURI') or resp.get('responseUri'),  # Handle both old and new field names
                'responseHash': resp.get('responseHash'),
                'createdAt': resp.get('createdAt')
            })
        
        # Map tags - tags are now strings (not bytes32)
        tags = []
        tag1 = feedback_data.get('tag1') or feedback_file.get('tag1')
        tag2 = feedback_data.get('tag2') or feedback_file.get('tag2')
        
        # Tags are now plain strings, but handle backward compatibility with hex bytes32
        if tag1:
            if isinstance(tag1, str) and not tag1.startswith("0x"):
                tags.append(tag1)
            elif isinstance(tag1, str) and tag1.startswith("0x"):
                # Try to convert from hex bytes32 (old format)
                try:
                    hex_bytes = bytes.fromhex(tag1[2:])
                    tag1_str = hex_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore')
                    if tag1_str:
                        tags.append(tag1_str)
                except Exception:
                    pass  # Ignore invalid hex strings
        
        if tag2:
            if isinstance(tag2, str) and not tag2.startswith("0x"):
                tags.append(tag2)
            elif isinstance(tag2, str) and tag2.startswith("0x"):
                # Try to convert from hex bytes32 (old format)
                try:
                    hex_bytes = bytes.fromhex(tag2[2:])
                    tag2_str = hex_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore')
                    if tag2_str:
                        tags.append(tag2_str)
                except Exception:
                    pass  # Ignore invalid hex strings
        
        return Feedback(
            id=Feedback.create_id(agentId, clientAddress, feedbackIndex),
            agentId=agentId,
            reviewer=self.web3_client.normalize_address(clientAddress),
            score=feedback_data.get('score'),
            tags=tags,
            text=feedback_file.get('text'),
            capability=feedback_file.get('capability'),
            context=feedback_file.get('context'),
            proofOfPayment={
                'fromAddress': feedback_file.get('proofOfPaymentFromAddress'),
                'toAddress': feedback_file.get('proofOfPaymentToAddress'),
                'chainId': feedback_file.get('proofOfPaymentChainId'),
                'txHash': feedback_file.get('proofOfPaymentTxHash'),
            } if feedback_file.get('proofOfPaymentFromAddress') else None,
            fileURI=feedback_data.get('feedbackURI') or feedback_data.get('feedbackUri'),  # Handle both old and new field names
            endpoint=feedback_data.get('endpoint'),
            createdAt=feedback_data.get('createdAt', int(time.time())),
            answers=answers,
            isRevoked=feedback_data.get('isRevoked', False),
            name=feedback_file.get('name'),
            skill=feedback_file.get('skill'),
            task=feedback_file.get('task'),
        )
    
    def search_feedback(
        self,
        agentId: AgentId,
        clientAddresses: Optional[List[Address]] = None,
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
        """Search feedback for an agent - uses subgraph if available."""
        # Parse chainId from agentId
        chain_id, token_id = self._parse_agent_id(agentId)
        
        # Get subgraph client for the chain
        subgraph_client = None
        full_agent_id = agentId
        
        if chain_id is not None:
            subgraph_client = self._get_subgraph_client_for_chain(chain_id)
        else:
            # No chainId in agentId, use SDK's default
            # Construct full agentId format for subgraph query
            default_chain_id = self.web3_client.chain_id
            full_agent_id = f"{default_chain_id}:{token_id}"
            subgraph_client = self.subgraph_client
        
        # Use subgraph if available (preferred)
        if subgraph_client:
            return self._search_feedback_subgraph(
                full_agent_id, clientAddresses, tags, capabilities, skills, tasks, names,
                minScore, maxScore, include_revoked, first, skip, subgraph_client
            )
        
        # Fallback not implemented (would require blockchain queries)
        # For now, return empty if subgraph unavailable
        return []
    
    def _search_feedback_subgraph(
        self,
        agentId: AgentId,
        clientAddresses: Optional[List[Address]],
        tags: Optional[List[str]],
        capabilities: Optional[List[str]],
        skills: Optional[List[str]],
        tasks: Optional[List[str]],
        names: Optional[List[str]],
        minScore: Optional[int],
        maxScore: Optional[int],
        include_revoked: bool,
        first: int,
        skip: int,
        subgraph_client: Optional[Any] = None,
    ) -> List[Feedback]:
        """Search feedback using subgraph."""
        # Use provided client or default
        client = subgraph_client or self.subgraph_client
        if not client:
            return []
        
        # Create SearchFeedbackParams
        params = SearchFeedbackParams(
            agents=[agentId],
            reviewers=clientAddresses,
            tags=tags,
            capabilities=capabilities,
            skills=skills,
            tasks=tasks,
            names=names,
            minScore=minScore,
            maxScore=maxScore,
            includeRevoked=include_revoked
        )
        
        # Query subgraph
        feedbacks_data = client.search_feedback(
            params=params,
            first=first,
            skip=skip,
            order_by="createdAt",
            order_direction="desc"
        )
        
        # Map to Feedback objects
        feedbacks = []
        for fb_data in feedbacks_data:
            # Parse agentId from feedback ID
            feedback_id = fb_data['id']
            parts = feedback_id.split(':')
            if len(parts) >= 2:
                agent_id_str = f"{parts[0]}:{parts[1]}"
                client_addr = parts[2] if len(parts) > 2 else ""
                feedback_idx = int(parts[3]) if len(parts) > 3 else 1
            else:
                agent_id_str = feedback_id
                client_addr = ""
                feedback_idx = 1
            
            feedback = self._map_subgraph_feedback_to_model(
                fb_data, agent_id_str, client_addr, feedback_idx
            )
            feedbacks.append(feedback)
        
        return feedbacks
    
    def _hexBytes32ToTags(self, tag1: str, tag2: str) -> List[str]:
        """Convert hex bytes32 tags back to strings, or return plain strings as-is.
        
        The subgraph now stores tags as human-readable strings (not hex),
        so this method handles both formats for backwards compatibility.
        """
        tags = []
        
        if tag1 and tag1 != "0x" + "00" * 32:
            # If it's already a plain string (from subgraph), use it directly
            if not tag1.startswith("0x"):
                if tag1:
                    tags.append(tag1)
            else:
                # Try to convert from hex bytes32 (on-chain format)
                try:
                    hex_bytes = bytes.fromhex(tag1[2:])
                    tag1_str = hex_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore')
                    if tag1_str:
                        tags.append(tag1_str)
                except Exception:
                    pass  # Ignore invalid hex strings
        
        if tag2 and tag2 != "0x" + "00" * 32:
            # If it's already a plain string (from subgraph), use it directly
            if not tag2.startswith("0x"):
                if tag2:
                    tags.append(tag2)
            else:
                # Try to convert from hex bytes32 (on-chain format)
                try:
                    if tag2.startswith("0x"):
                        hex_bytes = bytes.fromhex(tag2[2:])
                    else:
                        hex_bytes = bytes.fromhex(tag2)
                    tag2_str = hex_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore')
                    if tag2_str:
                        tags.append(tag2_str)
                except Exception:
                    pass  # Ignore invalid hex strings
        
        return tags

    def get_reputation_summary(
        self,
        agent_id: AgentId,
        group_by: List[str],
        reviewers: Optional[List[Address]] = None,
        since: Optional[Timestamp] = None,
        until: Optional[Timestamp] = None,
        sort: List[str] = None,
        page_size: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get reputation summary for an agent."""
        # This would aggregate feedback data
        # For now, return empty result
        return {
            "groups": [],
            "nextCursor": None
        }

    def get_reputation_map(
        self,
        agents: List[Union[AgentSummary, AgentId]],
        filters: Dict[str, Any],
        sort: List[str],
        reviewers: Optional[List[Address]] = None,
    ) -> List[Dict[str, Any]]:
        """Get reputation map for multiple agents."""
        # This would calculate reputation metrics for each agent
        # For now, return empty result
        return []

    def _get_agent_from_blockchain(self, token_id: int, sdk) -> Optional[Dict[str, Any]]:
        """Get agent data from blockchain."""
        try:
            # Get agent URI from contract (using ERC-721 tokenURI function)
            agent_uri = self.web3_client.call_contract(
                sdk.identity_registry,
                "tokenURI",  # ERC-721 standard function name, but represents agentURI
                token_id
            )
            
            # Get owner
            owner = self.web3_client.call_contract(
                sdk.identity_registry,
                "ownerOf",
                token_id
            )
            
            # Get agentWallet using new dedicated function
            wallet_address = None
            try:
                wallet_address = self.web3_client.call_contract(
                    sdk.identity_registry,
                    "getAgentWallet",
                    token_id
                )
                if wallet_address == "0x0000000000000000000000000000000000000000":
                    wallet_address = None
            except Exception:
                # Fallback to registration file if getAgentWallet not available
                pass
            
            # Create agent ID
            agent_id = f"{sdk.chain_id}:{token_id}"
            
            # Try to load registration data from IPFS
            registration_data = self._load_registration_from_ipfs(agent_uri, sdk)
            
            if registration_data:
                # Use data from IPFS, but prefer on-chain wallet if available
                return {
                    "agentId": agent_id,
                    "name": registration_data.get("name", f"Agent {token_id}"),
                    "description": registration_data.get("description", f"Agent registered with token ID {token_id}"),
                    "owner": owner,
                    "tokenId": token_id,
                    "agentURI": agent_uri,  # Updated field name
                    "x402support": registration_data.get("x402Support", registration_data.get("x402support", False)),
                    "trustModels": registration_data.get("trustModels", ["reputation"]),
                    "active": registration_data.get("active", True),
                    "endpoints": registration_data.get("endpoints", []),
                    "image": registration_data.get("image"),
                    "walletAddress": wallet_address or registration_data.get("walletAddress"),  # Prefer on-chain wallet
                    "metadata": registration_data.get("metadata", {})
                }
            else:
                # Fallback to basic data
                return {
                    "agentId": agent_id,
                    "name": f"Agent {token_id}",
                    "description": f"Agent registered with token ID {token_id}",
                    "owner": owner,
                    "tokenId": token_id,
                    "agentURI": agent_uri,  # Updated field name
                    "x402support": False,
                    "trustModels": ["reputation"],
                    "active": True,
                    "endpoints": [],
                    "image": None,
                    "walletAddress": wallet_address,
                    "metadata": {}
                }
        except Exception as e:
            logger.error(f"Error loading agent {token_id}: {e}")
            return None

    def _load_registration_from_ipfs(self, token_uri: str, sdk) -> Optional[Dict[str, Any]]:
        """Load agent registration data from IPFS or HTTP gateway."""
        try:
            import json
            import requests
            
            # Extract IPFS hash from token URI
            if token_uri.startswith("ipfs://"):
                ipfs_hash = token_uri[7:]  # Remove "ipfs://" prefix
            elif token_uri.startswith("https://") and "ipfs" in token_uri:
                # Extract hash from IPFS gateway URL
                parts = token_uri.split("/")
                ipfs_hash = parts[-1] if parts[-1] else parts[-2]
            elif token_uri.startswith("https://"):
                # Direct HTTP URL - try to fetch directly
                try:
                    response = requests.get(token_uri, timeout=10)
                    response.raise_for_status()
                    return response.json()
                except Exception as e:
                    logger.warning(f"Could not load HTTP data from {token_uri}: {e}")
                    return None
            else:
                return None
            
            # Try local IPFS client first (if available)
            if hasattr(sdk, 'ipfs_client') and sdk.ipfs_client is not None:
                try:
                    data = sdk.ipfs_client.get(ipfs_hash)
                    if data:
                        return json.loads(data)
                except Exception as e:
                    logger.warning(f"Could not load from local IPFS for {ipfs_hash}: {e}")
            
            # Fallback to IPFS HTTP gateways
            gateways = [
                f"https://ipfs.io/ipfs/{ipfs_hash}",
                f"https://gateway.pinata.cloud/ipfs/{ipfs_hash}",
                f"https://cloudflare-ipfs.com/ipfs/{ipfs_hash}",
                f"https://dweb.link/ipfs/{ipfs_hash}"
            ]
            
            for gateway_url in gateways:
                try:
                    response = requests.get(gateway_url, timeout=10)
                    response.raise_for_status()
                    return response.json()
                except Exception as e:
                    logger.debug(f"Could not load from {gateway_url}: {e}")
                    continue
            
            logger.warning(f"Could not load data for {ipfs_hash} from any source")
            return None
                
        except Exception as e:
            logger.warning(f"Could not parse token URI {token_uri}: {e}")
            return None

    def _get_subgraph_client_for_chain(self, chain_id: int):
        """
        Get or create SubgraphClient for a specific chain.

        Checks (in order):
        1. Client cache (already created)
        2. Subgraph URL overrides (from constructor)
        3. DEFAULT_SUBGRAPH_URLS (from contracts.py)
        4. Environment variables (SUBGRAPH_URL_<chainId>)

        Returns None if no subgraph URL is available for this chain.
        """
        # Check cache first
        if chain_id in self._subgraph_client_cache:
            return self._subgraph_client_cache[chain_id]

        # Get subgraph URL for this chain
        subgraph_url = self._get_subgraph_url_for_chain(chain_id)

        if subgraph_url is None:
            logger.warning(f"No subgraph URL configured for chain {chain_id}")
            return None

        # Create new SubgraphClient
        from .subgraph_client import SubgraphClient
        client = SubgraphClient(subgraph_url)

        # Cache for future use
        self._subgraph_client_cache[chain_id] = client

        logger.info(f"Created subgraph client for chain {chain_id}: {subgraph_url}")

        return client

    def _get_subgraph_url_for_chain(self, chain_id: int) -> Optional[str]:
        """
        Get subgraph URL for a specific chain.

        Priority order:
        1. Constructor-provided overrides (self.subgraph_url_overrides)
        2. DEFAULT_SUBGRAPH_URLS from contracts.py
        3. Environment variable SUBGRAPH_URL_<chainId>
        4. None (not configured)
        """
        import os

        # 1. Check constructor overrides
        if chain_id in self.subgraph_url_overrides:
            return self.subgraph_url_overrides[chain_id]

        # 2. Check DEFAULT_SUBGRAPH_URLS
        from .contracts import DEFAULT_SUBGRAPH_URLS
        if chain_id in DEFAULT_SUBGRAPH_URLS:
            return DEFAULT_SUBGRAPH_URLS[chain_id]

        # 3. Check environment variable
        env_key = f"SUBGRAPH_URL_{chain_id}"
        env_url = os.environ.get(env_key)
        if env_url:
            logger.info(f"Using subgraph URL from environment: {env_key}={env_url}")
            return env_url

        # 4. Not found
        return None

    def _parse_agent_id(self, agent_id: AgentId) -> tuple[Optional[int], str]:
        """
        Parse agentId to extract chainId and tokenId.
        
        Returns:
            (chain_id, token_id_str) where:
            - chain_id: int if "chainId:tokenId" format, None if just "tokenId"
            - token_id_str: the tokenId part (always present)
        """
        if ":" in agent_id:
            parts = agent_id.split(":", 1)
            try:
                chain_id = int(parts[0])
                token_id = parts[1]
                return (chain_id, token_id)
            except ValueError:
                # Invalid chainId, treat as tokenId only
                return (None, agent_id)
        return (None, agent_id)

    def _get_all_configured_chains(self) -> List[int]:
        """
        Get list of all chains that have subgraphs configured.

        This is used when params.chains is None (query all available chains).
        """
        import os
        from .contracts import DEFAULT_SUBGRAPH_URLS

        chains = set()

        # Add chains from DEFAULT_SUBGRAPH_URLS
        chains.update(DEFAULT_SUBGRAPH_URLS.keys())

        # Add chains from constructor overrides
        chains.update(self.subgraph_url_overrides.keys())

        # Add chains from environment variables
        for key, value in os.environ.items():
            if key.startswith("SUBGRAPH_URL_") and value:
                try:
                    chain_id = int(key.replace("SUBGRAPH_URL_", ""))
                    chains.add(chain_id)
                except ValueError:
                    pass

        return sorted(list(chains))

    def _apply_cross_chain_filters(
        self,
        agents: List[Dict[str, Any]],
        params: SearchParams
    ) -> List[Dict[str, Any]]:
        """
        Apply filters that couldn't be expressed in subgraph WHERE clause.

        Most filters are already applied by the subgraph query, but some
        (like supportedTrust, mcpTools, etc.) need post-processing.
        """
        filtered = agents

        # Filter by supportedTrust (if specified)
        if params.supportedTrust is not None:
            filtered = [
                agent for agent in filtered
                if any(
                    trust in agent.get('registrationFile', {}).get('supportedTrusts', [])
                    for trust in params.supportedTrust
                )
            ]

        # Filter by mcpTools (if specified)
        if params.mcpTools is not None:
            filtered = [
                agent for agent in filtered
                if any(
                    tool in agent.get('registrationFile', {}).get('mcpTools', [])
                    for tool in params.mcpTools
                )
            ]

        # Filter by a2aSkills (if specified)
        if params.a2aSkills is not None:
            filtered = [
                agent for agent in filtered
                if any(
                    skill in agent.get('registrationFile', {}).get('a2aSkills', [])
                    for skill in params.a2aSkills
                )
            ]

        # Filter by mcpPrompts (if specified)
        if params.mcpPrompts is not None:
            filtered = [
                agent for agent in filtered
                if any(
                    prompt in agent.get('registrationFile', {}).get('mcpPrompts', [])
                    for prompt in params.mcpPrompts
                )
            ]

        # Filter by mcpResources (if specified)
        if params.mcpResources is not None:
            filtered = [
                agent for agent in filtered
                if any(
                    resource in agent.get('registrationFile', {}).get('mcpResources', [])
                    for resource in params.mcpResources
                )
            ]

        return filtered

    def _deduplicate_agents_cross_chain(
        self,
        agents: List[Dict[str, Any]],
        params: SearchParams
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate agents across chains (if requested).

        Strategy:
        - By default, DON'T deduplicate (agents on different chains are different entities)
        - If params.deduplicate_cross_chain=True, deduplicate by (owner, registration_hash)

        When deduplicating:
        - Keep the first instance encountered
        - Add 'deployedOn' array with all chain IDs where this agent exists
        """
        # Check if deduplication requested
        if not params.deduplicate_cross_chain:
            return agents

        # Group agents by identity key
        seen = {}
        deduplicated = []

        for agent in agents:
            # Create identity key: (owner, name, description)
            # This identifies "the same agent" across chains
            owner = agent.get('owner', '').lower()
            reg_file = agent.get('registrationFile', {})
            name = reg_file.get('name', '')
            description = reg_file.get('description', '')

            identity_key = (owner, name, description)

            if identity_key not in seen:
                # First time seeing this agent
                seen[identity_key] = agent

                # Add deployedOn array
                agent['deployedOn'] = [agent['chainId']]

                deduplicated.append(agent)
            else:
                # Already seen this agent on another chain
                # Add this chain to deployedOn array
                seen[identity_key]['deployedOn'].append(agent['chainId'])

        logger.info(
            f"Deduplication: {len(agents)} agents → {len(deduplicated)} unique agents"
        )

        return deduplicated

    def _sort_agents_cross_chain(
        self,
        agents: List[Dict[str, Any]],
        sort: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Sort agents from multiple chains.

        Supports sorting by:
        - createdAt (timestamp)
        - updatedAt (timestamp)
        - totalFeedback (count)
        - name (alphabetical)
        - averageScore (reputation, if available)
        """
        if not sort or len(sort) == 0:
            # Default: sort by createdAt descending (newest first)
            return sorted(
                agents,
                key=lambda a: a.get('createdAt', 0),
                reverse=True
            )

        # Parse first sort specification
        sort_spec = sort[0]
        if ':' in sort_spec:
            field, direction = sort_spec.split(':', 1)
        else:
            field = sort_spec
            direction = 'desc'

        reverse = (direction.lower() == 'desc')

        # Define sort key function
        def get_sort_key(agent: Dict[str, Any]):
            if field == 'createdAt':
                return agent.get('createdAt', 0)

            elif field == 'updatedAt':
                return agent.get('updatedAt', 0)

            elif field == 'totalFeedback':
                return agent.get('totalFeedback', 0)

            elif field == 'name':
                reg_file = agent.get('registrationFile', {})
                return reg_file.get('name', '').lower()

            elif field == 'averageScore':
                # If reputation search was done, averageScore may be available
                return agent.get('averageScore', 0)

            else:
                logger.warning(f"Unknown sort field: {field}, defaulting to createdAt")
                return agent.get('createdAt', 0)

        return sorted(agents, key=get_sort_key, reverse=reverse)

    def _parse_multi_chain_cursor(self, cursor: Optional[str]) -> Dict[int, int]:
        """
        Parse multi-chain cursor into per-chain offsets.

        Cursor format (JSON):
        {
            "11155111": 50,  # Ethereum Sepolia offset
            "84532": 30,     # Base Sepolia offset
            "_global_offset": 100  # Total items returned so far
        }

        Returns:
            Dict mapping chainId → offset (default 0)
        """
        if not cursor:
            return {}

        try:
            cursor_data = json.loads(cursor)

            # Validate format
            if not isinstance(cursor_data, dict):
                logger.warning(f"Invalid cursor format: {cursor}, using empty")
                return {}

            return cursor_data

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse cursor: {e}, using empty")
            return {}

    def _create_multi_chain_cursor(
        self,
        global_offset: int,
    ) -> str:
        """
        Create multi-chain cursor for next page.

        Args:
            global_offset: Total items returned so far

        Returns:
            JSON string cursor
        """
        cursor_data = {
            "_global_offset": global_offset
        }

        return json.dumps(cursor_data)

    def _extract_order_by(self, sort: List[str]) -> str:
        """Extract order_by field from sort specification."""
        if not sort or len(sort) == 0:
            return "createdAt"

        sort_spec = sort[0]
        if ':' in sort_spec:
            field, _ = sort_spec.split(':', 1)
            return field
        return sort_spec

    def _extract_order_direction(self, sort: List[str]) -> str:
        """Extract order direction from sort specification."""
        if not sort or len(sort) == 0:
            return "desc"

        sort_spec = sort[0]
        if ':' in sort_spec:
            _, direction = sort_spec.split(':', 1)
            return direction
        return "desc"
