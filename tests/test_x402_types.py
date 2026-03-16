"""
Tests for x402 types and parsing (agent0_sdk.core.x402_types).
"""

import base64
import json
import pytest

from agent0_sdk.core.x402_types import (
    X402Accept,
    ResourceInfo,
    Parse402FromHeaderResult,
    X402SettlementResponse,
    parse_402_from_header,
    parse_402_from_body,
    parse_402_from_www_authenticate,
    filter_evm_accepts,
    parse_402_settlement_from_header,
    isX402Required,
)


class TestParse402FromHeader:
    def test_empty_or_none_returns_empty_accepts(self):
        assert parse_402_from_header(None).accepts == []
        assert parse_402_from_header("").accepts == []

    def test_valid_base64_json_with_accepts(self):
        payload = {
            "accepts": [
                {"paymentRequirements": {"price": "1000000", "token": "0xabc", "network": "eip155:8453"}},
            ],
            "x402Version": 2,
        }
        header = base64.b64encode(json.dumps(payload).encode()).decode()
        result = parse_402_from_header(header)
        assert len(result.accepts) == 1
        assert result.accepts[0].price == "1000000"
        assert result.accepts[0].token == "0xabc"
        assert result.accepts[0].network == "eip155:8453"
        assert result.x402Version == 2

    def test_invalid_base64_returns_empty(self):
        result = parse_402_from_header("not-valid-base64!!")
        assert result.accepts == []


class TestParse402FromBody:
    def test_empty_or_none_returns_empty_accepts(self):
        assert parse_402_from_body(None).accepts == []
        assert parse_402_from_body("").accepts == []

    def test_valid_json_body(self):
        body = json.dumps({
            "accepts": [{"price": "500", "token": "0xdef", "network": "eip155:1"}],
            "x402Version": 1,
        })
        result = parse_402_from_body(body)
        assert len(result.accepts) == 1
        assert result.accepts[0].price == "500"
        assert result.accepts[0].token == "0xdef"


class TestParse402FromWwwAuthenticate:
    def test_empty_returns_empty(self):
        assert parse_402_from_www_authenticate(None).accepts == []
        assert parse_402_from_www_authenticate("Bearer realm=x").accepts == []

    def test_x402_challenge_parsed(self):
        h = 'x402 address="0x123", amount="1", token="0xabc", chainid="8453"'
        result = parse_402_from_www_authenticate(h)
        assert len(result.accepts) == 1
        assert result.accepts[0].destination == "0x123"
        assert result.accepts[0].token == "0xabc"
        assert result.accepts[0].network == "eip155:8453"
        assert result.x402Version == 2

    def test_x402_v1_chain_name_preserved(self):
        """x402 v1 uses chain names in header; network must be preserved as-is, not turned into eip155:name."""
        h = 'x402 address="0x123", amount="0.01", token="0xabc", chainid="base-sepolia"'
        result = parse_402_from_www_authenticate(h)
        assert len(result.accepts) == 1
        assert result.accepts[0].network == "base-sepolia"
        assert result.x402Version == 1


class TestFilterEvmAccepts:
    def test_evm_accepts_kept(self):
        acc = X402Accept(price="1", token="0x", network="eip155:1")
        assert len(filter_evm_accepts([acc])) == 1
        acc2 = X402Accept(price="1", token="0x", network=None)
        assert len(filter_evm_accepts([acc2])) == 1

    def test_solana_style_removed(self):
        acc = X402Accept(price="1", token="So11111", network="solana:mainnet")
        assert len(filter_evm_accepts([acc])) == 0

    def test_v1_chain_name_kept(self):
        """x402 v1 uses chain names (e.g. base-sepolia), not chainId; filter must keep them."""
        acc = X402Accept(price="1", token="0xabc", network="base-sepolia")
        assert len(filter_evm_accepts([acc])) == 1
        acc2 = X402Accept(price="1", token="0xdef", network="ethereum-mainnet")
        assert len(filter_evm_accepts([acc2])) == 1


class TestParse402SettlementFromHeader:
    def test_empty_returns_none(self):
        assert parse_402_settlement_from_header(None) is None
        assert parse_402_settlement_from_header("") is None

    def test_valid_settlement(self):
        payload = {"success": True, "transaction": "0xabc"}
        header = base64.b64encode(json.dumps(payload).encode()).decode()
        result = parse_402_settlement_from_header(header)
        assert result is not None
        assert result.success is True
        assert result.transaction == "0xabc"


class TestIsX402Required:
    def test_none_false(self):
        assert isX402Required(None) is False

    def test_dict_with_flag(self):
        assert isX402Required({"x402Required": True}) is True
        assert isX402Required({"x402Required": False}) is False

    def test_object_with_attr(self):
        class R:
            x402Required = True
        assert isX402Required(R()) is True
