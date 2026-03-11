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
