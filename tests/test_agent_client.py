"""
Tests for AgentClient - HTTP/REST-based agent execution client.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from agent0_sdk.core.agent_client import AgentClient


class TestAgentClientInitialization:
    """Test AgentClient initialization and agent card loading."""

    @patch('requests.get')
    def test_init_loads_agent_card(self, mock_get):
        """Test that initialization loads agent card from URL."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000",
            "preferredTransport": "HTTP+JSON",
            "capabilities": {}
        }
        mock_get.return_value = mock_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")

        assert client.agent_card["name"] == "Test Agent"
        assert client.endpoint_url == "http://localhost:3000"
        mock_get.assert_called_once_with("http://example.com/agent.json", timeout=10)

    @patch('requests.get')
    def test_init_detects_x402_extension(self, mock_get):
        """Test that x402 extension is detected from agent card."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Paid Agent",
            "url": "http://localhost:3000",
            "capabilities": {
                "extensions": [
                    {
                        "uri": "https://agent0.network/extensions/x402",
                        "params": {
                            "gateway_url": "http://localhost:3000/process",
                            "price_usdc": "0.05"
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")

        assert client.x402_config is not None
        assert client.x402_config["gateway_url"] == "http://localhost:3000/process"
        assert client.x402_config["price_usdc"] == "0.05"

    @patch('requests.get')
    def test_init_missing_url_raises_error(self, mock_get):
        """Test that missing URL in agent card raises error."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test Agent"
            # Missing 'url' field
        }
        mock_get.return_value = mock_response

        with pytest.raises(Exception, match="No 'url' field in agent card|Failed to load agent card"):
            AgentClient(agent_card_url="http://example.com/agent.json")

    @patch('requests.get')
    def test_init_network_error_raises_exception(self, mock_get):
        """Test that network errors during card loading raise exception."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        with pytest.raises(Exception, match="Failed to load agent card"):
            AgentClient(agent_card_url="http://example.com/agent.json")

    @patch('requests.get')
    def test_init_with_custom_timeout(self, mock_get):
        """Test initialization with custom timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000"
        }
        mock_get.return_value = mock_response

        client = AgentClient(
            agent_card_url="http://example.com/agent.json",
            timeout=60
        )

        assert client.timeout == 60


class TestAgentClientInfo:
    """Test agent information retrieval methods."""

    @patch('requests.get')
    def test_get_info(self, mock_get):
        """Test get_info returns agent card data."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000",
            "description": "A test agent"
        }
        mock_get.return_value = mock_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")
        info = client.get_info()

        assert info["name"] == "Test Agent"
        assert info["description"] == "A test agent"

    @patch('requests.get')
    def test_get_skills_with_skills(self, mock_get):
        """Test get_skills returns skill list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000",
            "skills": [
                {"name": "search", "description": "Search capability"},
                {"name": "analyze", "description": "Analysis capability"}
            ]
        }
        mock_get.return_value = mock_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")
        skills = client.get_skills()

        assert len(skills) == 2
        assert skills[0]["name"] == "search"
        assert skills[1]["name"] == "analyze"

    @patch('requests.get')
    def test_get_skills_no_skills(self, mock_get):
        """Test get_skills returns empty list when no skills defined."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000"
        }
        mock_get.return_value = mock_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")
        skills = client.get_skills()

        assert skills == []


class TestAgentClientHTTPCalls:
    """Test HTTP+JSON agent calling."""

    @patch('requests.get')
    @patch('requests.post')
    def test_call_http_json_basic(self, mock_post, mock_get):
        """Test basic HTTP+JSON call."""
        # Setup agent card
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000",
            "preferredTransport": "HTTP+JSON"
        }
        mock_get.return_value = mock_get_response

        # Setup agent response
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {
            "response": "Test response"
        }
        mock_post.return_value = mock_post_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")
        result = client.call("Test message")

        assert result["response"] == "Test response"
        mock_post.assert_called_once()

        # Verify request payload
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://localhost:3000"
        assert call_args[1]["json"]["message"] == "Test message"

    @patch('requests.get')
    @patch('requests.post')
    def test_call_with_skill(self, mock_post, mock_get):
        """Test call with specific skill."""
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000"
        }
        mock_get.return_value = mock_get_response

        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {"response": "Skill response"}
        mock_post.return_value = mock_post_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")
        result = client.call("Test message", skill="search")

        # Verify skill was included in payload
        call_args = mock_post.call_args
        assert call_args[1]["json"]["skill"] == "search"

    @patch('requests.get')
    @patch('requests.post')
    def test_call_with_context(self, mock_post, mock_get):
        """Test call with additional context."""
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000"
        }
        mock_get.return_value = mock_get_response

        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {"response": "Context response"}
        mock_post.return_value = mock_post_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")
        context = {"user_id": "123", "session": "abc"}
        result = client.call("Test message", context=context)

        # Verify context was merged into payload
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["user_id"] == "123"
        assert payload["session"] == "abc"

    @patch('requests.get')
    @patch('requests.post')
    def test_call_network_error(self, mock_post, mock_get):
        """Test handling of network errors during call."""
        import requests

        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000"
        }
        mock_get.return_value = mock_get_response

        mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

        client = AgentClient(agent_card_url="http://example.com/agent.json")

        with pytest.raises(Exception, match="Failed to call agent"):
            client.call("Test message")

    @patch('requests.get')
    @patch('requests.post')
    def test_call_unsupported_transport(self, mock_post, mock_get):
        """Test error on unsupported transport."""
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000",
            "preferredTransport": "GRPC"  # Unsupported
        }
        mock_get.return_value = mock_get_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")

        with pytest.raises(ValueError, match="Unsupported transport"):
            client.call("Test message")


class TestAgentClientX402Integration:
    """Test x402 payment integration."""

    @patch('requests.get')
    def test_call_with_x402_client(self, mock_get):
        """Test that call routes to x402 when x402 client is provided."""
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "name": "Paid Agent",
            "url": "http://localhost:3000",
            "capabilities": {
                "extensions": [
                    {
                        "uri": "https://agent0.network/extensions/x402",
                        "params": {
                            "gateway_url": "http://localhost:3000/process",
                            "price_usdc": "0.05"
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_get_response

        # Mock x402 client
        mock_x402_client = Mock()
        mock_x402_client.process_payment.return_value = {
            "success": True,
            "task": {"status": {"message": {"parts": [{"kind": "text", "text": "Paid response"}]}}}
        }

        client = AgentClient(
            agent_card_url="http://example.com/agent.json",
            x402_client=mock_x402_client
        )

        result = client.call("Test message")

        # Verify x402 client was called
        mock_x402_client.process_payment.assert_called_once()
        call_args = mock_x402_client.process_payment.call_args
        assert call_args[1]["gateway_url"] == "http://localhost:3000/process"
        assert call_args[1]["message"] == "Test message"

    @patch('requests.get')
    def test_call_without_x402_client_uses_http(self, mock_get):
        """Test that call uses HTTP when x402 config exists but no client."""
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "name": "Paid Agent",
            "url": "http://localhost:3000",
            "capabilities": {
                "extensions": [
                    {
                        "uri": "https://agent0.network/extensions/x402",
                        "params": {"gateway_url": "http://localhost:3000/process"}
                    }
                ]
            }
        }
        mock_get.return_value = mock_get_response

        client = AgentClient(
            agent_card_url="http://example.com/agent.json"
            # No x402_client provided
        )

        with patch('requests.post') as mock_post:
            mock_post_response = Mock()
            mock_post_response.status_code = 200
            mock_post_response.json.return_value = {"response": "HTTP response"}
            mock_post.return_value = mock_post_response

            result = client.call("Test message")

            # Should fall back to HTTP
            mock_post.assert_called_once()


class TestAgentClientHealthCheck:
    """Test agent health checking."""

    @patch('requests.get')
    @patch('requests.post')
    def test_health_check_success(self, mock_post, mock_get):
        """Test successful health check."""
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000"
        }
        mock_get.return_value = mock_get_response

        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = {"status": "healthy"}
        mock_post.return_value = mock_post_response

        client = AgentClient(agent_card_url="http://example.com/agent.json")
        result = client.health_check()

        assert result is True

    @patch('requests.get')
    @patch('requests.post')
    def test_health_check_failure(self, mock_post, mock_get):
        """Test failed health check."""
        import requests

        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            "name": "Test Agent",
            "url": "http://localhost:3000"
        }
        mock_get.return_value = mock_get_response

        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        client = AgentClient(agent_card_url="http://example.com/agent.json")
        result = client.health_check()

        assert result is False
