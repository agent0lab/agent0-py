"""
Tests for core models.
"""

import pytest
from datetime import datetime

from agent0_sdk.core.models import (
    EndpointType, TrustModel, Endpoint, RegistrationFile,
    AgentSummary, Feedback, SearchParams
)


class TestEndpointType:
    """Test EndpointType enum."""
    
    def test_endpoint_types(self):
        """Test endpoint type values."""
        assert EndpointType.MCP.value == "MCP"
        assert EndpointType.A2A.value == "A2A"
        assert EndpointType.ENS.value == "ENS"
        assert EndpointType.DID.value == "DID"


class TestTrustModel:
    """Test TrustModel enum."""
    
    def test_trust_models(self):
        """Test trust model values."""
        assert TrustModel.REPUTATION.value == "reputation"
        assert TrustModel.CRYPTO_ECONOMIC.value == "crypto-economic"
        assert TrustModel.TEE_ATTESTATION.value == "tee-attestation"


class TestEndpoint:
    """Test Endpoint class."""
    
    def test_endpoint_creation(self):
        """Test endpoint creation."""
        endpoint = Endpoint(
            type=EndpointType.MCP,
            value="https://mcp.example.com/",
            meta={"version": "1.0"}
        )
        
        assert endpoint.type == EndpointType.MCP
        assert endpoint.value == "https://mcp.example.com/"
        assert endpoint.meta == {"version": "1.0"}
    
    def test_endpoint_default_meta(self):
        """Test endpoint with default meta."""
        endpoint = Endpoint(type=EndpointType.A2A, value="https://a2a.example.com/")
        assert endpoint.meta == {}


class TestRegistrationFile:
    """Test RegistrationFile class."""
    
    def test_registration_file_creation(self):
        """Test registration file creation."""
        rf = RegistrationFile(
            name="Test Agent",
            description="A test agent",
            image="https://example.com/image.png"
        )
        
        assert rf.name == "Test Agent"
        assert rf.description == "A test agent"
        assert rf.image == "https://example.com/image.png"
        assert rf.active is False
        assert rf.x402support is False
        assert rf.endpoints == []
        assert rf.trustModels == []
    
    def test_registration_file_to_dict(self):
        """Test conversion to dictionary."""
        rf = RegistrationFile(
            name="Test Agent",
            description="A test agent",
            image="https://example.com/image.png",
            agentId="1:123",
            endpoints=[
                Endpoint(type=EndpointType.MCP, value="https://mcp.example.com/")
            ],
            trustModels=[TrustModel.REPUTATION]
        )
        
        data = rf.to_dict()
        
        assert data["name"] == "Test Agent"
        assert data["description"] == "A test agent"
        assert data["image"] == "https://example.com/image.png"
        assert data["type"] == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
        assert data["x402Support"] is False  # Updated to camelCase per ERC-8004 spec
        assert len(data["services"]) == 1
        assert data["services"][0]["name"] == "MCP"
        assert data["services"][0]["endpoint"] == "https://mcp.example.com/"
        assert data["supportedTrust"] == ["reputation"]
    
    def test_registration_file_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "name": "Test Agent",
            "description": "A test agent",
            "image": "https://example.com/image.png",
            "services": [
                {
                    "name": "MCP",
                    "endpoint": "https://mcp.example.com/",
                    "version": "1.0"
                }
            ],
            "supportedTrust": ["reputation"],
            "x402support": True
        }
        
        rf = RegistrationFile.from_dict(data)
        
        assert rf.name == "Test Agent"
        assert rf.description == "A test agent"
        assert rf.image == "https://example.com/image.png"
        assert rf.x402support is True
        assert len(rf.endpoints) == 1
        assert rf.endpoints[0].type == EndpointType.MCP
        assert rf.endpoints[0].value == "https://mcp.example.com/"
        assert rf.endpoints[0].meta == {"version": "1.0"}
        assert len(rf.trustModels) == 1
        assert rf.trustModels[0] == TrustModel.REPUTATION


class TestAgentSummary:
    """Test AgentSummary class."""
    
    def test_agent_summary_creation(self):
        """Test agent summary creation."""
        summary = AgentSummary(
            chainId=1,
            agentId="1:123",
            name="Test Agent",
            image="https://example.com/image.png",
            description="A test agent",
            owners=["0x123"],
            operators=["0x456"],
            mcp=True,
            a2a=False,
            ens="test.eth",
            did=None,
            walletAddress="0x789",
            supportedTrusts=["onchain_feedback_v1"],
            a2aSkills=[],
            mcpTools=["tool1"],
            mcpPrompts=[],
            mcpResources=[],
            active=True
        )
        
        assert summary.chainId == 1
        assert summary.agentId == "1:123"
        assert summary.name == "Test Agent"
        assert summary.mcp is True
        assert summary.a2a is False
        assert summary.ens == "test.eth"
        assert summary.did is None


class TestFeedback:
    """Test Feedback class."""
    
    def test_feedback_creation(self):
        """Test feedback creation."""
        feedback = Feedback(
            id=("1:123", "0x456", 1),
            agentId="1:123",
            reviewer="0x456",
            value=4.5,
            tags=["quality", "speed"],
            text="Great service!",
            capability="tools"
        )
        
        assert feedback.id == ("1:123", "0x456", 1)
        assert feedback.id_string == "1:123:0x456:1"
        assert feedback.agentId == "1:123"
        assert feedback.reviewer == "0x456"
        assert feedback.value == 4.5
        assert feedback.tags == ["quality", "speed"]
        assert feedback.text == "Great service!"
        assert feedback.capability == "tools"


class TestSearchParams:
    """Test SearchParams class."""
    
    def test_search_params_creation(self):
        """Test search params creation."""
        params = SearchParams(
            name="test",
            mcp=True,
            a2a=False,
            active=True,
            x402support=True
        )
        
        assert params.name == "test"
        assert params.mcp is True
        assert params.a2a is False
        assert params.active is True
        assert params.x402support is True
        assert params.chains is None
    
    def test_search_params_to_dict(self):
        """Test conversion to dictionary."""
        params = SearchParams(
            name="test",
            mcp=True,
            chains=[1, 8453]
        )
        
        data = params.to_dict()
        
        assert data["name"] == "test"
        assert data["mcp"] is True
        assert data["chains"] == [1, 8453]
        assert "a2a" not in data  # None values should be excluded
