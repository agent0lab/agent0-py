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
            # Some deployments don't expose agentWallet fields on AgentRegistrationFile.
            if (
                "Type `AgentRegistrationFile` has no field `agentWallet`" in msg
                or "Type `AgentRegistrationFile` has no field `agentWalletChainId`" in msg
            ):
                logger.debug("Subgraph schema missing agentWallet fields; retrying query without them")
                q2 = query.replace("agentWalletChainId", "").replace("agentWallet", "")
                return _do_query(q2)
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
                x402support
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
                x402support
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
                    score
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
                averageScore
                scoreDistribution
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
                score
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
        
        if params.minScore is not None:
            where_conditions.append(f'score_gte: {params.minScore}')
        
        if params.maxScore is not None:
            where_conditions.append(f'score_lte: {params.maxScore}')
        
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
                score
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
    
    def search_agents_by_reputation(
        self,
        agents: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        reviewers: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        tasks: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        minAverageScore: Optional[int] = None,  # 0-100
        includeRevoked: bool = False,
        first: int = 100,
        skip: int = 0,
        order_by: str = "createdAt",
        order_direction: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        Search agents filtered by reputation criteria.
        
        Args:
            agents: List of agent IDs to filter by
            tags: List of tags to filter feedback by
            reviewers: List of reviewer addresses to filter feedback by
            capabilities: List of capabilities to filter feedback by
            skills: List of skills to filter feedback by
            tasks: List of tasks to filter feedback by
            minAverageScore: Minimum average score (0-100) for included agents
            includeRevoked: Whether to include revoked feedback in calculations
            first: Number of results to return
            skip: Number of results to skip
            order_by: Field to order by
            order_direction: Sort direction (asc/desc)
            
        Returns:
            List of agents with averageScore field calculated from filtered feedback
        """
        # Build feedback filter
        feedback_filters = []
        
        if not includeRevoked:
            feedback_filters.append('isRevoked: false')
        
        if tags is not None and len(tags) > 0:
            # Tags are now stored as human-readable strings in the subgraph
            tag_filter = []
            for tag in tags:
                tag_filter.append(f'{{or: [{{tag1: "{tag}"}}, {{tag2: "{tag}"}}]}}')
            feedback_filters.append(f'or: [{", ".join(tag_filter)}]')
        
        if reviewers is not None and len(reviewers) > 0:
            reviewers_list = [f'"{addr}"' for addr in reviewers]
            feedback_filters.append(f'clientAddress_in: [{", ".join(reviewers_list)}]')
        
        # Feedback file filters
        feedback_file_filters = []
        
        if capabilities is not None and len(capabilities) > 0:
            capabilities_list = [f'"{cap}"' for cap in capabilities]
            feedback_file_filters.append(f'capability_in: [{", ".join(capabilities_list)}]')
        
        if skills is not None and len(skills) > 0:
            skills_list = [f'"{skill}"' for skill in skills]
            feedback_file_filters.append(f'skill_in: [{", ".join(skills_list)}]')
        
        if tasks is not None and len(tasks) > 0:
            tasks_list = [f'"{task}"' for task in tasks]
            feedback_file_filters.append(f'task_in: [{", ".join(tasks_list)}]')
        
        if names is not None and len(names) > 0:
            names_list = [f'"{name}"' for name in names]
            feedback_file_filters.append(f'name_in: [{", ".join(names_list)}]')
        
        if feedback_file_filters:
            feedback_filters.append(f'feedbackFile_: {{ {", ".join(feedback_file_filters)} }}')
        
        # If we have feedback filters (tags, capabilities, skills, etc.), we need to first
        # query feedback to get agent IDs, then query those agents
        # Otherwise, query agents directly
        if tags or capabilities or skills or tasks or names or reviewers:
            # First, query feedback to get unique agent IDs that have matching feedback
            feedback_where = f"{{ {', '.join(feedback_filters)} }}" if feedback_filters else "{}"
            
            feedback_query = f"""
            {{
                feedbacks(
                    where: {feedback_where}
                    first: 1000
                    skip: 0
                ) {{
                    agent {{
                        id
                    }}
                }}
            }}
            """
            
            try:
                feedback_result = self.query(feedback_query)
                feedbacks_data = feedback_result.get('feedbacks', [])
                
                # Extract unique agent IDs
                agent_ids_set = set()
                for fb in feedbacks_data:
                    agent = fb.get('agent', {})
                    agent_id = agent.get('id')
                    if agent_id:
                        agent_ids_set.add(agent_id)
                
                if not agent_ids_set:
                    # No agents have matching feedback
                    return []
                
                # Now query only those agents
                agent_ids_list = list(agent_ids_set)
                # Apply any agent filters if specified
                if agents is not None and len(agents) > 0:
                    agent_ids_list = [aid for aid in agent_ids_list if aid in agents]
                    if not agent_ids_list:
                        return []
                
                # Query agents (limit to first N based on pagination)
                agent_ids_str = ', '.join([f'"{aid}"' for aid in agent_ids_list])
                agent_where = f"where: {{ id_in: [{agent_ids_str}] }}"
            except Exception as e:
                logger.warning(f"Failed to query feedback for agent IDs: {e}")
                return []
        else:
            # No feedback filters - query agents directly
            # For reputation search, we want agents that have feedback
            # Filter by totalFeedback > 0 to only get agents with feedback
            agent_filters = ['totalFeedback_gt: 0']  # Only agents with feedback (BigInt comparison)
            if agents is not None and len(agents) > 0:
                agent_ids = [f'"{aid}"' for aid in agents]
                agent_filters.append(f'id_in: [{", ".join(agent_ids)}]')
            
            agent_where = f"where: {{ {', '.join(agent_filters)} }}"
        
        # Build feedback where for agent query (to calculate scores)
        feedback_where_for_agents = f"{{ {', '.join(feedback_filters)} }}" if feedback_filters else "{}"
        
        query = f"""
        {{
            agents(
                {agent_where}
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
                createdAt
                updatedAt
                totalFeedback
                lastActivity
                registrationFile {{
                    id
                    name
                    description
                    image
                    active
                    x402support
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
                }}
                feedback(where: {feedback_where_for_agents}) {{
                    score
                    isRevoked
                    feedbackFile {{
                        capability
                        skill
                        task
                        name
                    }}
                }}
            }}
        }}
        """
        
        try:
            result = self.query(query)
            
            # Check for GraphQL errors
            if 'errors' in result:
                logger.error(f"GraphQL errors in search_agents_by_reputation: {result['errors']}")
                return []
            
            agents_result = result.get('agents', [])
            
            # Calculate average scores
            for agent in agents_result:
                feedbacks = agent.get('feedback', [])
                if feedbacks:
                    scores = [int(fb['score']) for fb in feedbacks if fb.get('score', 0) > 0]
                    if scores:
                        avg_score = sum(scores) / len(scores)
                        agent['averageScore'] = avg_score
                    else:
                        agent['averageScore'] = None
                else:
                    agent['averageScore'] = None
            
            # Filter by minAverageScore
            if minAverageScore is not None:
                agents_result = [
                    agent for agent in agents_result
                    if agent.get('averageScore') is not None and agent['averageScore'] >= minAverageScore
                ]
            
            # For reputation search, filter logic:
            # - If specific agents were requested, return them even if averageScore is None
            #   (the user explicitly asked for these agents, so return them)
            # - If general search (no specific agents), only return agents with reputation data
            if agents is None or len(agents) == 0:
                # General search - only return agents with reputation
                agents_result = [
                    agent for agent in agents_result
                    if agent.get('averageScore') is not None
                ]
            # else: specific agents requested - return all requested agents (even if averageScore is None)
            
            return agents_result
            
        except Exception as e:
            logger.warning(f"Subgraph reputation search failed: {e}")
            return []
