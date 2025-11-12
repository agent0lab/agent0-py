"""
Tests for OASF skills and domains management.
"""

import pytest
from unittest.mock import patch, MagicMock

from agent0_sdk.core.sdk import SDK
from agent0_sdk.core.models import EndpointType
from agent0_sdk.core.oasf_validator import validate_skill, validate_domain


class TestOASFManagement:
    """Test OASF skills and domains management."""

    def test_add_skill_without_validation(self):
        """Test adding a skill without validation."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            # Create a mock instance with chain_id attribute
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add skill without validation
            agent.addSkill("custom_skill/test_skill", validate_oasf=False)
            
            # Verify OASF endpoint was created
            oasf_endpoints = [ep for ep in agent.endpoints if ep.type == EndpointType.OASF]
            assert len(oasf_endpoints) == 1
            
            oasf_endpoint = oasf_endpoints[0]
            assert oasf_endpoint.value == "https://github.com/agntcy/oasf/"
            assert oasf_endpoint.meta["version"] == "v0.8.0"
            assert "custom_skill/test_skill" in oasf_endpoint.meta["skills"]

    def test_add_skill_with_validation_valid(self):
        """Test adding a valid skill with validation."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add valid skill with validation
            agent.addSkill("advanced_reasoning_planning/strategic_planning", validate_oasf=True)
            
            # Verify skill was added
            oasf_endpoint = next(ep for ep in agent.endpoints if ep.type == EndpointType.OASF)
            assert "advanced_reasoning_planning/strategic_planning" in oasf_endpoint.meta["skills"]

    def test_add_skill_with_validation_invalid(self):
        """Test adding an invalid skill with validation raises ValueError."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Try to add invalid skill with validation
            with pytest.raises(ValueError, match="Invalid OASF skill slug"):
                agent.addSkill("invalid_skill/does_not_exist", validate_oasf=True)

    def test_add_skill_duplicate(self):
        """Test adding duplicate skill doesn't create duplicates."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add same skill twice
            agent.addSkill("test_skill/slug", validate_oasf=False)
            agent.addSkill("test_skill/slug", validate_oasf=False)
            
            # Verify only one instance exists
            oasf_endpoint = next(ep for ep in agent.endpoints if ep.type == EndpointType.OASF)
            assert oasf_endpoint.meta["skills"].count("test_skill/slug") == 1

    def test_remove_skill_existing(self):
        """Test removing an existing skill."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add skill
            agent.addSkill("test_skill/slug1", validate_oasf=False)
            agent.addSkill("test_skill/slug2", validate_oasf=False)
            
            # Remove one skill
            agent.removeSkill("test_skill/slug1")
            
            # Verify skill was removed
            oasf_endpoint = next(ep for ep in agent.endpoints if ep.type == EndpointType.OASF)
            assert "test_skill/slug1" not in oasf_endpoint.meta["skills"]
            assert "test_skill/slug2" in oasf_endpoint.meta["skills"]

    def test_remove_skill_non_existent(self):
        """Test removing a non-existent skill succeeds silently."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Remove skill when OASF endpoint doesn't exist (should succeed silently)
            agent.removeSkill("non_existent_skill")
            
            # Should not raise an error

    def test_remove_skill_when_endpoint_missing(self):
        """Test removing skill when OASF endpoint doesn't exist."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Remove skill when no OASF endpoint exists
            agent.removeSkill("some_skill")
            
            # Should succeed silently (idempotent)

    def test_add_domain_without_validation(self):
        """Test adding a domain without validation."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add domain without validation
            agent.addDomain("custom_domain/test_domain", validate_oasf=False)
            
            # Verify OASF endpoint was created
            oasf_endpoints = [ep for ep in agent.endpoints if ep.type == EndpointType.OASF]
            assert len(oasf_endpoints) == 1
            
            oasf_endpoint = oasf_endpoints[0]
            assert "custom_domain/test_domain" in oasf_endpoint.meta["domains"]

    def test_add_domain_with_validation_valid(self):
        """Test adding a valid domain with validation."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add valid domain with validation
            agent.addDomain("finance_and_business/investment_services", validate_oasf=True)
            
            # Verify domain was added
            oasf_endpoint = next(ep for ep in agent.endpoints if ep.type == EndpointType.OASF)
            assert "finance_and_business/investment_services" in oasf_endpoint.meta["domains"]

    def test_add_domain_with_validation_invalid(self):
        """Test adding an invalid domain with validation raises ValueError."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Try to add invalid domain with validation
            with pytest.raises(ValueError, match="Invalid OASF domain slug"):
                agent.addDomain("invalid_domain/does_not_exist", validate_oasf=True)

    def test_add_domain_duplicate(self):
        """Test adding duplicate domain doesn't create duplicates."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add same domain twice
            agent.addDomain("test_domain/slug", validate_oasf=False)
            agent.addDomain("test_domain/slug", validate_oasf=False)
            
            # Verify only one instance exists
            oasf_endpoint = next(ep for ep in agent.endpoints if ep.type == EndpointType.OASF)
            assert oasf_endpoint.meta["domains"].count("test_domain/slug") == 1

    def test_remove_domain_existing(self):
        """Test removing an existing domain."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add domains
            agent.addDomain("test_domain/slug1", validate_oasf=False)
            agent.addDomain("test_domain/slug2", validate_oasf=False)
            
            # Remove one domain
            agent.removeDomain("test_domain/slug1")
            
            # Verify domain was removed
            oasf_endpoint = next(ep for ep in agent.endpoints if ep.type == EndpointType.OASF)
            assert "test_domain/slug1" not in oasf_endpoint.meta["domains"]
            assert "test_domain/slug2" in oasf_endpoint.meta["domains"]

    def test_remove_domain_non_existent(self):
        """Test removing a non-existent domain succeeds silently."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Remove domain when OASF endpoint doesn't exist (should succeed silently)
            agent.removeDomain("non_existent_domain")
            
            # Should not raise an error

    def test_method_chaining(self):
        """Test method chaining."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Chain multiple operations
            agent.addSkill("skill1", validate_oasf=False)\
                 .addDomain("domain1", validate_oasf=False)\
                 .addSkill("skill2", validate_oasf=False)\
                 .removeSkill("skill1")
            
            # Verify results
            oasf_endpoint = next(ep for ep in agent.endpoints if ep.type == EndpointType.OASF)
            assert "skill1" not in oasf_endpoint.meta["skills"]
            assert "skill2" in oasf_endpoint.meta["skills"]
            assert "domain1" in oasf_endpoint.meta["domains"]

    def test_serialization_deserialization(self):
        """Test that OASF data persists through serialization/deserialization."""
        with patch('agent0_sdk.core.sdk.Web3Client') as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.chain_id = 11155111
            mock_web3_class.return_value = mock_web3_instance
            
            sdk = SDK(
                chainId=11155111,
                signer="0x1234567890abcdef1234567890abcdef12345678",
                rpcUrl="https://eth-sepolia.g.alchemy.com/v2/test"
            )
            
            agent = sdk.createAgent("Test Agent", "A test agent")
            
            # Add skills and domains
            agent.addSkill("test_skill/slug1", validate_oasf=False)
            agent.addSkill("test_skill/slug2", validate_oasf=False)
            agent.addDomain("test_domain/slug1", validate_oasf=False)
            
            # Serialize to dict
            reg_file_dict = agent.registration_file.to_dict()
            
            # Find OASF endpoint in serialized data
            oasf_endpoint_dict = next(
                ep for ep in reg_file_dict["endpoints"] 
                if ep["name"] == "OASF"
            )
            
            # Verify data is present
            assert "test_skill/slug1" in oasf_endpoint_dict["skills"]
            assert "test_skill/slug2" in oasf_endpoint_dict["skills"]
            assert "test_domain/slug1" in oasf_endpoint_dict["domains"]
            
            # Deserialize back
            from agent0_sdk.core.models import RegistrationFile
            new_reg_file = RegistrationFile.from_dict(reg_file_dict)
            
            # Verify OASF endpoint was restored
            oasf_endpoints = [ep for ep in new_reg_file.endpoints if ep.type == EndpointType.OASF]
            assert len(oasf_endpoints) == 1
            
            oasf_endpoint = oasf_endpoints[0]
            assert "test_skill/slug1" in oasf_endpoint.meta["skills"]
            assert "test_skill/slug2" in oasf_endpoint.meta["skills"]
            assert "test_domain/slug1" in oasf_endpoint.meta["domains"]


class TestOASFValidator:
    """Test OASF validator utilities."""

    def test_validate_skill_valid(self):
        """Test validating a valid skill."""
        assert validate_skill("advanced_reasoning_planning/strategic_planning") is True

    def test_validate_skill_invalid(self):
        """Test validating an invalid skill."""
        assert validate_skill("invalid_skill/does_not_exist") is False

    def test_validate_domain_valid(self):
        """Test validating a valid domain."""
        assert validate_domain("finance_and_business/investment_services") is True

    def test_validate_domain_invalid(self):
        """Test validating an invalid domain."""
        assert validate_domain("invalid_domain/does_not_exist") is False

