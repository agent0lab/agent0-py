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
    AgentSummary, Feedback, SearchFilters, SearchOptions, SearchFeedbackParams
)
from .web3_client import Web3Client

logger = logging.getLogger(__name__)

from .semantic_search_client import SemanticSearchClient


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
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
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
        registration_data = await self._load_registration_data(agent_uri)
        
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
        # Extract endpoints (legacy/non-subgraph path)
        endpoints = registration_data.get("endpoints", [])
        mcp: Optional[str] = None
        a2a: Optional[str] = None
        web: Optional[str] = None
        email: Optional[str] = None
        for ep in endpoints:
            name = (ep.get("name") or "").upper()
            value = ep.get("endpoint")
            if not isinstance(value, str):
                continue
            if name == "MCP":
                mcp = value
            elif name == "A2A":
                a2a = value
            elif name == "WEB":
                web = value
            elif name == "EMAIL":
                email = value
        
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
            web=web,
            email=email,
            ens=ens,
            did=did,
            walletAddress=registration_data.get("walletAddress"),
            supportedTrusts=registration_data.get("supportedTrust", []),
            a2aSkills=a2a_skills,
            mcpTools=mcp_tools,
            mcpPrompts=mcp_prompts,
            mcpResources=mcp_resources,
            oasfSkills=[],
            oasfDomains=[],
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
                mcp=reg_file.get('mcpEndpoint') or None,
                a2a=reg_file.get('a2aEndpoint') or None,
                web=reg_file.get('webEndpoint') or None,
                email=reg_file.get('emailEndpoint') or None,
                ens=reg_file.get('ens'),
                did=reg_file.get('did'),
                walletAddress=agent_data.get('agentWallet'),
                supportedTrusts=reg_file.get('supportedTrusts', []),
                a2aSkills=reg_file.get('a2aSkills', []),
                mcpTools=reg_file.get('mcpTools', []),
                mcpPrompts=reg_file.get('mcpPrompts', []),
                mcpResources=reg_file.get('mcpResources', []),
                oasfSkills=reg_file.get('oasfSkills', []) or [],
                oasfDomains=reg_file.get('oasfDomains', []) or [],
                active=reg_file.get('active', True),
                x402support=reg_file.get('x402Support', reg_file.get('x402support', False)),
                createdAt=agent_data.get('createdAt'),
                updatedAt=agent_data.get('updatedAt'),
                lastActivity=agent_data.get('lastActivity'),
                agentURI=agent_data.get('agentURI'),
                agentURIType=agent_data.get('agentURIType'),
                feedbackCount=agent_data.get('totalFeedback'),
                extras={}
            )
            
        except Exception as e:
            raise ValueError(f"Failed to get agent from subgraph: {e}")

    def search_agents(
        self,
        filters: SearchFilters,
        options: SearchOptions,
    ) -> List[AgentSummary]:
        """Unified search entry point (replaces all legacy search variants)."""
        if filters.keyword and str(filters.keyword).strip():
            return self._search_unified_with_keyword(filters, options)
        else:
            return self._search_unified_no_keyword(filters, options)

    # -------------------------------------------------------------------------
    # Unified search (v2)
    # -------------------------------------------------------------------------

    def _parse_sort(self, sort: Optional[List[str]], keyword_present: bool) -> tuple[str, str]:
        default = "semanticScore:desc" if keyword_present else "updatedAt:desc"
        spec = (sort[0] if sort and len(sort) > 0 else default) or default
        parts = spec.split(":", 1)
        field = parts[0] if parts and parts[0] else ("semanticScore" if keyword_present else "updatedAt")
        direction = (parts[1] if len(parts) > 1 else "desc").lower()
        if direction not in ("asc", "desc"):
            direction = "desc"
        return field, direction

    def _resolve_chains(self, filters: SearchFilters, keyword_present: bool) -> List[int]:
        # If the caller supplied a chain filter, use it exactly (aside from de-duplication).
        if filters.chains == "all":
            return self._get_all_configured_chains()
        if isinstance(filters.chains, list) and len(filters.chains) > 0:
            out: List[int] = []
            for c in filters.chains:
                try:
                    cid = int(c)
                except Exception:
                    continue
                if cid not in out:
                    out.append(cid)
            return out

        # Default behavior (keyword or not): query chain 1 + the SDK-initialized chainId.
        # Avoid looking into chain 1 twice if SDK is initialized with chainId=1.
        default_chains = [1, int(self.web3_client.chain_id)]
        out: List[int] = []
        for cid in default_chains:
            if cid not in out:
                out.append(cid)
        return out

    # Pagination removed: cursor helpers deleted.

    def _to_unix_seconds(self, dt: Any) -> int:
        if isinstance(dt, int):
            return dt
        if isinstance(dt, datetime):
            return int(dt.timestamp())
        s = str(dt).strip()
        if not s:
            raise ValueError("Empty date")
        # If no timezone, treat as UTC by appending 'Z'
        if not ("Z" in s or "z" in s or "+" in s or "-" in s[-6:]):
            s = f"{s}Z"
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())

    def _normalize_agent_ids(self, filters: SearchFilters, chains: List[int]) -> Optional[Dict[int, List[str]]]:
        if not filters.agentIds:
            return None
        by_chain: Dict[int, List[str]] = {}
        for aid in filters.agentIds:
            s = str(aid)
            if ":" in s:
                chain_str = s.split(":", 1)[0]
                try:
                    chain_id = int(chain_str)
                except Exception:
                    continue
                by_chain.setdefault(chain_id, []).append(s)
            else:
                if len(chains) != 1:
                    raise ValueError("agentIds without chain prefix are only allowed when searching exactly one chain.")
                by_chain.setdefault(chains[0], []).append(f"{chains[0]}:{s}")
        return by_chain

    def _build_where_v2(self, filters: SearchFilters, ids_for_chain: Optional[List[str]] = None) -> Dict[str, Any]:
        base: Dict[str, Any] = {}
        and_conditions: List[Dict[str, Any]] = []

        # Default: only agents with registration files
        if filters.hasRegistrationFile is False:
            base["registrationFile"] = None
        else:
            base["registrationFile_not"] = None

        if ids_for_chain:
            base["id_in"] = ids_for_chain

        if filters.walletAddress:
            base["agentWallet"] = str(filters.walletAddress).lower()

        # Feedback existence filters can be pushed down via Agent.totalFeedback when they are the ONLY feedback constraint.
        fb = filters.feedback
        if fb and (getattr(fb, "hasFeedback", False) or getattr(fb, "hasNoFeedback", False)):
            has_threshold = any(
                x is not None
                for x in [
                    getattr(fb, "minCount", None),
                    getattr(fb, "maxCount", None),
                    getattr(fb, "minValue", None),
                    getattr(fb, "maxValue", None),
                ]
            )
            has_any_constraint = any(
                [
                    bool(getattr(fb, "hasResponse", False)),
                    bool(getattr(fb, "fromReviewers", None)),
                    bool(getattr(fb, "endpoint", None)),
                    bool(getattr(fb, "tag", None)),
                    bool(getattr(fb, "tag1", None)),
                    bool(getattr(fb, "tag2", None)),
                ]
            )
            if not has_threshold and not has_any_constraint:
                if getattr(fb, "hasFeedback", False):
                    base["totalFeedback_gt"] = "0"
                if getattr(fb, "hasNoFeedback", False):
                    base["totalFeedback"] = "0"

        if filters.owners:
            base["owner_in"] = [str(o).lower() for o in filters.owners]

        if filters.operators:
            ops = [str(o).lower() for o in filters.operators]
            and_conditions.append({"or": [{"operators_contains": [op]} for op in ops]})

        if filters.registeredAtFrom is not None:
            base["createdAt_gte"] = self._to_unix_seconds(filters.registeredAtFrom)
        if filters.registeredAtTo is not None:
            base["createdAt_lte"] = self._to_unix_seconds(filters.registeredAtTo)
        if filters.updatedAtFrom is not None:
            base["updatedAt_gte"] = self._to_unix_seconds(filters.updatedAtFrom)
        if filters.updatedAtTo is not None:
            base["updatedAt_lte"] = self._to_unix_seconds(filters.updatedAtTo)

        rf: Dict[str, Any] = {}
        if filters.name:
            rf["name_contains_nocase"] = filters.name
        if filters.description:
            rf["description_contains_nocase"] = filters.description
        if filters.ensContains:
            rf["ens_contains_nocase"] = filters.ensContains
        if filters.didContains:
            rf["did_contains_nocase"] = filters.didContains
        if filters.active is not None:
            rf["active"] = filters.active
        if filters.x402support is not None:
            rf["x402Support"] = filters.x402support

        if filters.hasMCP is not None:
            rf["mcpEndpoint_not" if filters.hasMCP else "mcpEndpoint"] = None
        if filters.hasA2A is not None:
            rf["a2aEndpoint_not" if filters.hasA2A else "a2aEndpoint"] = None
        if filters.hasWeb is not None:
            rf["webEndpoint_not" if filters.hasWeb else "webEndpoint"] = None
        if filters.hasOASF is not None:
            # Exact semantics: true iff (oasfSkills OR oasfDomains) is non-empty (via subgraph derived field).
            rf["hasOASF"] = bool(filters.hasOASF)

        if filters.mcpContains:
            rf["mcpEndpoint_contains_nocase"] = filters.mcpContains
        if filters.a2aContains:
            rf["a2aEndpoint_contains_nocase"] = filters.a2aContains
        if filters.webContains:
            rf["webEndpoint_contains_nocase"] = filters.webContains

        if rf:
            base["registrationFile_"] = rf

        def any_of_list(field: str, values: Optional[List[str]]):
            if not values:
                return
            and_conditions.append({"or": [{"registrationFile_": {f"{field}_contains": [v]}} for v in values]})

        any_of_list("supportedTrusts", filters.supportedTrust)
        any_of_list("a2aSkills", filters.a2aSkills)
        any_of_list("mcpTools", filters.mcpTools)
        any_of_list("mcpPrompts", filters.mcpPrompts)
        any_of_list("mcpResources", filters.mcpResources)
        any_of_list("oasfSkills", filters.oasfSkills)
        any_of_list("oasfDomains", filters.oasfDomains)

        if filters.hasEndpoints is not None:
            if filters.hasEndpoints:
                and_conditions.append(
                    {
                        "or": [
                            {"registrationFile_": {"webEndpoint_not": None}},
                            {"registrationFile_": {"mcpEndpoint_not": None}},
                            {"registrationFile_": {"a2aEndpoint_not": None}},
                        ]
                    }
                )
            else:
                and_conditions.append({"registrationFile_": {"webEndpoint": None, "mcpEndpoint": None, "a2aEndpoint": None}})

        if not and_conditions:
            return base
        return {"and": [base, *and_conditions]}

    def _intersect_ids(self, a: Optional[List[str]], b: Optional[List[str]]) -> Optional[List[str]]:
        if a is None and b is None:
            return None
        if a is None:
            return b or []
        if b is None:
            return a or []
        bset = set(b)
        return [x for x in a if x in bset]

    def _utf8_to_hex(self, s: str) -> str:
        return "0x" + s.encode("utf-8").hex()

    def _prefilter_by_metadata(self, filters: SearchFilters, chains: List[int]) -> Optional[Dict[int, List[str]]]:
        key = filters.hasMetadataKey or (filters.metadataValue.get("key") if isinstance(filters.metadataValue, dict) else None)
        if not key:
            return None
        value_str = None
        if isinstance(filters.metadataValue, dict):
            value_str = filters.metadataValue.get("value")
        value_hex = self._utf8_to_hex(str(value_str)) if value_str is not None else None

        first = 1000
        out: Dict[int, List[str]] = {}

        for chain_id in chains:
            sub = self._get_subgraph_client_for_chain(chain_id)
            if sub is None:
                out[chain_id] = []
                continue
            ids: List[str] = []
            skip = 0
            while True:
                where: Dict[str, Any] = {"key": key}
                if value_hex is not None:
                    where["value"] = value_hex
                rows = sub.query_agent_metadatas(where=where, first=first, skip=skip)
                for r in rows:
                    agent = r.get("agent") or {}
                    aid = agent.get("id")
                    if aid:
                        ids.append(str(aid))
                if len(rows) < first:
                    break
                skip += first
            out[chain_id] = sorted(list(set(ids)))
        return out

    def _prefilter_by_feedback(
        self,
        filters: SearchFilters,
        chains: List[int],
        candidate_ids_by_chain: Optional[Dict[int, List[str]]] = None,
    ) -> tuple[Optional[Dict[int, List[str]]], Dict[str, Dict[str, float]]]:
        fb = filters.feedback
        if fb is None:
            return None, {}

        include_revoked = bool(getattr(fb, "includeRevoked", False))
        has_threshold = any(
            x is not None
            for x in [
                getattr(fb, "minCount", None),
                getattr(fb, "maxCount", None),
                getattr(fb, "minValue", None),
                getattr(fb, "maxValue", None),
            ]
        )
        has_any_constraint = any(
            [
                bool(getattr(fb, "hasResponse", False)),
                bool(getattr(fb, "fromReviewers", None)),
                bool(getattr(fb, "endpoint", None)),
                bool(getattr(fb, "tag", None)),
                bool(getattr(fb, "tag1", None)),
                bool(getattr(fb, "tag2", None)),
            ]
        )

        # If hasNoFeedback/hasFeedback are the ONLY feedback constraint, we push them down via Agent.totalFeedback in _build_where_v2.
        if getattr(fb, "hasNoFeedback", False) and not has_threshold and not has_any_constraint:
            return None, {}
        if getattr(fb, "hasFeedback", False) and not has_threshold and not has_any_constraint:
            return None, {}

        # Otherwise, hasNoFeedback requires an explicit candidate set to subtract from.
        if getattr(fb, "hasNoFeedback", False):
            if not candidate_ids_by_chain or not any(candidate_ids_by_chain.get(c) for c in chains):
                raise ValueError("feedback.hasNoFeedback requires a pre-filtered candidate set (e.g. agentIds or keyword).")

        first = 1000

        sums: Dict[str, float] = {}
        counts: Dict[str, int] = {}
        matched_by_chain: Dict[int, set[str]] = {}

        for chain_id in chains:
            sub = self._get_subgraph_client_for_chain(chain_id)
            if sub is None:
                continue
            candidates = (candidate_ids_by_chain or {}).get(chain_id)

            base: Dict[str, Any] = {}
            and_conditions: List[Dict[str, Any]] = []

            if not include_revoked:
                base["isRevoked"] = False
            from_reviewers = getattr(fb, "fromReviewers", None)
            if from_reviewers:
                base["clientAddress_in"] = [str(a).lower() for a in from_reviewers]
            endpoint = getattr(fb, "endpoint", None)
            if endpoint:
                base["endpoint_contains_nocase"] = endpoint
            if candidates:
                base["agent_in"] = candidates

            tag1 = getattr(fb, "tag1", None)
            tag2 = getattr(fb, "tag2", None)
            tag = getattr(fb, "tag", None)
            if tag1:
                base["tag1"] = tag1
            if tag2:
                base["tag2"] = tag2
            if tag:
                and_conditions.append({"or": [{"tag1": tag}, {"tag2": tag}]})

            where: Dict[str, Any] = {"and": [base, *and_conditions]} if and_conditions else base

            skip = 0
            while True:
                rows = sub.query_feedbacks_minimal(where=where, first=first, skip=skip, order_by="createdAt", order_direction="desc")
                for r in rows:
                    agent = r.get("agent") or {}
                    aid = agent.get("id")
                    if not aid:
                        continue
                    if getattr(fb, "hasResponse", False):
                        responses = r.get("responses") or []
                        if not isinstance(responses, list) or len(responses) == 0:
                            continue
                    try:
                        v = float(r.get("value"))
                    except Exception:
                        continue
                    aid_s = str(aid)
                    sums[aid_s] = sums.get(aid_s, 0.0) + v
                    counts[aid_s] = counts.get(aid_s, 0) + 1
                    matched_by_chain.setdefault(chain_id, set()).add(aid_s)
                if len(rows) < first:
                    break
                skip += first

        stats: Dict[str, Dict[str, float]] = {}
        for aid, cnt in counts.items():
            avg = (sums.get(aid, 0.0) / cnt) if cnt > 0 else 0.0
            stats[aid] = {"count": float(cnt), "avg": float(avg)}

        def passes(aid: str) -> bool:
            st = stats.get(aid, {"count": 0.0, "avg": 0.0})
            cnt = st["count"]
            avg = st["avg"]
            min_count = getattr(fb, "minCount", None)
            max_count = getattr(fb, "maxCount", None)
            min_val = getattr(fb, "minValue", None)
            max_val = getattr(fb, "maxValue", None)
            if min_count is not None and cnt < float(min_count):
                return False
            if max_count is not None and cnt > float(max_count):
                return False
            if min_val is not None and avg < float(min_val):
                return False
            if max_val is not None and avg > float(max_val):
                return False
            return True

        allow: Dict[int, List[str]] = {}
        for chain_id in chains:
            matched = matched_by_chain.get(chain_id, set())
            candidates = (candidate_ids_by_chain or {}).get(chain_id)

            if getattr(fb, "hasNoFeedback", False):
                base_list = candidates or []
                allow[chain_id] = [x for x in base_list if x not in matched]
                continue

            ids = list(matched)
            if has_threshold:
                ids = [x for x in ids if passes(x)]
            elif has_any_constraint or getattr(fb, "hasFeedback", False):
                ids = [x for x in ids if counts.get(x, 0) > 0]

            if candidates:
                cset = set(candidates)
                ids = [x for x in ids if x in cset]

            allow[chain_id] = ids

        return allow, stats

    def _search_unified_no_keyword(self, filters: SearchFilters, options: SearchOptions) -> List[AgentSummary]:
        if not self.subgraph_client:
            raise ValueError("Subgraph client required for searchAgents")

        field, direction = self._parse_sort(options.sort, False)
        chains = self._resolve_chains(filters, False)
        ids_by_chain = self._normalize_agent_ids(filters, chains)
        metadata_ids_by_chain = self._prefilter_by_metadata(filters, chains)

        candidate_for_feedback: Dict[int, List[str]] = {}
        for c in chains:
            ids0 = self._intersect_ids((ids_by_chain or {}).get(c), (metadata_ids_by_chain or {}).get(c))
            if ids0:
                candidate_for_feedback[c] = ids0

        feedback_ids_by_chain, feedback_stats_by_id = self._prefilter_by_feedback(
            filters, chains, candidate_for_feedback if candidate_for_feedback else None
        )

        order_by = field if field in ("createdAt", "updatedAt", "name", "chainId", "lastActivity", "totalFeedback") else "updatedAt"
        if field == "feedbackCount":
            order_by = "totalFeedback"

        def to_summary(agent_data: Dict[str, Any]) -> AgentSummary:
            reg_file = agent_data.get("registrationFile") or {}
            if not isinstance(reg_file, dict):
                reg_file = {}
            aid = str(agent_data.get("id", ""))
            st = feedback_stats_by_id.get(aid) or {}
            return AgentSummary(
                chainId=int(agent_data.get("chainId", 0)),
                agentId=aid,
                name=reg_file.get("name") or aid,
                image=reg_file.get("image"),
                description=reg_file.get("description", "") or "",
                owners=[agent_data.get("owner", "")] if agent_data.get("owner") else [],
                operators=agent_data.get("operators", []) or [],
                mcp=reg_file.get("mcpEndpoint") or None,
                a2a=reg_file.get("a2aEndpoint") or None,
                web=reg_file.get("webEndpoint") or None,
                email=reg_file.get("emailEndpoint") or None,
                ens=reg_file.get("ens"),
                did=reg_file.get("did"),
                walletAddress=agent_data.get("agentWallet"),
                supportedTrusts=reg_file.get("supportedTrusts", []) or [],
                a2aSkills=reg_file.get("a2aSkills", []) or [],
                mcpTools=reg_file.get("mcpTools", []) or [],
                mcpPrompts=reg_file.get("mcpPrompts", []) or [],
                mcpResources=reg_file.get("mcpResources", []) or [],
                oasfSkills=reg_file.get("oasfSkills", []) or [],
                oasfDomains=reg_file.get("oasfDomains", []) or [],
                active=bool(reg_file.get("active", False)),
                x402support=bool(reg_file.get("x402Support", reg_file.get("x402support", False))),
                createdAt=agent_data.get("createdAt"),
                updatedAt=agent_data.get("updatedAt"),
                lastActivity=agent_data.get("lastActivity"),
                agentURI=agent_data.get("agentURI"),
                agentURIType=agent_data.get("agentURIType"),
                feedbackCount=agent_data.get("totalFeedback"),
                averageValue=float(st.get("avg")) if st.get("avg") is not None else None,
                extras={},
            )

        batch = 1000
        out: List[AgentSummary] = []
        for chain_id in chains:
            client = self._get_subgraph_client_for_chain(chain_id)
            if client is None:
                continue
            ids0 = self._intersect_ids((ids_by_chain or {}).get(chain_id), (metadata_ids_by_chain or {}).get(chain_id))
            ids = self._intersect_ids(ids0, (feedback_ids_by_chain or {}).get(chain_id))
            if ids is not None and len(ids) == 0:
                continue
            where = self._build_where_v2(filters, ids)

            skip = 0
            while True:
                agents = client.get_agents_v2(where=where, first=batch, skip=skip, order_by=order_by, order_direction=direction)
                for a in agents:
                    out.append(to_summary(a))
                if len(agents) < batch:
                    break
                skip += batch

        reverse = direction == "desc"

        def sort_key(a: AgentSummary):
            if field == "name":
                return (a.name or "").lower()
            v = getattr(a, field, None)
            if v is None and field == "totalFeedback":
                v = getattr(a, "feedbackCount", None)
            if v is None:
                return 0.0
            try:
                return float(v)
            except Exception:
                return 0.0

        return sorted(out, key=sort_key, reverse=reverse)

    def _search_unified_with_keyword(self, filters: SearchFilters, options: SearchOptions) -> List[AgentSummary]:
        field, direction = self._parse_sort(options.sort, True)
        chains = self._resolve_chains(filters, True)

        client = SemanticSearchClient()
        semantic_results = client.search(
            str(filters.keyword),
            min_score=options.semanticMinScore,
            top_k=options.semanticTopK,
        )

        allowed = set(chains)
        semantic_results = [r for r in semantic_results if r.chainId in allowed]
        ids_by_chain: Dict[int, List[str]] = {}
        score_by_id: Dict[str, float] = {}
        for r in semantic_results:
            ids_by_chain.setdefault(r.chainId, []).append(r.agentId)
            score_by_id[r.agentId] = r.score

        fetched: List[AgentSummary] = []

        metadata_ids_by_chain = self._prefilter_by_metadata(filters, chains)
        feedback_ids_by_chain, feedback_stats_by_id = self._prefilter_by_feedback(filters, chains, ids_by_chain)

        # Query agents by id_in chunks and apply remaining filters via where.
        chunk_size = 500
        for chain_id in chains:
            sub = self._get_subgraph_client_for_chain(chain_id)
            ids = ids_by_chain.get(chain_id, [])
            if sub is None:
                continue
            try:
                for i in range(0, len(ids), chunk_size):
                    chunk = ids[i : i + chunk_size]
                    ids2 = self._intersect_ids(chunk, (metadata_ids_by_chain or {}).get(chain_id))
                    ids3 = self._intersect_ids(ids2, (feedback_ids_by_chain or {}).get(chain_id))
                    if ids3 is not None and len(ids3) == 0:
                        continue
                    if ids3 is not None and len(ids3) == 0:
                        continue
                    where = self._build_where_v2(filters, ids3)
                    agents = sub.get_agents_v2(where=where, first=len(ids3 or []), skip=0, order_by="updatedAt", order_direction="desc")
                    for a in agents:
                        reg_file = a.get("registrationFile") or {}
                        if not isinstance(reg_file, dict):
                            reg_file = {}
                        aid = str(a.get("id", ""))
                        st = feedback_stats_by_id.get(aid) or {}
                        fetched.append(
                            AgentSummary(
                                chainId=int(a.get("chainId", 0)),
                                agentId=aid,
                                name=reg_file.get("name") or aid,
                                image=reg_file.get("image"),
                                description=reg_file.get("description", "") or "",
                                owners=[a.get("owner", "")] if a.get("owner") else [],
                                operators=a.get("operators", []) or [],
                                mcp=reg_file.get("mcpEndpoint") or None,
                                a2a=reg_file.get("a2aEndpoint") or None,
                                web=reg_file.get("webEndpoint") or None,
                                email=reg_file.get("emailEndpoint") or None,
                                ens=reg_file.get("ens"),
                                did=reg_file.get("did"),
                                walletAddress=a.get("agentWallet"),
                                supportedTrusts=reg_file.get("supportedTrusts", []) or [],
                                a2aSkills=reg_file.get("a2aSkills", []) or [],
                                mcpTools=reg_file.get("mcpTools", []) or [],
                                mcpPrompts=reg_file.get("mcpPrompts", []) or [],
                                mcpResources=reg_file.get("mcpResources", []) or [],
                                oasfSkills=reg_file.get("oasfSkills", []) or [],
                                oasfDomains=reg_file.get("oasfDomains", []) or [],
                                active=bool(reg_file.get("active", False)),
                                x402support=bool(reg_file.get("x402Support", reg_file.get("x402support", False))),
                                createdAt=a.get("createdAt"),
                                updatedAt=a.get("updatedAt"),
                                lastActivity=a.get("lastActivity"),
                                agentURI=a.get("agentURI"),
                                agentURIType=a.get("agentURIType"),
                                feedbackCount=a.get("totalFeedback"),
                                semanticScore=float(score_by_id.get(aid, 0.0)),
                                averageValue=float(st.get("avg")) if st.get("avg") is not None else None,
                                extras={},
                            )
                        )
            except Exception:
                continue

        # Default keyword sorting: semanticScore desc, unless overridden.
        sort_field = field if options.sort and len(options.sort) > 0 else "semanticScore"
        sort_dir = direction if options.sort and len(options.sort) > 0 else "desc"

        def sort_key(agent: AgentSummary):
            v = getattr(agent, sort_field, None)
            if v is None:
                return 0
            if sort_field == "name":
                return (agent.name or "").lower()
            try:
                return float(v)
            except Exception:
                return 0

        fetched.sort(key=sort_key, reverse=(sort_dir == "desc"))
        return fetched

    # Pagination removed: legacy cursor-based multi-chain agent search deleted.

    # Pagination removed: legacy cursor-based agent search helpers deleted.

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
            value=float(feedback_data.get("value")) if feedback_data.get("value") is not None else None,
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
            # Prefer on-chain endpoint; fall back to off-chain file endpoint if missing
            endpoint=feedback_data.get('endpoint') or feedback_file.get('endpoint'),
            createdAt=feedback_data.get('createdAt', int(time.time())),
            answers=answers,
            isRevoked=feedback_data.get('isRevoked', False),
            name=feedback_file.get('name'),
            skill=feedback_file.get('skill'),
            task=feedback_file.get('task'),
        )
    
    def search_feedback(
        self,
        agentId: Optional[AgentId] = None,
        clientAddresses: Optional[List[Address]] = None,
        tags: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        tasks: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        minValue: Optional[float] = None,
        maxValue: Optional[float] = None,
        include_revoked: bool = False,
        agents: Optional[List[AgentId]] = None,
    ) -> List[Feedback]:
        """Search feedback via subgraph.
        
        Backwards compatible:
        - Previously required `agentId`; it is now optional.
        
        New:
        - `agents` supports searching across multiple agents.
        - If neither `agentId` nor `agents` is provided, subgraph search can still run using
          other filters (e.g., reviewers / tags).
        """

        merged_agents: Optional[List[AgentId]] = None
        if agents:
            merged_agents = list(agents)
        if agentId:
            merged_agents = (merged_agents or []) + [agentId]

        # Determine chain/subgraph client based on first specified agent (if any)
        chain_id = None
        if merged_agents and len(merged_agents) > 0:
            first_agent = merged_agents[0]
            chain_id, token_id = self._parse_agent_id(first_agent)
        
        # Get subgraph client for the chain
        subgraph_client = None

        if chain_id is not None:
            subgraph_client = self._get_subgraph_client_for_chain(chain_id)
        else:
            # If no explicit chainId, use SDK's default subgraph client (if configured).
            subgraph_client = self.subgraph_client

        # If we have agent ids but they weren't chain-prefixed, prefix them with default chain id for the subgraph.
        if merged_agents and chain_id is None:
            default_chain_id = self.web3_client.chain_id
            normalized: List[AgentId] = []
            for aid in merged_agents:
                if isinstance(aid, str) and ":" in aid:
                    normalized.append(aid)
                else:
                    normalized.append(f"{default_chain_id}:{int(aid)}")
            merged_agents = normalized
        elif merged_agents and chain_id is not None:
            # Ensure all agent ids are chain-prefixed for the chosen chain
            normalized = []
            for aid in merged_agents:
                if isinstance(aid, str) and ":" in aid:
                    normalized.append(aid)
                else:
                    normalized.append(f"{chain_id}:{int(aid)}")
            merged_agents = normalized
        
        # Use subgraph if available (preferred)
        if subgraph_client:
            return self._search_feedback_subgraph(
                agentId=None,
                agents=merged_agents,
                clientAddresses=clientAddresses,
                tags=tags,
                capabilities=capabilities,
                skills=skills,
                tasks=tasks,
                names=names,
                minValue=minValue,
                maxValue=maxValue,
                include_revoked=include_revoked,
                subgraph_client=subgraph_client,
            )
        
        # Fallback not implemented (would require blockchain queries)
        # For now, return empty if subgraph unavailable
        return []
    
    def _search_feedback_subgraph(
        self,
        agentId: Optional[AgentId],
        agents: Optional[List[AgentId]],
        clientAddresses: Optional[List[Address]],
        tags: Optional[List[str]],
        capabilities: Optional[List[str]],
        skills: Optional[List[str]],
        tasks: Optional[List[str]],
        names: Optional[List[str]],
        minValue: Optional[float],
        maxValue: Optional[float],
        include_revoked: bool,
        subgraph_client: Optional[Any] = None,
    ) -> List[Feedback]:
        """Search feedback using subgraph."""
        client = subgraph_client or self.subgraph_client
        if not client:
            return []

        merged_agents: Optional[List[AgentId]] = None
        if agents:
            merged_agents = list(agents)
        if agentId:
            merged_agents = (merged_agents or []) + [agentId]

        params = SearchFeedbackParams(
            agents=merged_agents,
            reviewers=clientAddresses,
            tags=tags,
            capabilities=capabilities,
            skills=skills,
            tasks=tasks,
            names=names,
            minValue=minValue,
            maxValue=maxValue,
            includeRevoked=include_revoked,
        )

        feedbacks: List[Feedback] = []
        batch = 1000
        skip = 0
        while True:
            feedbacks_data = client.search_feedback(
                params=params,
                first=batch,
                skip=skip,
                order_by="createdAt",
                order_direction="desc",
            )

            for fb_data in feedbacks_data:
                feedback_id = fb_data["id"]
                parts = feedback_id.split(":")
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

            if len(feedbacks_data) < batch:
                break
            skip += batch

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
    ) -> Dict[str, Any]:
        """Get reputation summary for an agent."""
        # This would aggregate feedback data
        # For now, return empty result
        return {
            "groups": [],
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
            
            # Get on-chain verified wallet (IdentityRegistry.getAgentWallet)
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
        params: SearchFilters
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
        params: SearchFilters
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
        # Deduplication across chains was part of an older API surface; the unified search does not deduplicate.
        return agents

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
        - averageValue (reputation, if available)
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

            elif field == 'averageValue':
                # If reputation search was done, averageValue may be available
                return agent.get('averageValue', 0)

            else:
                logger.warning(f"Unknown sort field: {field}, defaulting to createdAt")
                return agent.get('createdAt', 0)

        return sorted(agents, key=get_sort_key, reverse=reverse)

    # Pagination removed: multi-chain cursor helpers deleted.

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
