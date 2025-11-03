"""
Simple agent execution client for HTTP/REST-based agents.
Works with standard HTTP+JSON agents.
"""

import logging
import json
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)

try:
    from .x402_client import X402Client
except ImportError:
    X402Client = None


class AgentClient:
    """Simple client for calling HTTP/REST-based agents."""

    def __init__(
        self,
        agent_card_url: str,
        timeout: int = 30,
        x402_client: Optional[Any] = None
    ):
        """
        Initialize agent client from agent card URL.

        Args:
            agent_card_url: URL to the agent's card/manifest
            timeout: Request timeout in seconds
            x402_client: Optional X402Client for micropayments
        """
        self.agent_card_url = agent_card_url
        self.timeout = timeout
        self.agent_card = None
        self.endpoint_url = None
        self.x402_client = x402_client
        self.x402_config = None

        # Load agent card
        self._load_agent_card()

    def _load_agent_card(self):
        """Load and parse the agent card."""
        try:
            response = requests.get(self.agent_card_url, timeout=10)
            response.raise_for_status()
            self.agent_card = response.json()

            # Extract endpoint URL
            self.endpoint_url = self.agent_card.get('url')
            if not self.endpoint_url:
                raise ValueError("No 'url' field in agent card")

            # Check for x402 extension
            capabilities = self.agent_card.get('capabilities', {})
            extensions = capabilities.get('extensions', [])
            for ext in extensions:
                if 'x402' in ext.get('uri', ''):
                    self.x402_config = ext.get('params', {})
                    logger.info(f"x402 payments enabled: ${self.x402_config.get('price_usdc')} USDC per request")

            logger.info(f"Loaded agent: {self.agent_card.get('name')}")
            logger.info(f"Endpoint: {self.endpoint_url}")

        except Exception as e:
            raise Exception(f"Failed to load agent card: {e}")

    def get_info(self) -> Dict[str, Any]:
        """
        Get agent information.

        Returns:
            Agent card data
        """
        return self.agent_card

    def get_skills(self) -> list:
        """
        Get list of agent skills.

        Returns:
            List of skill definitions
        """
        return self.agent_card.get('skills', [])

    def call(
        self,
        message: str,
        skill: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call the agent with a message.

        Args:
            message: Message/query to send to the agent
            skill: Optional specific skill to invoke
            context: Optional context/parameters

        Returns:
            Agent response
        """
        # Build request payload
        payload = {
            "message": message
        }

        if skill:
            payload["skill"] = skill

        if context:
            payload.update(context)

        # Check if x402 payment is required
        if self.x402_config and self.x402_client:
            logger.info("Using x402 payment gateway")
            return self._call_with_x402_payment(payload)

        # Determine transport
        transport = self.agent_card.get('preferredTransport', 'HTTP+JSON')

        if transport == 'HTTP+JSON':
            return self._call_http_json(payload)
        else:
            raise ValueError(f"Unsupported transport: {transport}")

    def _call_with_x402_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call agent with x402 payment.

        Args:
            payload: Request payload

        Returns:
            Agent response
        """
        gateway_url = self.x402_config.get('gateway_url')
        price_usdc = float(self.x402_config.get('price_usdc', 0))

        if not gateway_url:
            raise Exception("x402 gateway URL not found in agent card")

        # Extract message from payload
        message = payload.get('message', '')

        return self.x402_client.process_payment(
            gateway_url=gateway_url,
            message=message,
            price_usdc=price_usdc
        )

    def _call_http_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call agent using HTTP+JSON transport.

        Args:
            payload: Request payload

        Returns:
            Response data
        """
        try:
            headers = {'Content-Type': 'application/json'}

            logger.debug(f"Calling {self.endpoint_url}")

            response = requests.post(
                self.endpoint_url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )

            response.raise_for_status()

            # Try to parse as JSON
            try:
                return response.json()
            except json.JSONDecodeError:
                # Return text response if not JSON
                logger.debug("Non-JSON response received, returning as text")
                return {"response": response.text}

        except requests.exceptions.RequestException as e:
            logger.error(f"Agent call failed: {e}")
            raise Exception(f"Failed to call agent: {e}")

    def health_check(self) -> bool:
        """
        Check if agent is responsive.

        Returns:
            True if agent is healthy
        """
        try:
            # Try a simple call
            self.call("health check")
            return True
        except Exception:
            return False
