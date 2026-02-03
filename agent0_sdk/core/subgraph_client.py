"""
Subgraph client for querying The Graph network.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


class SubgraphClient:
    """Client for querying the subgraph GraphQL API."""

    def __init__(self, subgraph_url: str):
        """Initialize subgraph client."""
        self.subgraph_url = subgraph_url

    def query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against the subgraph.
        
        Args:
            query: GraphQL query string
            variables: Optional variables for the query
            
        Returns:
            JSON response from the subgraph
        """
        def _do_query(q: str) -> Dict[str, Any]:
            response = requests.post(
                self.subgraph_url,
                json={'query': q, 'variables': variables or {}},
                headers={'Content-Type': 'application/json'},
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            if 'errors' in result:
                error_messages = [err.get('message', 'Unknown error') for err in result['errors']]
                raise ValueError(f"GraphQL errors: {', '.join(error_messages)}")
            return result.get('data', {})

        try:
            return _do_query(query)
        except ValueError as e:
            # Backwards/forwards compatibility for hosted subgraphs:
            # Some deployments still expose `responseUri` instead of `responseURI`.
            msg = str(e)
            if ("has no field" in msg and "responseURI" in msg) and ("responseURI" in query):
                logger.debug("Subgraph schema missing responseURI; retrying query with responseUri")
                return _do_query(query.replace("responseURI", "responseUri"))
            # Some deployments still expose `x402support` instead of `x402Support`.
            if (("has no field" in msg and "x402Support" in msg) or ("Cannot query field" in msg and "x402Support" in msg)) and (
                "x402Support" in query
            ):
                logger.debug("Subgraph schema missing x402Support; retrying query with x402support")
                return _do_query(query.replace("x402Support", "x402support"))
            # Some deployments don't expose agentWallet fields on AgentRegistrationFile.
            if (
                "Type `AgentRegistrationFile` has no field `agentWallet`" in msg
                or "Type `AgentRegistrationFile` has no field `agentWalletChainId`" in msg
            ):
                logger.debug("Subgraph schema missing agentWallet fields; retrying query without them")
                q2 = query.replace("agentWalletChainId", "").replace("agentWallet", "")
                return _do_query(q2)
            # Some deployments do not yet expose `hasOASF` on AgentRegistrationFile.
            if (("has no field" in msg and "hasOASF" in msg) or ("Cannot query field" in msg and "hasOASF" in msg)) and (
                "hasOASF" in query
            ):
                logger.debug("Subgraph schema missing hasOASF; retrying query without it")
                return _do_query(query.replace("hasOASF", "oasfEndpoint"))
            raise
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to query subgraph: {e}")

    def get_agents(
        self,
        where: Optional[Dict[str, Any]] = None,
        first: int = 100,
        skip: int = 0,
        order_by: str = "createdAt",
        order_direction: str = "desc",
        include_registration_file: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Query agents from the subgraph.
        
        Args:
            where: Filter conditions
            first: Number of results to return
            skip: Number of results to skip
            order_by: Field to order by
            order_direction: Sort direction (asc/desc)
            include_registration_file: Whether to include full registration file data
            
        Returns:
            List of agent records
        """
        # Build WHERE clause
        where_clause = ""
        if where:
            conditions = []
            for key, value in where.items():
                if isinstance(value, bool):
                    conditions.append(f"{key}: {str(value).lower()}")
                elif isinstance(value, str):
                    conditions.append(f'{key}: "{value}"')
                elif isinstance(value, (int, float)):
                    conditions.append(f"{key}: {value}")
                elif isinstance(value, list):
                    conditions.append(f"{key}: {json.dumps(value)}")
            if conditions:
                where_clause = f"where: {{ {', '.join(conditions)} }}"
        
        # Build registration file fragment
        reg_file_fragment = ""
        if include_registration_file:
            reg_file_fragment = """
            registrationFile {
                id
                agentId
                name
                description
                image
                active
                x402Support
                supportedTrusts
                mcpEndpoint
                mcpVersion
                a2aEndpoint
                a2aVersion
                ens
                did
                agentWallet
                agentWalletChainId
                mcpTools
                mcpPrompts
                mcpResources
                a2aSkills
                createdAt
            }
            """
        
        query = f"""
        {{
            agents(
                {where_clause}
                first: {first}
                skip: {skip}
                orderBy: {order_by}
                orderDirection: {order_direction}
            ) {{
                id
                chainId
                agentId
                agentURI
                agentURIType
                owner
                operators
                totalFeedback
                createdAt
                updatedAt
                lastActivity
                {reg_file_fragment}
            }}
        }}
        """
        
        result = self.query(query)
        return result.get('agents', [])

    # -------------------------------------------------------------------------
    # V2 query helpers (variable-based where clauses; used by unified search)
    # -------------------------------------------------------------------------

    def get_agents_v2(
        self,
        where: Optional[Dict[str, Any]],
        first: int,
        skip: int,
        order_by: str,
        order_direction: str,
    ) -> List[Dict[str, Any]]:
        query = """
        query SearchAgentsV2($where: Agent_filter, $first: Int!, $skip: Int!, $orderBy: Agent_orderBy!, $orderDirection: OrderDirection!) {
            agents(where: $where, first: $first, skip: $skip, orderBy: $orderBy, orderDirection: $orderDirection) {
                id
                chainId
                agentId
                agentURI
                agentURIType
                owner
                operators
                agentWallet
                totalFeedback
                createdAt
                updatedAt
                lastActivity
                registrationFile {
                    id
                    agentId
                    name
                    description
                    image
                    active
                    x402Support
                    supportedTrusts
                    mcpEndpoint
                    mcpVersion
                    a2aEndpoint
                    a2aVersion
                    webEndpoint
                    emailEndpoint
                    hasOASF
                    oasfSkills
                    oasfDomains
                    ens
                    did
                    mcpTools
                    mcpPrompts
                    mcpResources
                    a2aSkills
                    createdAt
                }
            }
        }
        """
        variables = {
            "where": where,
            "first": first,
            "skip": skip,
            "orderBy": order_by,
            "orderDirection": order_direction,
        }
        try:
            data = self.query(query, variables)
            return data.get("agents", [])
        except ValueError as e:
            # Compatibility: some deployments do not support AgentRegistrationFile.hasOASF in the *filter input*.
            # Retry by translating registrationFile_.hasOASF => oasfEndpoint existence checks.
            msg = str(e)
            if where and "hasOASF" in msg and ("AgentRegistrationFile" in msg or "AgentRegistrationFile_filter" in msg):
                def rewrite(node: Any) -> Any:
                    if isinstance(node, list):
                        return [rewrite(x) for x in node]
                    if not isinstance(node, dict):
                        return node
                    out: Dict[str, Any] = {}
                    for k, v in node.items():
                        if k == "registrationFile_" and isinstance(v, dict):
                            rf = dict(v)
                            if "hasOASF" in rf:
                                want = bool(rf.get("hasOASF"))
                                rf.pop("hasOASF", None)
                                if want:
                                    rf["oasfEndpoint_not"] = None
                                else:
                                    rf["oasfEndpoint"] = None
                            out[k] = rewrite(rf)
                        else:
                            out[k] = rewrite(v)
                    return out

                variables2 = dict(variables)
                variables2["where"] = rewrite(where)
                data2 = self.query(query, variables2)
                return data2.get("agents", [])
            raise

    def query_agent_metadatas(self, where: Dict[str, Any], first: int, skip: int) -> List[Dict[str, Any]]:
        query = """
        query AgentMetadatas($where: AgentMetadata_filter, $first: Int!, $skip: Int!) {
            agentMetadatas(where: $where, first: $first, skip: $skip) {
                id
                key
                value
                updatedAt
                agent { id }
            }
        }
        """
        try:
            data = self.query(query, {"where": where, "first": first, "skip": skip})
            return data.get("agentMetadatas", [])
        except ValueError as e:
            # Hosted subgraph compatibility: some deployments expose AgentMetadata list as `agentMetadata_collection`.
            msg = str(e)
            if ("has no field" in msg and "agentMetadatas" in msg) or ("Cannot query field" in msg and "agentMetadatas" in msg):
                query2 = """
                query AgentMetadataCollection($where: AgentMetadata_filter, $first: Int!, $skip: Int!) {
                    agentMetadata_collection(where: $where, first: $first, skip: $skip) {
                        id
                        key
                        value
                        updatedAt
                        agent { id }
                    }
                }
                """
                data2 = self.query(query2, {"where": where, "first": first, "skip": skip})
                return data2.get("agentMetadata_collection", [])
            raise

    def query_feedbacks_minimal(
        self,
        where: Dict[str, Any],
        first: int,
        skip: int,
        order_by: str = "createdAt",
        order_direction: str = "desc",
    ) -> List[Dict[str, Any]]:
        query = """
        query Feedbacks($where: Feedback_filter, $first: Int!, $skip: Int!, $orderBy: Feedback_orderBy!, $orderDirection: OrderDirection!) {
            feedbacks(where: $where, first: $first, skip: $skip, orderBy: $orderBy, orderDirection: $orderDirection) {
                id
                agent { id }
                clientAddress
                value
                tag1
                tag2
                endpoint
                isRevoked
                createdAt
                responses(first: 1) { id }
            }
        }
        """
        data = self.query(
            query,
            {"where": where, "first": first, "skip": skip, "orderBy": order_by, "orderDirection": order_direction},
        )
        return data.get("feedbacks", [])

    def query_feedback_responses(self, where: Dict[str, Any], first: int, skip: int) -> List[Dict[str, Any]]:
        query = """
        query FeedbackResponses($where: FeedbackResponse_filter, $first: Int!, $skip: Int!) {
            feedbackResponses(where: $where, first: $first, skip: $skip) {
                id
                feedback { id }
                createdAt
            }
        }
        """
        data = self.query(query, {"where": where, "first": first, "skip": skip})
        return data.get("feedbackResponses", [])

    def get_agent_by_id(self, agent_id: str, include_registration_file: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get a specific agent by ID.
        
        Args:
            agent_id: Agent ID in format "chainId:tokenId"
            include_registration_file: Whether to include full registration file data
            
        Returns:
            Agent record or None if not found
        """
        # Build registration file fragment
        reg_file_fragment = ""
        if include_registration_file:
            reg_file_fragment = """
            registrationFile {
                id
                agentId
                name
                description
                image
                active
                x402Support
                supportedTrusts
                mcpEndpoint
                mcpVersion
                a2aEndpoint
                a2aVersion
                ens
                did
                agentWallet
                agentWalletChainId
                mcpTools
                mcpPrompts
                mcpResources
                a2aSkills
                createdAt
            }
            """
        
        query = f"""
        {{
            agent(id: "{agent_id}") {{
                id
                chainId
                agentId
                agentURI
                agentURIType
                owner
                operators
                totalFeedback
                createdAt
                updatedAt
                lastActivity
                {reg_file_fragment}
            }}
        }}
        """
        
        result = self.query(query)
        agent = result.get('agent')
        
        if agent is None:
            return None
        
        return agent

    def get_feedback_for_agent(
        self,
        agent_id: str,
        first: int = 100,
        skip: int = 0,
        include_revoked: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get feedback for a specific agent.
        
        Args:
            agent_id: Agent ID in format "chainId:tokenId"
            first: Number of results to return
            skip: Number of results to skip
            include_revoked: Whether to include revoked feedback
            
        Returns:
            List of feedback records
        """
        query = f"""
        {{
            agent(id: "{agent_id}") {{
                id
                agentId
                feedback(
                    first: {first}
                    skip: {skip}
                    where: {{ isRevoked: {'false' if not include_revoked else 'true'} }}
                    orderBy: createdAt
                    orderDirection: desc
                ) {{
                    id
                    value
                    feedbackIndex
                    tag1
                    tag2
                    endpoint
                    clientAddress
                    feedbackURI
                    feedbackURIType
                    feedbackHash
                    isRevoked
                    createdAt
                    revokedAt
                    feedbackFile {{
                        id
                        text
                        capability
                        name
                        skill
                        task
                        context
                        proofOfPaymentFromAddress
                        proofOfPaymentToAddress
                        proofOfPaymentChainId
                        proofOfPaymentTxHash
                        tag1
                        tag2
                        createdAt
                    }}
                    responses {{
                        id
                        responder
                        responseURI
                        responseHash
                        createdAt
                    }}
                }}
            }}
        }}
        """
        
        result = self.query(query)
        agent = result.get('agent')
        
        if agent is None:
            return []
        
        return agent.get('feedback', [])

    def get_agent_stats(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific agent.
        
        Args:
            agent_id: Agent ID in format "chainId:tokenId"
            
        Returns:
            Agent statistics or None if not found
        """
        query = f"""
        {{
            agentStats(id: "{agent_id}") {{
                agent {{
                    id
                    agentId
                }}
                totalFeedback
                averageFeedbackValue
                totalValidations
                completedValidations
                averageValidationScore
                lastActivity
                updatedAt
            }}
        }}
        """
        
        result = self.query(query)
        return result.get('agentStats')

    def get_protocol_stats(self, chain_id: int) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific protocol/chain.
        
        Args:
            chain_id: Chain ID
            
        Returns:
            Protocol statistics or None if not found
        """
        query = f"""
        {{
            protocol(id: "{chain_id}") {{
                id
                chainId
                name
                identityRegistry
                reputationRegistry
                validationRegistry
                totalAgents
                totalFeedback
                totalValidations
                agents
                tags
                trustModels
                createdAt
                updatedAt
            }}
        }}
        """
        
        result = self.query(query)
        return result.get('protocol')

    def get_global_stats(self) -> Optional[Dict[str, Any]]:
        """
        Get global statistics across all chains.
        
        Returns:
            Global statistics or None if not found
        """
        query = """
        {
            globalStats(id: "stats") {
                totalAgents
                totalFeedback
                totalValidations
                totalProtocols
                agents
                tags
                createdAt
                updatedAt
            }
        }
        """
        
        result = self.query(query)
        return result.get('globalStats')
    
    def get_feedback_by_id(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific feedback entry by ID with responses.
        
        Args:
            feedback_id: Feedback ID in format "chainId:agentId:clientAddress:feedbackIndex"
            
        Returns:
            Feedback record with nested feedbackFile and responses, or None if not found
        """
        query = """
        query GetFeedbackById($feedbackId: ID!) {
            feedback(id: $feedbackId) {
                id
                agent { id agentId chainId }
                clientAddress
                feedbackIndex
                value
                tag1
                tag2
                endpoint
                feedbackURI
                feedbackURIType
                feedbackHash
                isRevoked
                createdAt
                revokedAt
                feedbackFile {
                    id
                    feedbackId
                    text
                    capability
                    name
                    skill
                    task
                    context
                    proofOfPaymentFromAddress
                    proofOfPaymentToAddress
                    proofOfPaymentChainId
                    proofOfPaymentTxHash
                    tag1
                    tag2
                    createdAt
                }
                responses {
                    id
                    responder
                    responseURI
                    responseHash
                    createdAt
                }
            }
        }
        """
        variables = {"feedbackId": feedback_id}
        result = self.query(query, variables)
        return result.get('feedback')
    
    def search_feedback(
        self,
        params: Any,  # SearchFeedbackParams
        first: int = 100,
        skip: int = 0,
        order_by: str = "createdAt",
        order_direction: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        Search for feedback entries with filtering.
        
        Args:
            params: SearchFeedbackParams object with filter criteria
            first: Number of results to return
            skip: Number of results to skip
            order_by: Field to order by
            order_direction: Sort direction (asc/desc)
            
        Returns:
            List of feedback records with nested feedbackFile and responses
        """
        # Build WHERE clause from params
        where_conditions = []
        
        if params.agents is not None and len(params.agents) > 0:
            agent_ids = [f'"{aid}"' for aid in params.agents]
            where_conditions.append(f'agent_in: [{", ".join(agent_ids)}]')
        
        if params.reviewers is not None and len(params.reviewers) > 0:
            reviewers = [f'"{addr}"' for addr in params.reviewers]
            where_conditions.append(f'clientAddress_in: [{", ".join(reviewers)}]')
        
        if not params.includeRevoked:
            where_conditions.append('isRevoked: false')
        
        # Build all non-tag conditions first
        non_tag_conditions = list(where_conditions)
        where_conditions = non_tag_conditions
        
        # Handle tag filtering separately - it needs to be at the top level
        tag_filter_condition = None
        if params.tags is not None and len(params.tags) > 0:
            # Tag search: any of the tags must match in tag1 OR tag2
            # Tags are now stored as human-readable strings in the subgraph
            
            # Build complete condition with all filters for each tag alternative
            # For each tag, create two alternatives: matching tag1 OR matching tag2
            tag_where_items = []
            for tag in params.tags:
                # For tag1 match
                all_conditions_tag1 = non_tag_conditions + [f'tag1: "{tag}"']
                tag_where_items.append(", ".join(all_conditions_tag1))
                # For tag2 match
                all_conditions_tag2 = non_tag_conditions + [f'tag2: "{tag}"']
                tag_where_items.append(", ".join(all_conditions_tag2))
            
            # Join all tag alternatives (each already contains complete filter set)
            tag_filter_condition = ", ".join([f"{{ {item} }}" for item in tag_where_items])
        
        if params.minValue is not None:
            where_conditions.append(f'value_gte: "{params.minValue}"')
        
        if params.maxValue is not None:
            where_conditions.append(f'value_lte: "{params.maxValue}"')
        
        # Feedback file filters
        feedback_file_filters = []
        
        if params.capabilities is not None and len(params.capabilities) > 0:
            capabilities = [f'"{cap}"' for cap in params.capabilities]
            feedback_file_filters.append(f'capability_in: [{", ".join(capabilities)}]')
        
        if params.skills is not None and len(params.skills) > 0:
            skills = [f'"{skill}"' for skill in params.skills]
            feedback_file_filters.append(f'skill_in: [{", ".join(skills)}]')
        
        if params.tasks is not None and len(params.tasks) > 0:
            tasks = [f'"{task}"' for task in params.tasks]
            feedback_file_filters.append(f'task_in: [{", ".join(tasks)}]')
        
        if params.names is not None and len(params.names) > 0:
            names = [f'"{name}"' for name in params.names]
            feedback_file_filters.append(f'name_in: [{", ".join(names)}]')
        
        if feedback_file_filters:
            where_conditions.append(f'feedbackFile_: {{ {", ".join(feedback_file_filters)} }}')
        
        # Use tag_filter_condition if tags were provided, otherwise use standard where clause
        if tag_filter_condition:
            # tag_filter_condition already contains properly formatted items: "{ condition1 }, { condition2 }"
            where_clause = f"where: {{ or: [{tag_filter_condition}] }}"
        elif where_conditions:
            where_clause = f"where: {{ {', '.join(where_conditions)} }}"
        else:
            where_clause = ""
        
        query = f"""
        {{
            feedbacks(
                {where_clause}
                first: {first}
                skip: {skip}
                orderBy: {order_by}
                orderDirection: {order_direction}
            ) {{
                id
                agent {{ id agentId chainId }}
                clientAddress
                feedbackIndex
                value
                tag1
                tag2
                endpoint
                feedbackURI
                feedbackURIType
                feedbackHash
                isRevoked
                createdAt
                revokedAt
                feedbackFile {{
                    id
                    feedbackId
                    text
                    capability
                    name
                    skill
                    task
                    context
                    proofOfPaymentFromAddress
                    proofOfPaymentToAddress
                    proofOfPaymentChainId
                    proofOfPaymentTxHash
                    tag1
                    tag2
                    createdAt
                }}
                responses {{
                    id
                    responder
                    responseURI
                    responseHash
                    createdAt
                }}
            }}
        }}
        """
        
        result = self.query(query)
        return result.get('feedbacks', [])
    
    # NOTE: `search_agents_by_reputation` was removed in favor of unified `SDK.searchAgents()` with `filters.feedback`.
