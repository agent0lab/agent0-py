"""
Tests for x402 EVM payment building (agent0_sdk.core.x402_payment).
"""

import pytest
from unittest.mock import Mock, MagicMock

from agent0_sdk.core.x402_types import X402Accept, RequestSnapshot
from agent0_sdk.core.x402_payment import build_evm_payment, check_evm_balance


class TestCheckEvmBalance:
    def test_balance_sufficient(self):
        mock_client = Mock()
        mock_client.call_contract = Mock(return_value=1000000)
        accept = X402Accept(price="100", token="0xtoken", network="eip155:1")
        assert check_evm_balance(accept, mock_client) is True

    def test_balance_insufficient(self):
        mock_client = Mock()
        mock_client.call_contract = Mock(return_value=50)
        accept = X402Accept(price="100", token="0xtoken", network="eip155:1")
        assert check_evm_balance(accept, mock_client) is False

    def test_balance_retries_on_429_then_succeeds(self):
        mock_client = Mock()
        mock_client.call_contract = Mock(
            side_effect=[
                Exception("429 Client Error: Too Many Requests for url: https://mainnet.base.org/"),
                1_000_000,
            ]
        )
        accept = X402Accept(price="100", token="0xtoken", network="eip155:1")
        assert check_evm_balance(accept, mock_client) is True
        assert mock_client.call_contract.call_count == 2


class TestBuildEvmPayment:
    def test_returns_string_payload(self):
        mock_contract = Mock()
        mock_client = Mock()
        mock_client.get_contract = Mock(return_value=mock_contract)
        mock_client.call_contract = Mock(side_effect=["MyToken", "1", 2000000])
        mock_client.sign_typed_data = Mock(return_value=b"\\x00signature")
        mock_client.account = Mock(address="0xpayer")
        mock_client.chain_id = 8453
        mock_client.is_address = Mock(return_value=True)
        mock_client.to_checksum_address = lambda x: x
        accept = X402Accept(price="1000000", token="0xTokenAddr", network="eip155:8453", destination="0xdest")
        snapshot = RequestSnapshot(url="https://example.com", method="GET", headers={})
        payload = build_evm_payment(accept, mock_client, snapshot)
        assert isinstance(payload, str)
        assert len(payload) > 0

    def test_v2_maxtimeout_matches_ts_only_top_level_counts(self):
        """Nested extra maxTimeoutSeconds must not set accepted.maxTimeoutSeconds (TS parity)."""
        import base64
        import json

        mock_contract = Mock()
        mock_client = Mock()
        mock_client.get_contract = Mock(return_value=mock_contract)
        mock_client.call_contract = Mock(side_effect=["USDC", "2", 10_000_000_000])
        mock_client.sign_typed_data = Mock(return_value=b"\x00" * 65)
        mock_client.account = Mock(address="0x" + "11" * 20)
        mock_client.chain_id = 8453
        mock_client.is_address = Mock(return_value=True)
        mock_client.to_checksum_address = lambda x: x
        accept = X402Accept(
            price="10000",
            token="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            network="eip155:8453",
            destination="0x9f8bd9875b3E0b632a24A3A7C73f7787175e73A2",
            extra={"maxTimeoutSeconds": 300, "provider": "coinbase"},
        )
        snapshot = RequestSnapshot(url="https://example.com/mcp", method="POST", headers={})
        b64 = build_evm_payment(accept, mock_client, snapshot)
        obj = json.loads(base64.b64decode(b64).decode())
        assert obj.get("x402Version") == 2
        assert obj["accepted"]["maxTimeoutSeconds"] == 60
        assert obj["accepted"]["extra"]["maxTimeoutSeconds"] == 300

    def test_v2_maxtimeout_top_level_from_server(self):
        import base64
        import json

        mock_contract = Mock()
        mock_client = Mock()
        mock_client.get_contract = Mock(return_value=mock_contract)
        mock_client.call_contract = Mock(side_effect=["USDC", "2", 10_000_000_000])
        mock_client.sign_typed_data = Mock(return_value=b"\x00" * 65)
        mock_client.account = Mock(address="0x" + "11" * 20)
        mock_client.chain_id = 8453
        mock_client.is_address = Mock(return_value=True)
        mock_client.to_checksum_address = lambda x: x
        accept = X402Accept(
            price="10000",
            token="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            network="eip155:8453",
            destination="0x9f8bd9875b3E0b632a24A3A7C73f7787175e73A2",
            extra={"provider": "coinbase"},
            maxTimeoutSeconds=120,
        )
        snapshot = RequestSnapshot(url="https://example.com", method="POST", headers={})
        b64 = build_evm_payment(accept, mock_client, snapshot)
        obj = json.loads(base64.b64decode(b64).decode())
        assert obj["accepted"]["maxTimeoutSeconds"] == 120
