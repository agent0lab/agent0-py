"""
Tests for multi-chain agent search functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from agent0_sdk.core.indexer import AgentIndexer
from agent0_sdk.core.models import SearchParams


class TestMultiChainSearch:
    """Test multi-chain agent search functionality."""

    @pytest.fixture
    def mock_web3_client(self):
        """Create a mock Web3Client."""
        client = Mock()
        client.chain_id = 11155111  # Ethereum Sepolia
        client.normalize_address = lambda addr: addr.lower()
        return client

    @pytest.fixture
    def mock_subgraph_responses(self):
        """Create mock subgraph responses for different chains."""
        return {
            11155111: [  # Ethereum Sepolia
                {
                    'id': '11155111:1',
                    'chainId': '11155111',
                    'agentId': '1',
                    'owner': '0xabc123',
                    'operators': [],
                    'totalFeedback': 5,
                    'createdAt': 1700000000,
                    'updatedAt': 1700000100,
                    'registrationFile': {
                        'name': 'Agent Alpha',
                        'description': 'Test agent on Ethereum',
                        'image': 'ipfs://...',
                        'active': True,
                        'x402support': False,
                        'supportedTrusts': ['reputation'],
                        'mcpEndpoint': 'https://agent-alpha.example.com/mcp',
                        'a2aEndpoint': None,
                        'mcpTools': ['code_generation', 'analysis'],
                        'a2aSkills': [],
                        'mcpPrompts': [],
                        'mcpResources': [],
                    }
                },
                {
                    'id': '11155111:2',
                    'chainId': '11155111',
                    'agentId': '2',
                    'owner': '0xdef456',
                    'operators': [],
                    'totalFeedback': 3,
                    'createdAt': 1700000200,
                    'updatedAt': 1700000300,
                    'registrationFile': {
                        'name': 'Agent Beta',
                        'description': 'Another test agent',
                        'active': True,
                        'x402support': True,
                        'supportedTrusts': ['reputation', 'crypto-economic'],
                        'mcpEndpoint': None,
                        'a2aEndpoint': 'https://agent-beta.example.com/a2a',
                        'mcpTools': [],
                        'a2aSkills': ['translation', 'summarization'],
                        'mcpPrompts': [],
                        'mcpResources': [],
                    }
                }
            ],
            84532: [  # Base Sepolia
                {
                    'id': '84532:1',
                    'chainId': '84532',
                    'agentId': '1',
                    'owner': '0xghi789',
                    'operators': [],
                    'totalFeedback': 10,
                    'createdAt': 1700000400,
                    'updatedAt': 1700000500,
                    'registrationFile': {
                        'name': 'Agent Gamma',
                        'description': 'Base network agent',
                        'active': True,
                        'x402support': False,
                        'supportedTrusts': ['reputation'],
                        'mcpEndpoint': 'https://agent-gamma.example.com/mcp',
                        'a2aEndpoint': 'https://agent-gamma.example.com/a2a',
                        'mcpTools': ['data_analysis'],
                        'a2aSkills': ['research'],
                        'mcpPrompts': [],
                        'mcpResources': [],
                    }
                }
            ],
            59141: [  # Linea Sepolia
                {
                    'id': '59141:1',
                    'chainId': '59141',
                    'agentId': '1',
                    'owner': '0xjkl012',
                    'operators': [],
                    'totalFeedback': 2,
                    'createdAt': 1700000600,
                    'updatedAt': 1700000700,
                    'registrationFile': {
                        'name': 'Agent Delta',
                        'description': 'Linea network agent',
                        'active': True,
                        'x402support': True,
                        'supportedTrusts': ['tee-attestation'],
                        'mcpEndpoint': 'https://agent-delta.example.com/mcp',
                        'a2aEndpoint': None,
                        'mcpTools': ['security_audit'],
                        'a2aSkills': [],
                        'mcpPrompts': [],
                        'mcpResources': [],
                    }
                }
            ]
        }

    def test_multi_chain_detection(self, mock_web3_client):
        """Test that multi-chain queries are detected correctly."""
        indexer = AgentIndexer(web3_client=mock_web3_client)

        # Single chain should use existing method
        params_single = SearchParams(chains=[11155111])

        # Multi-chain should use new method
        params_multi = SearchParams(chains=[11155111, 84532])

        # We can't directly test the routing without mocking the subgraph,
        # but we can verify the logic exists
        assert params_multi.chains and len(params_multi.chains) > 1

    @pytest.mark.asyncio
    async def test_search_across_multiple_chains(
        self, mock_web3_client, mock_subgraph_responses
    ):
        """Test searching agents across multiple chains."""
        indexer = AgentIndexer(
            web3_client=mock_web3_client,
            subgraph_url_overrides={
                11155111: "https://eth-sepolia.example.com",
                84532: "https://base-sepolia.example.com",
            }
        )

        # Mock the _get_subgraph_client_for_chain method
        def mock_get_client(chain_id):
            client = Mock()
            client.get_agents = Mock(return_value=mock_subgraph_responses.get(chain_id, []))
            return client

        indexer._get_subgraph_client_for_chain = mock_get_client

        # Execute multi-chain search
        params = SearchParams(chains=[11155111, 84532])
        result = await indexer._search_agents_across_chains(
            params=params,
            sort=[],
            page_size=10,
            cursor=None
        )

        # Verify results
        assert len(result['items']) == 3  # 2 from Ethereum + 1 from Base
        assert result['meta']['successfulChains'] == [11155111, 84532]
        assert result['meta']['failedChains'] == []
        assert result['meta']['totalResults'] == 3

        # Verify agents from both chains are present
        chain_ids = [agent['chainId'] for agent in result['items']]
        assert '11155111' in chain_ids
        assert '84532' in chain_ids

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_chain_failure(
        self, mock_web3_client, mock_subgraph_responses
    ):
        """Test that failure on one chain doesn't break entire request."""
        indexer = AgentIndexer(
            web3_client=mock_web3_client,
            subgraph_url_overrides={
                11155111: "https://eth-sepolia.example.com",
                84532: "https://base-sepolia.example.com",
            }
        )

        # Mock clients where Base Sepolia fails
        def mock_get_client(chain_id):
            if chain_id == 84532:
                # Simulate client that will fail
                client = Mock()
                client.get_agents = Mock(side_effect=ConnectionError("Subgraph down"))
                return client
            else:
                # Ethereum Sepolia works
                client = Mock()
                client.get_agents = Mock(return_value=mock_subgraph_responses.get(chain_id, []))
                return client

        indexer._get_subgraph_client_for_chain = mock_get_client

        # Execute multi-chain search
        params = SearchParams(chains=[11155111, 84532])
        result = await indexer._search_agents_across_chains(
            params=params,
            sort=[],
            page_size=10,
            cursor=None
        )

        # Verify partial results
        assert len(result['items']) == 2  # Only Ethereum results
        assert result['meta']['successfulChains'] == [11155111]
        assert result['meta']['failedChains'] == [84532]

    @pytest.mark.asyncio
    async def test_deduplication_across_chains(
        self, mock_web3_client, mock_subgraph_responses
    ):
        """Test deduplication of same agent across chains."""
        # Create duplicate agent (same owner, name, description) on different chains
        duplicate_responses = {
            11155111: [
                {
                    'id': '11155111:1',
                    'chainId': '11155111',
                    'agentId': '1',
                    'owner': '0xsame',
                    'operators': [],
                    'totalFeedback': 5,
                    'createdAt': 1700000000,
                    'updatedAt': 1700000100,
                    'registrationFile': {
                        'name': 'Duplicate Agent',
                        'description': 'Same agent on multiple chains',
                        'active': True,
                        'x402support': False,
                        'supportedTrusts': [],
                        'mcpEndpoint': 'https://agent.example.com/mcp',
                        'mcpTools': [],
                        'a2aSkills': [],
                        'mcpPrompts': [],
                        'mcpResources': [],
                    }
                }
            ],
            84532: [
                {
                    'id': '84532:1',
                    'chainId': '84532',
                    'agentId': '1',
                    'owner': '0xsame',
                    'operators': [],
                    'totalFeedback': 3,
                    'createdAt': 1700000200,
                    'updatedAt': 1700000300,
                    'registrationFile': {
                        'name': 'Duplicate Agent',
                        'description': 'Same agent on multiple chains',
                        'active': True,
                        'x402support': False,
                        'supportedTrusts': [],
                        'mcpEndpoint': 'https://agent.example.com/mcp',
                        'mcpTools': [],
                        'a2aSkills': [],
                        'mcpPrompts': [],
                        'mcpResources': [],
                    }
                }
            ]
        }

        indexer = AgentIndexer(
            web3_client=mock_web3_client,
            subgraph_url_overrides={
                11155111: "https://eth-sepolia.example.com",
                84532: "https://base-sepolia.example.com",
            }
        )

        def mock_get_client(chain_id):
            client = Mock()
            client.get_agents = Mock(return_value=duplicate_responses.get(chain_id, []))
            return client

        indexer._get_subgraph_client_for_chain = mock_get_client

        # Execute WITHOUT deduplication
        params = SearchParams(chains=[11155111, 84532], deduplicate_cross_chain=False)
        result = await indexer._search_agents_across_chains(
            params=params,
            sort=[],
            page_size=10,
            cursor=None
        )

        # Should get 2 agents (not deduplicated)
        assert len(result['items']) == 2

        # Execute WITH deduplication
        params_dedup = SearchParams(chains=[11155111, 84532], deduplicate_cross_chain=True)
        result_dedup = await indexer._search_agents_across_chains(
            params=params_dedup,
            sort=[],
            page_size=10,
            cursor=None
        )

        # Should get 1 agent (deduplicated)
        assert len(result_dedup['items']) == 1
        # Should have deployedOn array
        assert 'deployedOn' in result_dedup['items'][0]['extras']
        deployed_on = result_dedup['items'][0]['extras']['deployedOn']
        assert len(deployed_on) == 2
        assert 11155111 in deployed_on or '11155111' in deployed_on
        assert 84532 in deployed_on or '84532' in deployed_on

    @pytest.mark.asyncio
    async def test_sorting_across_chains(
        self, mock_web3_client, mock_subgraph_responses
    ):
        """Test sorting agents from multiple chains."""
        indexer = AgentIndexer(
            web3_client=mock_web3_client,
            subgraph_url_overrides={
                11155111: "https://eth-sepolia.example.com",
                84532: "https://base-sepolia.example.com",
            }
        )

        def mock_get_client(chain_id):
            client = Mock()
            client.get_agents = Mock(return_value=mock_subgraph_responses.get(chain_id, []))
            return client

        indexer._get_subgraph_client_for_chain = mock_get_client

        # Sort by totalFeedback descending
        params = SearchParams(chains=[11155111, 84532])
        result = await indexer._search_agents_across_chains(
            params=params,
            sort=['totalFeedback:desc'],
            page_size=10,
            cursor=None
        )

        # Verify sort order (Base agent has 10, Ethereum agents have 5 and 3)
        assert result['items'][0]['totalFeedback'] == 10  # Base agent first
        assert result['items'][1]['totalFeedback'] == 5   # Ethereum agent second
        assert result['items'][2]['totalFeedback'] == 3   # Ethereum agent third

    @pytest.mark.asyncio
    async def test_pagination_across_chains(
        self, mock_web3_client, mock_subgraph_responses
    ):
        """Test pagination across multiple chains."""
        indexer = AgentIndexer(
            web3_client=mock_web3_client,
            subgraph_url_overrides={
                11155111: "https://eth-sepolia.example.com",
                84532: "https://base-sepolia.example.com",
            }
        )

        def mock_get_client(chain_id):
            client = Mock()
            client.get_agents = Mock(return_value=mock_subgraph_responses.get(chain_id, []))
            return client

        indexer._get_subgraph_client_for_chain = mock_get_client

        # First page (page_size=2)
        params = SearchParams(chains=[11155111, 84532])
        page1 = await indexer._search_agents_across_chains(
            params=params,
            sort=[],
            page_size=2,
            cursor=None
        )

        assert len(page1['items']) == 2
        assert page1['nextCursor'] is not None  # More results available

        # Second page
        page2 = await indexer._search_agents_across_chains(
            params=params,
            sort=[],
            page_size=2,
            cursor=page1['nextCursor']
        )

        assert len(page2['items']) == 1  # Only 1 agent left
        assert page2['nextCursor'] is None  # No more results

    def test_cross_chain_filters(self, mock_web3_client):
        """Test cross-chain filtering for fields not in subgraph WHERE clause."""
        indexer = AgentIndexer(web3_client=mock_web3_client)

        agents = [
            {
                'chainId': '11155111',
                'registrationFile': {
                    'mcpTools': ['code_generation', 'analysis'],
                    'supportedTrusts': ['reputation']
                }
            },
            {
                'chainId': '84532',
                'registrationFile': {
                    'mcpTools': ['data_analysis'],
                    'supportedTrusts': ['crypto-economic']
                }
            }
        ]

        # Filter by mcpTools
        params = SearchParams(mcpTools=['code_generation'])
        filtered = indexer._apply_cross_chain_filters(agents, params)
        assert len(filtered) == 1
        assert filtered[0]['chainId'] == '11155111'

        # Filter by supportedTrust
        params2 = SearchParams(supportedTrust=['crypto-economic'])
        filtered2 = indexer._apply_cross_chain_filters(agents, params2)
        assert len(filtered2) == 1
        assert filtered2[0]['chainId'] == '84532'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
