"""
Tests for SDK class.
"""

import pytest
from unittest.mock import Mock, patch

from agent0_sdk.core.sdk import SDK
from agent0_sdk.core.models import EndpointType, TrustModel


class TestSDK:
    """Test SDK class."""
    
    def test_sdk_initialization(self):
        """Test SDK initialization."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            mock_web3.return_value.chain_id = 11155111
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            assert sdk.chainId == 11155111
            assert sdk.rpcUrl == "https://eth-sepolia.g.alchemy.com/v2/test"
            mock_web3.assert_called_once()
    
    def test_create_agent(self):
        """Test agent creation."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            mock_web3.return_value.chain_id = 11155111
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent(
                name="Test Agent",
                description="A test agent",
                image="https://example.com/image.png"
            )
            
            assert agent.name == "Test Agent"
            assert agent.description == "A test agent"
            assert agent.image == "https://example.com/image.png"
            assert agent.sdk == sdk
    
    def test_registries(self):
        """Test registry resolution."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            mock_web3.return_value.chain_id = 11155111
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
        registries = sdk.registries()
        assert "IDENTITY" in registries
        assert "REPUTATION" in registries
        # VALIDATION registry commented out until deployed
        # assert "VALIDATION" in registries
    
    def test_set_chain(self):
        """Test chain switching."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            mock_web3.return_value.chain_id = 11155111
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            # Base Sepolia temporarily disabled - contracts not deployed yet
            # sdk.set_chain(84532)  # Switch to Base Sepolia
            # assert sdk.chainId == 84532
            # assert sdk._registries["IDENTITY"] is not None  # Should have Base Sepolia registry
            pass  # Test skipped until Base Sepolia contracts are deployed

    def test_load_agent_with_empty_agent_uri_returns_partial_agent(self):
        """If agentURI (tokenURI) is empty on-chain, loadAgent should return a partial Agent (no crash)."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            # Mock web3 client and contract calls
            web3_instance = mock_web3.return_value
            web3_instance.get_contract.return_value = Mock()

            # tokenURI (represents agentURI) -> "" (missing), ownerOf -> address, getAgentWallet -> zero address
            def call_contract_side_effect(contract, fn_name, *args):
                if fn_name == "tokenURI":  # ERC-721 standard function name, but represents agentURI
                    return ""
                if fn_name == "ownerOf":
                    return "0x1234567890abcdef1234567890abcdef12345678"
                if fn_name == "getAgentWallet":
                    return "0x0000000000000000000000000000000000000000"
                raise AssertionError(f"Unexpected contract call: {fn_name} args={args}")

            web3_instance.call_contract.side_effect = call_contract_side_effect

            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )

            agent = sdk.loadAgent("11155111:1")
            assert agent.agentId == "11155111:1"
            assert agent.agentURI is None
            assert agent.owners == ["0x1234567890abcdef1234567890abcdef12345678"]


class TestAgent:
    """Test Agent class."""
    
    def test_agent_endpoint_management(self):
        """Test agent endpoint management."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            mock_web3.return_value.chain_id = 11155111
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add MCP endpoint
            agent.setMCP("https://mcp.example.com/")
            assert len(agent.endpoints) == 1
            assert agent.endpoints[0].type == EndpointType.MCP
            assert agent.endpoints[0].value == "https://mcp.example.com/"
            assert agent.endpoints[0].meta["version"] == "2025-06-18"
            
            # Add A2A endpoint
            agent.setA2A("https://a2a.example.com/", "1.0")
            assert len(agent.endpoints) == 2
            
            # Add ENS endpoint
            agent.setENS("test-agent.eth")
            assert len(agent.endpoints) == 3
            ens_endpoint = next(ep for ep in agent.endpoints if ep.type == EndpointType.ENS)
            assert ens_endpoint.value == "test-agent.eth"
            assert ens_endpoint.meta["version"] == "1.0"
            
            # Remove specific endpoint
            agent.removeEndpoint(EndpointType.MCP, "https://mcp.example.com/")
            assert len(agent.endpoints) == 2
            assert agent.endpoints[0].type == EndpointType.A2A
            
            # Remove all endpoints
            agent.removeEndpoints()
            assert len(agent.endpoints) == 0
    
    def test_agent_trust_models(self):
        """Test agent trust model management."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            mock_web3.return_value.chain_id = 11155111
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Set trust models using new method
            agent.setTrust(reputation=True, cryptoEconomic=True)
            # Access trustModels through registration_file since property is shadowed by method
            assert len(agent.registration_file.trustModels) == 2
            assert TrustModel.REPUTATION in agent.registration_file.trustModels
            assert TrustModel.CRYPTO_ECONOMIC in agent.registration_file.trustModels
            
            # Set trust models using direct assignment (since trustModels is a property, not callable)
            agent.registration_file.trustModels = [TrustModel.REPUTATION, "custom_trust"]
            assert len(agent.registration_file.trustModels) == 2
            assert TrustModel.REPUTATION in agent.registration_file.trustModels
            assert "custom_trust" in agent.registration_file.trustModels
    
    def test_agent_metadata_management(self):
        """Test agent metadata management."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            mock_web3.return_value.chain_id = 11155111
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Set metadata
            agent.setMetadata({"key1": "value1", "key2": "value2"})
            assert agent.getMetadata() == {"key1": "value1", "key2": "value2"}
            
            # Set single key using setMetadata
            agent.setMetadata({"key3": "value3"})
            assert agent.getMetadata() == {"key1": "value1", "key2": "value2", "key3": "value3"}
            
            # Delete key
            agent.delMetadata("key2")
            assert agent.getMetadata() == {"key1": "value1", "key3": "value3"}
    
    def test_agent_info_update(self):
        """Test agent info updates."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            mock_web3.return_value.chain_id = 11155111
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Update info
            agent.updateInfo(
                name="Updated Agent",
                description="An updated agent",
                image="https://example.com/new-image.png"
            )
            
            assert agent.name == "Updated Agent"
            assert agent.description == "An updated agent"
            assert agent.image == "https://example.com/new-image.png"
            
            # setAgentWallet is on-chain only and requires agent to be registered
            valid_address = "0x1234567890abcdef1234567890abcdef12345678"
            with pytest.raises(ValueError):
            agent.setAgentWallet(valid_address)
    
    def test_agent_json_serialization(self):
        """Test agent JSON serialization."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3:
            mock_web3.return_value.chain_id = 11155111
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            agent.setMCP("https://mcp.example.com/")
            agent.setTrust(reputation=True)
            
            json_data = agent.toJson()
            assert isinstance(json_data, str)
            assert "Test Agent" in json_data
            assert "MCP" in json_data
            assert "reputation" in json_data
            
            # Test x402 support
            agent.setX402Support(True)
            assert agent.x402support is True
            
            json_data_with_x402 = agent.toJson()
            assert "x402Support" in json_data_with_x402  # Updated to camelCase per ERC-8004 spec
            
            # Test active status
            agent.setActive(True)
            assert agent.active is True
            
            agent.setActive(False)
            assert agent.active is False
