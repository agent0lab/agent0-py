"""
Tests for X402Client - x402 micropayment protocol client.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from web3 import Web3
import json
import time

from agent0_sdk.core.x402_client import X402Client, USDC_SEPOLIA, USDC_BASE, USDC_BASE_SEPOLIA


class TestX402ClientInitialization:
    """Test X402Client initialization."""

    def test_init_ethereum_sepolia(self):
        """Test initialization with Ethereum Sepolia chain."""
        client = X402Client(
            rpc_url="https://ethereum-sepolia-rpc.publicnode.com",
            private_key="0x" + "1" * 64,
            chain_id=11155111
        )

        assert client.chain_id == 11155111
        assert client.usdc_address == Web3.to_checksum_address(USDC_SEPOLIA)
        assert client.address is not None

    def test_init_base_mainnet(self):
        """Test initialization with Base mainnet chain."""
        client = X402Client(
            rpc_url="https://mainnet.base.org",
            private_key="0x" + "1" * 64,
            chain_id=8453
        )

        assert client.chain_id == 8453
        assert client.usdc_address == Web3.to_checksum_address(USDC_BASE)

    def test_init_base_sepolia(self):
        """Test initialization with Base Sepolia chain."""
        client = X402Client(
            rpc_url="https://sepolia.base.org",
            private_key="0x" + "1" * 64,
            chain_id=84532
        )

        assert client.chain_id == 84532
        assert client.usdc_address == Web3.to_checksum_address(USDC_BASE_SEPOLIA)

    def test_init_unsupported_chain(self):
        """Test initialization with unsupported chain raises error."""
        with pytest.raises(ValueError, match="Unsupported chain ID"):
            X402Client(
                rpc_url="https://mainnet.eth.org",
                private_key="0x" + "1" * 64,
                chain_id=1  # Ethereum mainnet not supported
            )


class TestX402PaymentSigning:
    """Test x402 payment signature generation."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return X402Client(
            rpc_url="https://mainnet.base.org",
            private_key="0x" + "1" * 64,
            chain_id=8453
        )

    def test_sign_payment_option_structure(self, client):
        """Test payment option signing produces correct structure."""
        payment_option = {
            "scheme": "erc20-authorization",
            "network": "eip155:8453",
            "asset": USDC_BASE,
            "maxAmountRequired": 50000,  # $0.05 in USDC (6 decimals)
            "maxTimeoutSeconds": 600,
            "payTo": "0x742D35cc6634c0532925a3b844bc9E7595F0BEb6",
            "extra": {
                "name": "USD Coin",
                "version": "2"
            }
        }

        message = "Test message"
        signed_payment = client._sign_payment_option(payment_option, message)

        # Verify structure
        assert "x402Version" in signed_payment
        assert signed_payment["x402Version"] == 1
        assert "scheme" in signed_payment
        assert signed_payment["scheme"] == "erc20-authorization"
        assert "network" in signed_payment
        assert "payload" in signed_payment

        # Verify payload structure
        payload = signed_payment["payload"]
        assert "signature" in payload
        assert "authorization" in payload

        # Verify authorization structure
        auth = payload["authorization"]
        assert "from" in auth
        assert "to" in auth
        assert "value" in auth
        assert "validAfter" in auth
        assert "validBefore" in auth
        assert "nonce" in auth

        # Verify signature has 0x prefix
        assert payload["signature"].startswith("0x")
        assert len(payload["signature"]) == 132  # 0x + 130 hex chars

    def test_sign_payment_nonce_uniqueness(self, client):
        """Test that each payment generates unique nonce."""
        payment_option = {
            "scheme": "erc20-authorization",
            "network": "eip155:8453",
            "asset": USDC_BASE,
            "maxAmountRequired": 50000,
            "maxTimeoutSeconds": 600,
            "payTo": "0x742D35cc6634c0532925a3b844bc9E7595F0BEb6",
            "extra": {"name": "USD Coin", "version": "2"}
        }

        signed1 = client._sign_payment_option(payment_option, "msg1")
        signed2 = client._sign_payment_option(payment_option, "msg2")

        nonce1 = signed1["payload"]["authorization"]["nonce"]
        nonce2 = signed2["payload"]["authorization"]["nonce"]

        assert nonce1 != nonce2
        assert nonce1.startswith("0x")
        assert len(nonce1) == 66  # 0x + 64 hex chars (32 bytes)

    def test_sign_payment_valid_timeframe(self, client):
        """Test that validAfter and validBefore are set correctly."""
        payment_option = {
            "scheme": "erc20-authorization",
            "network": "eip155:8453",
            "asset": USDC_BASE,
            "maxAmountRequired": 50000,
            "maxTimeoutSeconds": 300,
            "payTo": "0x742D35cc6634c0532925a3b844bc9E7595F0BEb6",
            "extra": {"name": "USD Coin", "version": "2"}
        }

        current_time = int(time.time())
        signed = client._sign_payment_option(payment_option, "test")

        auth = signed["payload"]["authorization"]
        valid_after = int(auth["validAfter"])
        valid_before = int(auth["validBefore"])

        assert valid_after == 0
        assert valid_before > current_time
        assert valid_before <= current_time + 300


class TestX402ProcessPayment:
    """Test complete x402 payment processing."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return X402Client(
            rpc_url="https://mainnet.base.org",
            private_key="0x" + "1" * 64,
            chain_id=8453
        )

    @patch('requests.post')
    def test_process_payment_direct_success(self, mock_post, client):
        """Test direct success without 402 challenge."""
        # Mock sufficient balance
        client.get_balance = Mock(return_value=1.0)

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "success": True,
            "task": {
                "status": {
                    "code": "success",
                    "message": {"parts": [{"kind": "text", "text": "Response"}]}
                }
            }
        }

        mock_post.return_value = success_response

        result = client.process_payment(
            gateway_url="http://localhost:3000/process",
            message="Test",
            price_usdc=0.05
        )

        assert result["success"] is True
        assert mock_post.call_count == 1

    @patch('requests.post')
    def test_process_payment_network_error(self, mock_post, client):
        """Test handling of network errors."""
        import requests
        # Mock sufficient balance
        client.get_balance = Mock(return_value=1.0)

        mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

        with pytest.raises(Exception, match="x402 gateway request failed"):
            client.process_payment(
                gateway_url="http://localhost:3000/process",
                message="Test",
                price_usdc=0.05
            )


# Message formatting is internal implementation detail
# Tests removed as _build_a2a_message is not part of public API


class TestX402ChecksumAddresses:
    """Test proper address checksumming."""

    def test_usdc_addresses_checksummed(self):
        """Test that all USDC addresses are properly checksummed."""
        # These should not raise errors
        Web3.to_checksum_address(USDC_SEPOLIA)
        Web3.to_checksum_address(USDC_BASE)
        Web3.to_checksum_address(USDC_BASE_SEPOLIA)

        # Verify they are already checksummed
        assert USDC_SEPOLIA == Web3.to_checksum_address(USDC_SEPOLIA)
        assert USDC_BASE == Web3.to_checksum_address(USDC_BASE)
        assert USDC_BASE_SEPOLIA == Web3.to_checksum_address(USDC_BASE_SEPOLIA)


class TestX402Integration:
    """Integration tests with mocked Web3."""

    @pytest.fixture
    def client_with_balance(self):
        """Create client with mocked USDC balance."""
        with patch('agent0_sdk.core.x402_client.Web3') as mock_web3_class:
            mock_w3 = Mock()
            mock_web3_class.return_value = mock_w3

            # Mock contract
            mock_contract = Mock()
            mock_contract.functions.balanceOf.return_value.call.return_value = 1000000  # $1 USDC (6 decimals)
            mock_contract.functions.decimals.return_value.call.return_value = 6  # USDC has 6 decimals
            mock_w3.eth.contract.return_value = mock_contract

            client = X402Client(
                rpc_url="https://mainnet.base.org",
                private_key="0x" + "1" * 64,
                chain_id=8453
            )

            yield client

    def test_get_balance(self, client_with_balance):
        """Test USDC balance checking."""
        balance = client_with_balance.get_balance()
        assert balance == 1.0  # $1 USDC
