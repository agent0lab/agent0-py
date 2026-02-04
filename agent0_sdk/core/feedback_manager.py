"""
Feedback management system for Agent0 SDK.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timezone

from .models import (
    AgentId, Address, URI, Timestamp, IdemKey,
    Feedback, TrustModel, SearchFeedbackParams
)
from .web3_client import Web3Client
from .ipfs_client import IPFSClient
from .value_encoding import encode_feedback_value, decode_feedback_value
from .transaction_handle import TransactionHandle

logger = logging.getLogger(__name__)


class FeedbackManager:
    """Manages feedback operations for the Agent0 SDK."""

    def __init__(
        self,
        web3_client: Web3Client,
        ipfs_client: Optional[IPFSClient] = None,
        reputation_registry: Any = None,
        identity_registry: Any = None,
        subgraph_client: Optional[Any] = None,
        indexer: Optional[Any] = None,
    ):
        """Initialize feedback manager."""
        self.web3_client = web3_client
        self.ipfs_client = ipfs_client
        self.reputation_registry = reputation_registry
        self.identity_registry = identity_registry
        self.subgraph_client = subgraph_client
        self.indexer = indexer

    def prepareFeedbackFile(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare an off-chain feedback file payload (no on-chain fields).
        
        This intentionally does NOT attempt to represent on-chain fields like:
        value/tag1/tag2/endpoint (on-chain value), or registry-derived fields.
        
        It may validate/normalize and remove None values.
        """
        if input is None:
            raise ValueError("prepareFeedbackFile input cannot be None")
        if not isinstance(input, dict):
            raise TypeError(f"prepareFeedbackFile input must be a dict, got {type(input)}")

        # Shallow copy and strip None values
        out: Dict[str, Any] = {k: v for k, v in dict(input).items() if v is not None}

        # Minimal normalization for known optional fields
        if "endpoint" in out and out["endpoint"] is not None and not isinstance(out["endpoint"], str):
            out["endpoint"] = str(out["endpoint"])
        if "domain" in out and out["domain"] is not None and not isinstance(out["domain"], str):
            out["domain"] = str(out["domain"])

        return out

    def giveFeedback(
        self,
        agentId: AgentId,
        value: Union[int, float, str],
        tag1: Optional[str] = None,
        tag2: Optional[str] = None,
        endpoint: Optional[str] = None,
        feedbackFile: Optional[Dict[str, Any]] = None,
    ) -> TransactionHandle[Feedback]:
        """Give feedback (maps 8004 endpoint)."""
        # Parse agentId into (chainId, tokenId)
        agent_chain_id: Optional[int] = None
        tokenId: int
        if isinstance(agentId, str) and agentId.startswith("eip155:"):
            parts = agentId.split(":")
            if len(parts) != 3:
                raise ValueError(f"Invalid AgentId (expected eip155:chainId:tokenId): {agentId}")
            agent_chain_id = int(parts[1])
            tokenId = int(parts[2])
        elif isinstance(agentId, str) and ":" in agentId:
            parts = agentId.split(":")
            if len(parts) != 2:
                raise ValueError(f"Invalid AgentId (expected chainId:tokenId): {agentId}")
            agent_chain_id = int(parts[0])
            tokenId = int(parts[1])
        else:
            tokenId = int(agentId)
            agent_chain_id = int(self.web3_client.chain_id)

        # Ensure we are submitting the tx on the agent's chain
        if int(self.web3_client.chain_id) != int(agent_chain_id):
            raise ValueError(
                f"Chain mismatch for giveFeedback: agentId={agentId} targets chainId={agent_chain_id}, "
                f"but web3 client is connected to chainId={self.web3_client.chain_id}. "
                f"Initialize the SDK/Web3Client for chainId={agent_chain_id}."
            )
        
        # Get client address (the one giving feedback)
        # Keep in checksum format for blockchain calls (web3.py requirement)
        clientAddress = self.web3_client.account.address
        
        # Get current feedback index for this client-agent pair
        try:
            lastIndex = self.web3_client.call_contract(
                self.reputation_registry,
                "getLastIndex",
                tokenId,
                clientAddress
            )
            feedbackIndex = lastIndex + 1
        except Exception as e:
            raise ValueError(f"Failed to get feedback index: {e}")
        
        value_raw, value_decimals, _normalized = encode_feedback_value(value)

        tag1 = tag1 or ""
        tag2 = tag2 or ""

        feedback_file: Optional[Dict[str, Any]] = feedbackFile
        if feedback_file is not None and not isinstance(feedback_file, dict):
            raise TypeError(f"feedbackFile must be a dict when provided, got {type(feedback_file)}")

        # Endpoint precedence: explicit arg > file endpoint > empty string
        if endpoint:
            endpoint_onchain = endpoint
        elif feedback_file and isinstance(feedback_file.get("endpoint"), str) and feedback_file.get("endpoint"):
            endpoint_onchain = feedback_file.get("endpoint")
        else:
            endpoint_onchain = ""

        # If uploading a file and we have an explicit endpoint, inject it for consistency
        if feedback_file is not None and endpoint and isinstance(endpoint, str):
            feedback_file = dict(feedback_file)
            feedback_file["endpoint"] = endpoint
        
        # Handle off-chain file storage
        feedbackUri = ""
        feedbackHash = b"\x00" * 32  # Default empty hash
        
        if feedback_file is not None:
            if not self.ipfs_client:
                raise ValueError("feedbackFile was provided, but no IPFS client is configured")

            # Store an ERC-8004 compliant feedback file on IPFS (explicit opt-in)
            try:
                logger.debug("Storing feedback file on IPFS")
                # createdAt MUST be present in the off-chain file; use provided value if valid, else now (UTC).
                created_at = feedback_file.get("createdAt")
                if not isinstance(created_at, str) or not created_at:
                    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                identity_registry_address = "0x0"
                try:
                    if self.identity_registry is not None:
                        identity_registry_address = str(getattr(self.identity_registry, "address", "0x0"))
                except Exception:
                    identity_registry_address = "0x0"

                # Remove any user-provided copies of the envelope keys; SDK-owned values must win
                rich = dict(feedback_file)
                for k in [
                    "agentRegistry",
                    "agentId",
                    "clientAddress",
                    "createdAt",
                    "value",
                    "valueDecimals",
                    "tag1",
                    "tag2",
                    "endpoint",
                ]:
                    rich.pop(k, None)

                file_for_storage: Dict[str, Any] = {
                    # MUST fields (spec)
                    "agentRegistry": f"eip155:{agent_chain_id}:{identity_registry_address}",
                    "agentId": tokenId,
                    "clientAddress": f"eip155:{agent_chain_id}:{clientAddress}",
                    "createdAt": created_at,
                    # On-chain fields (store raw+decimals for precision)
                    "value": int(value_raw),
                    "valueDecimals": int(value_decimals),

                    # OPTIONAL fields that mirror on-chain
                    **({"tag1": tag1} if tag1 else {}),
                    **({"tag2": tag2} if tag2 else {}),
                    **({"endpoint": endpoint_onchain} if endpoint_onchain else {}),

                    # Rich/off-chain fields
                    **rich,
                }

                cid = self.ipfs_client.addFeedbackFile(file_for_storage)
                feedbackUri = f"ipfs://{cid}"
                feedbackHash = self.web3_client.keccak256(
                    json.dumps(file_for_storage, sort_keys=True).encode()
                )
                logger.debug(f"Feedback file stored on IPFS: {cid}")
            except Exception as e:
                raise ValueError(f"Failed to store feedback on IPFS: {e}")
        
        # Submit to blockchain with new signature: giveFeedback(agentId, value, valueDecimals, tag1, tag2, endpoint, feedbackURI, feedbackHash)
        try:
            txHash = self.web3_client.transact_contract(
                self.reputation_registry,
                "giveFeedback",
                tokenId,
                value_raw,
                value_decimals,
                tag1,
                tag2,
                endpoint_onchain,
                feedbackUri,
                feedbackHash
            )
        except Exception as e:
            raise ValueError(f"Failed to submit feedback to blockchain: {e}")

        # Create a tx handle; build the Feedback object on confirmation.
        feedbackId = Feedback.create_id(agentId, clientAddress, feedbackIndex)
        ff: Dict[str, Any] = feedback_file or {}

        return TransactionHandle(
            web3_client=self.web3_client,
            tx_hash=txHash,
            compute_result=lambda _receipt: Feedback(
                id=feedbackId,
                agentId=agentId,
                reviewer=clientAddress,
                value=decode_feedback_value(value_raw, value_decimals),
                tags=[tag1, tag2] if tag1 or tag2 else [],
                text=ff.get("text"),
                context=ff.get("context"),
                proofOfPayment=ff.get("proofOfPayment"),
                fileURI=feedbackUri if feedbackUri else None,
                endpoint=endpoint_onchain if endpoint_onchain else None,
                createdAt=int(time.time()),
                isRevoked=False,
                capability=ff.get("capability"),
                name=ff.get("name"),
                skill=ff.get("skill"),
                task=ff.get("task"),
            ),
        )

    def getFeedback(
        self,
        agentId: AgentId,
        clientAddress: Address,
        feedbackIndex: int,
    ) -> Feedback:
        """Get single feedback with responses from subgraph or blockchain."""
        # Prefer subgraph/indexer for richer data, but fall back to chain when subgraph is behind
        if self.indexer and self.subgraph_client:
            try:
                return self.indexer.get_feedback(agentId, clientAddress, feedbackIndex)
            except Exception as e:
                logger.debug(f"Indexer/subgraph get_feedback failed, falling back to blockchain: {e}")
                return self._get_feedback_from_blockchain(agentId, clientAddress, feedbackIndex)
        
        if self.subgraph_client:
            try:
                return self._get_feedback_from_subgraph(agentId, clientAddress, feedbackIndex)
            except Exception as e:
                logger.debug(f"Subgraph get feedback failed, falling back to blockchain: {e}")
                return self._get_feedback_from_blockchain(agentId, clientAddress, feedbackIndex)
        
        return self._get_feedback_from_blockchain(agentId, clientAddress, feedbackIndex)
    
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
        # If agentId already contains chainId (format: chainId:tokenId), use it as is
        # Otherwise, prepend chainId from web3_client
        if ":" in agentId:
            # agentId already has chainId, so use it directly
            feedback_id = f"{agentId}:{normalized_client_address}:{feedbackIndex}"
        else:
            # No chainId in agentId, prepend it
            chain_id = str(self.web3_client.chain_id)
            feedback_id = f"{chain_id}:{agentId}:{normalized_client_address}:{feedbackIndex}"
        
        try:
            feedback_data = self.subgraph_client.get_feedback_by_id(feedback_id)
            
            if feedback_data is None:
                raise ValueError(f"Feedback {feedback_id} not found in subgraph")
            
            feedback_file = feedback_data.get('feedbackFile') or {}
            if not isinstance(feedback_file, dict):
                feedback_file = {}
            
            # Map responses
            responses_data = feedback_data.get('responses', [])
            answers = []
            for resp in responses_data:
                answers.append({
                    'responder': resp.get('responder'),
                    'responseUri': resp.get('responseUri'),
                    'responseHash': resp.get('responseHash'),
                    'createdAt': resp.get('createdAt')
                })
            
            # Map tags: rely on whatever the subgraph returns (may be legacy bytes/hash-like values)
            tags: List[str] = []
            tag1 = feedback_data.get('tag1') or feedback_file.get('tag1')
            tag2 = feedback_data.get('tag2') or feedback_file.get('tag2')
            if isinstance(tag1, str) and tag1:
                    tags.append(tag1)
            if isinstance(tag2, str) and tag2:
                    tags.append(tag2)
            
            return Feedback(
                id=Feedback.create_id(agentId, clientAddress, feedbackIndex),  # create_id now normalizes
                agentId=agentId,
                reviewer=self.web3_client.normalize_address(clientAddress),  # Also normalize reviewer field
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
            
        except Exception as e:
            raise ValueError(f"Failed to get feedback from subgraph: {e}")
    
    def _get_feedback_from_blockchain(
        self,
        agentId: AgentId,
        clientAddress: Address,
        feedbackIndex: int,
    ) -> Feedback:
        """Get feedback from blockchain (fallback)."""
        # Parse agent ID
        if ":" in agentId:
            tokenId = int(agentId.split(":")[-1])
        else:
            tokenId = int(agentId)
        
        try:
            # Read from blockchain - new signature: readFeedback(agentId, clientAddress, feedbackIndex)
            result = self.web3_client.call_contract(
                self.reputation_registry,
                "readFeedback",
                tokenId,
                clientAddress,
                feedbackIndex
            )
            
            value_raw, value_decimals, tag1, tag2, is_revoked = result
            
            # Create feedback object (normalize address for consistency)
            normalized_address = self.web3_client.normalize_address(clientAddress)
            feedbackId = Feedback.create_id(agentId, normalized_address, feedbackIndex)
            
            # Tags are now strings, not bytes32
            tags = []
            if tag1:
                tags.append(tag1)
            if tag2:
                tags.append(tag2)
            
            return Feedback(
                id=feedbackId,
                agentId=agentId,
                reviewer=normalized_address,
                value=decode_feedback_value(int(value_raw), int(value_decimals)),
                tags=tags,
                text=None,  # Not stored on-chain
                capability=None,  # Not stored on-chain
                context=None,  # Not stored on-chain
                proofOfPayment=None,  # Not stored on-chain
                fileURI=None,  # Would need to be retrieved separately
                endpoint=None,  # Not stored on-chain in readFeedback
                createdAt=int(time.time()),  # Not stored on-chain
                isRevoked=is_revoked
            )
            
        except Exception as e:
            raise ValueError(f"Failed to get feedback: {e}")

    def searchFeedback(
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
        """Search feedback.
        
        Backwards compatible:
        - `agentId` was previously required; it is now optional.
        
        New:
        - `agents` supports searching across multiple agents.
        - If neither `agentId` nor `agents` are provided, the query can still run via subgraph
          using other filters like `clientAddresses` (reviewers), tags, etc.
        """
        # Use indexer for subgraph queries (unified search interface)
        if self.indexer and self.subgraph_client:
            # Indexer handles subgraph queries for unified search architecture
            # This enables future semantic search capabilities
            return self.indexer.search_feedback(
                agentId,
                clientAddresses,
                tags,
                capabilities,
                skills,
                tasks,
                names,
                minValue,
                maxValue,
                include_revoked,
                agents=agents,
            )
        
        # Fallback: direct subgraph access (if indexer not available)
        if self.subgraph_client:
            return self._search_feedback_subgraph(
                agentId,
                clientAddresses,
                tags,
                capabilities,
                skills,
                tasks,
                names,
                minValue,
                maxValue,
                include_revoked,
                agents=agents,
            )
        
        # Fallback to blockchain (requires a specific agent)
        if not agentId and not agents:
            raise ValueError(
                "searchFeedback requires a subgraph when searching without agentId/agents."
            )
        if not agentId and agents and len(agents) == 1:
            agentId = agents[0]
        if not agentId:
            raise ValueError(
                "Blockchain fallback only supports searching a single agent; provide agentId or a single-item agents=[...]."
            )

        # Parse agent ID
        if ":" in agentId:
            tokenId = int(agentId.split(":")[-1])
        else:
            tokenId = int(agentId)
        
        try:
            # Prepare filter parameters - tags are now strings
            client_list = clientAddresses if clientAddresses else []
            tag1_filter = tags[0] if tags else ""
            tag2_filter = tags[1] if tags and len(tags) > 1 else ""
            
            # Read from blockchain - signature returns: (clients, feedbackIndexes, values, valueDecimals, tag1s, tag2s, revokedStatuses)
            result = self.web3_client.call_contract(
                self.reputation_registry,
                "readAllFeedback",
                tokenId,
                client_list,
                tag1_filter,
                tag2_filter,
                include_revoked
            )
            
            clients, feedback_indexes, values, value_decimals, tag1s, tag2s, revoked_statuses = result
            
            # Convert to Feedback objects
            feedbacks = []
            for i in range(len(clients)):
                feedback_index = int(feedback_indexes[i]) if i < len(feedback_indexes) else (i + 1)
                feedbackId = Feedback.create_id(agentId, clients[i], feedback_index)
                
                # Tags are now strings
                tags_list = []
                if i < len(tag1s) and tag1s[i]:
                    tags_list.append(tag1s[i])
                if i < len(tag2s) and tag2s[i]:
                    tags_list.append(tag2s[i])
                
                feedback = Feedback(
                    id=feedbackId,
                    agentId=agentId,
                    reviewer=clients[i],
                    value=decode_feedback_value(int(values[i]), int(value_decimals[i])),
                    tags=tags_list,
                    text=None,
                    capability=None,
                    endpoint=None,
                    context=None,
                    proofOfPayment=None,
                    fileURI=None,
                    createdAt=int(time.time()),
                    isRevoked=revoked_statuses[i] if i < len(revoked_statuses) else False
                )
                feedbacks.append(feedback)
            
            return feedbacks
            
        except Exception as e:
            raise ValueError(f"Failed to search feedback: {e}")
    
    def _search_feedback_subgraph(
        self,
        agentId: Optional[AgentId],
        clientAddresses: Optional[List[Address]],
        tags: Optional[List[str]],
        capabilities: Optional[List[str]],
        skills: Optional[List[str]],
        tasks: Optional[List[str]],
        names: Optional[List[str]],
        minValue: Optional[float],
        maxValue: Optional[float],
        include_revoked: bool,
        agents: Optional[List[AgentId]] = None,
    ) -> List[Feedback]:
        """Search feedback using subgraph."""
        merged_agents: Optional[List[AgentId]] = None
        if agents:
            merged_agents = list(agents)
        if agentId:
            merged_agents = (merged_agents or []) + [agentId]

        # Create SearchFeedbackParams
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
            includeRevoked=include_revoked
        )
        
        feedbacks = []
        batch = 1000
        skip = 0
        while True:
            feedbacks_data = self.subgraph_client.search_feedback(
                params=params,
                first=batch,
                skip=skip,
                order_by="createdAt",
                order_direction="desc",
            )

            for fb_data in feedbacks_data:
                feedback_file = fb_data.get('feedbackFile') or {}
                if not isinstance(feedback_file, dict):
                    feedback_file = {}

                # Map responses
                responses_data = fb_data.get('responses', [])
                answers = []
                for resp in responses_data:
                    answers.append({
                        'responder': resp.get('responder'),
                        'responseUri': resp.get('responseUri'),
                        'responseHash': resp.get('responseHash'),
                        'createdAt': resp.get('createdAt')
                    })

                # Map tags: rely on whatever the subgraph returns (may be legacy bytes/hash-like values)
                tags_list: List[str] = []
                tag1 = fb_data.get('tag1') or feedback_file.get('tag1')
                tag2 = fb_data.get('tag2') or feedback_file.get('tag2')
                if isinstance(tag1, str) and tag1:
                    tags_list.append(tag1)
                if isinstance(tag2, str) and tag2:
                    tags_list.append(tag2)

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

                feedback = Feedback(
                    id=Feedback.create_id(agent_id_str, client_addr, feedback_idx),
                    agentId=agent_id_str,
                    reviewer=client_addr,
                    value=float(fb_data.get("value")) if fb_data.get("value") is not None else None,
                    tags=tags_list,
                    text=feedback_file.get('text'),
                    capability=feedback_file.get('capability'),
                    context=feedback_file.get('context'),
                    proofOfPayment={
                        'fromAddress': feedback_file.get('proofOfPaymentFromAddress'),
                        'toAddress': feedback_file.get('proofOfPaymentToAddress'),
                        'chainId': feedback_file.get('proofOfPaymentChainId'),
                        'txHash': feedback_file.get('proofOfPaymentTxHash'),
                    } if feedback_file.get('proofOfPaymentFromAddress') else None,
                    fileURI=fb_data.get('feedbackURI') or fb_data.get('feedbackUri'),  # Handle both old and new field names
                    endpoint=fb_data.get('endpoint'),
                    createdAt=fb_data.get('createdAt', int(time.time())),
                    answers=answers,
                    isRevoked=fb_data.get('isRevoked', False),
                    name=feedback_file.get('name'),
                    skill=feedback_file.get('skill'),
                    task=feedback_file.get('task'),
                )
                feedbacks.append(feedback)

            if len(feedbacks_data) < batch:
                break
            skip += batch
        
        return feedbacks

    def revokeFeedback(
        self,
        agentId: AgentId,
        feedbackIndex: int,
    ) -> TransactionHandle[Feedback]:
        """Revoke feedback."""
        # Parse agent ID
        if ":" in agentId:
            tokenId = int(agentId.split(":")[-1])
        else:
            tokenId = int(agentId)
        
        clientAddress = self.web3_client.account.address
        
        try:
            txHash = self.web3_client.transact_contract(
                self.reputation_registry,
                "revokeFeedback",
                tokenId,
                feedbackIndex
            )
            return TransactionHandle(
                web3_client=self.web3_client,
                tx_hash=txHash,
                compute_result=lambda _receipt: self.getFeedback(agentId, clientAddress, feedbackIndex),
            )
        except Exception as e:
            raise ValueError(f"Failed to revoke feedback: {e}")

    def appendResponse(
        self,
        agentId: AgentId,
        clientAddress: Address,
        feedbackIndex: int,
        response: Dict[str, Any],
    ) -> TransactionHandle[Feedback]:
        """Append a response/follow-up to existing feedback."""
        # Parse agent ID
        if ":" in agentId:
            tokenId = int(agentId.split(":")[-1])
        else:
            tokenId = int(agentId)
        
        # Prepare response data
        responseText = response.get("text", "")
        responseUri = ""
        responseHash = b"\x00" * 32
        
        if self.ipfs_client and (response.get("text") or response.get("attachments")):
            try:
                cid = self.ipfs_client.add_json(response)
                responseUri = f"ipfs://{cid}"
                responseHash = self.web3_client.keccak256(json.dumps(response, sort_keys=True).encode())
            except Exception as e:
                logger.warning(f"Failed to store response on IPFS: {e}")
        
        try:
            txHash = self.web3_client.transact_contract(
                self.reputation_registry,
                "appendResponse",
                tokenId,
                clientAddress,
                feedbackIndex,
                responseUri,  # Note: contract uses responseURI but variable name kept for compatibility
                responseHash
            )
            return TransactionHandle(
                web3_client=self.web3_client,
                tx_hash=txHash,
                compute_result=lambda _receipt: self.getFeedback(agentId, clientAddress, feedbackIndex),
            )
        except Exception as e:
            raise ValueError(f"Failed to append response: {e}")

    def getReputationSummary(
        self,
        agentId: AgentId,
        clientAddresses: Optional[List[Address]] = None,
        tag1: Optional[str] = None,
        tag2: Optional[str] = None,
        groupBy: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get reputation summary for an agent with optional grouping."""
        # Parse chainId from agentId
        chain_id = None
        if ":" in agentId:
            try:
                chain_id = int(agentId.split(":", 1)[0])
            except ValueError:
                chain_id = None
        
        # Try subgraph first (if available and indexer supports it)
        if self.indexer and self.subgraph_client:
            # Get correct subgraph client for the chain
            subgraph_client = None
            full_agent_id = agentId
            
            if chain_id is not None:
                subgraph_client = self.indexer._get_subgraph_client_for_chain(chain_id)
            else:
                # No chainId in agentId, use SDK's default
                # Construct full agentId format for subgraph query
                default_chain_id = self.web3_client.chain_id
                token_id = agentId.split(":")[-1] if ":" in agentId else agentId
                full_agent_id = f"{default_chain_id}:{token_id}"
                subgraph_client = self.subgraph_client
            
            if subgraph_client:
                # Use subgraph to calculate reputation
                return self._get_reputation_summary_from_subgraph(
                    full_agent_id, clientAddresses, tag1, tag2, groupBy
                )
        
        # Fallback to blockchain (requires chain-specific web3 client)
        # For now, only works if chain matches SDK's default
        if chain_id is not None and chain_id != self.web3_client.chain_id:
            raise ValueError(
                f"Blockchain reputation summary not supported for chain {chain_id}. "
                f"SDK is configured for chain {self.web3_client.chain_id}. "
                f"Use subgraph-based summary instead."
            )
        
        # Parse agent ID for blockchain call
        if ":" in agentId:
            tokenId = int(agentId.split(":")[-1])
        else:
            tokenId = int(agentId)
        
        try:
            client_list = clientAddresses if clientAddresses else []
            tag1_str = tag1 if tag1 else ""
            tag2_str = tag2 if tag2 else ""
            
            result = self.web3_client.call_contract(
                self.reputation_registry,
                "getSummary",
                tokenId,
                client_list,
                tag1_str,
                tag2_str
            )
            
            count, summary_value, summary_value_decimals = result
            average_value = decode_feedback_value(int(summary_value), int(summary_value_decimals))
            
            # If no grouping requested, return simple summary
            if not groupBy:
                return {
                    "agentId": agentId,
                    "count": count,
                    "averageValue": average_value,
                    "filters": {
                        "clientAddresses": clientAddresses,
                        "tag1": tag1,
                        "tag2": tag2
                    }
                }
            
            # Get detailed feedback data for grouping
            all_feedback = self.read_all_feedback(
                agentId=agentId,
                clientAddresses=clientAddresses,
                tags=[tag1, tag2] if tag1 or tag2 else None,
                include_revoked=False
            )
            
            # Group feedback by requested dimensions
            grouped_data = self._groupFeedback(all_feedback, groupBy)
            
            return {
                "agentId": agentId,
                "totalCount": count,
                "totalAverageValue": average_value,
                "groupedData": grouped_data,
                "filters": {
                    "clientAddresses": clientAddresses,
                    "tag1": tag1,
                    "tag2": tag2
                },
                "groupBy": groupBy
            }
            
        except Exception as e:
            raise ValueError(f"Failed to get reputation summary: {e}")
    
    def _get_reputation_summary_from_subgraph(
        self,
        agentId: AgentId,
        clientAddresses: Optional[List[Address]] = None,
        tag1: Optional[str] = None,
        tag2: Optional[str] = None,
        groupBy: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get reputation summary from subgraph."""
        # Build tags list
        tags = []
        if tag1:
            tags.append(tag1)
        if tag2:
            tags.append(tag2)
        
        # Get all feedback for the agent using indexer (which handles multi-chain)
        # Use searchFeedback with a large limit to get all feedback
        all_feedback = self.searchFeedback(
            agentId=agentId,
            clientAddresses=clientAddresses,
            tags=tags if tags else None,
            include_revoked=False,
            first=1000,  # Large limit to get all feedback
            skip=0
        )
        
        # Calculate summary statistics
        count = len(all_feedback)
        values = [fb.value for fb in all_feedback if fb.value is not None]
        average_value = sum(values) / len(values) if values else 0.0
        
        # If no grouping requested, return simple summary
        if not groupBy:
            return {
                "agentId": agentId,
                "count": count,
                "averageValue": average_value,
                "filters": {
                    "clientAddresses": clientAddresses,
                    "tag1": tag1,
                    "tag2": tag2
                }
            }
        
        # Group feedback by requested dimensions
        grouped_data = self._groupFeedback(all_feedback, groupBy)
        
        return {
            "agentId": agentId,
            "totalCount": count,
            "totalAverageValue": average_value,
            "groupedData": grouped_data,
            "filters": {
                "clientAddresses": clientAddresses,
                "tag1": tag1,
                "tag2": tag2
            },
            "groupBy": groupBy
        }
    
    def _groupFeedback(self, feedbackList: List[Feedback], groupBy: List[str]) -> Dict[str, Any]:
        """Group feedback by specified dimensions."""
        grouped = {}
        
        for feedback in feedbackList:
            # Create group key based on requested dimensions
            group_key = self._createGroupKey(feedback, groupBy)
            
            if group_key not in grouped:
                grouped[group_key] = {
                    "count": 0,
                    "totalValue": 0.0,
                    "averageValue": 0.0,
                    "values": [],
                    "feedback": []
                }
            
            # Add feedback to group
            grouped[group_key]["count"] += 1
            if feedback.value is not None:
                grouped[group_key]["totalValue"] += float(feedback.value)
                grouped[group_key]["values"].append(float(feedback.value))
            grouped[group_key]["feedback"].append(feedback)
        
        # Calculate averages for each group
        for group_data in grouped.values():
            if group_data["count"] > 0:
                group_data["averageValue"] = group_data["totalValue"] / group_data["count"]
        
        return grouped
    
    def _createGroupKey(self, feedback: Feedback, groupBy: List[str]) -> str:
        """Create a group key for feedback based on grouping dimensions."""
        key_parts = []
        
        for dimension in groupBy:
            if dimension == "tag":
                # Group by tags
                if feedback.tags:
                    key_parts.append(f"tags:{','.join(feedback.tags)}")
                else:
                    key_parts.append("tags:none")
            elif dimension == "capability":
                # Group by MCP capability
                if feedback.capability:
                    key_parts.append(f"capability:{feedback.capability}")
                else:
                    key_parts.append("capability:none")
            elif dimension == "skill":
                # Group by A2A skill
                if feedback.skill:
                    key_parts.append(f"skill:{feedback.skill}")
                else:
                    key_parts.append("skill:none")
            elif dimension == "task":
                # Group by A2A task
                if feedback.task:
                    key_parts.append(f"task:{feedback.task}")
                else:
                    key_parts.append("task:none")
            elif dimension == "endpoint":
                # Group by endpoint (from context or capability)
                endpoint = None
                if feedback.context and "endpoint" in feedback.context:
                    endpoint = feedback.context["endpoint"]
                elif feedback.capability:
                    endpoint = f"mcp:{feedback.capability}"
                
                if endpoint:
                    key_parts.append(f"endpoint:{endpoint}")
                else:
                    key_parts.append("endpoint:none")
            elif dimension == "time":
                # Group by time periods (daily, weekly, monthly)
                from datetime import datetime
                createdAt = datetime.fromtimestamp(feedback.createdAt)
                key_parts.append(f"time:{createdAt.strftime('%Y-%m')}")  # Monthly grouping
            else:
                # Unknown dimension, use as-is
                key_parts.append(f"{dimension}:unknown")
        
        return "|".join(key_parts)

    def _normalizeTag(self, tag: str) -> str:
        """Normalize string tag (trim, validate length if needed).
        
        Args:
            tag: Tag string to normalize
            
        Returns:
            Normalized tag string
        """
        if not tag:
            return ""
        # Trim whitespace
        normalized = tag.strip()
        # Tags are now strings with no length limit, but we can validate if needed
        return normalized
    
    def _hexBytes32ToTags(self, tag1: str, tag2: str) -> List[str]:
        """Convert hex bytes32 tags back to strings, or return plain strings as-is.
        
        DEPRECATED: This method is kept for backward compatibility with old data
        that may have bytes32 tags. New tags are strings and don't need conversion.
        
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
                    # Remove 0x prefix if present
                    hex_bytes = bytes.fromhex(tag1[2:])
                    tag1_str = hex_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore')
                    if tag1_str:
                        tags.append(tag1_str)
                except Exception as e:
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
                except Exception as e:
                    pass  # Ignore invalid hex strings
        
        return tags
