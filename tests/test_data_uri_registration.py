import pytest
from unittest.mock import Mock, patch

from agent0_sdk.core.data_uri import (
    is_erc8004_json_data_uri,
    decode_erc8004_json_data_uri,
    encode_erc8004_json_data_uri,
)
from agent0_sdk.core.sdk import SDK


def test_data_uri_codec_roundtrip_and_tolerance():
    obj = {"name": "Agent", "description": "Desc", "services": []}
    uri = encode_erc8004_json_data_uri(obj)
    tolerant = uri.replace(
        "data:application/json;base64,", "data:application/json;charset=utf-8;base64,"
    )
    assert is_erc8004_json_data_uri(tolerant) is True
    assert decode_erc8004_json_data_uri(tolerant) == obj


def test_data_uri_codec_enforces_max_bytes():
    obj = {"data": "x" * 1024}
    uri = encode_erc8004_json_data_uri(obj)
    with pytest.raises(ValueError):
        decode_erc8004_json_data_uri(uri, max_bytes=10)


def test_sdk_load_agent_decodes_data_uri_tokenuri():
    # Build a data URI that contains an ERC-8004-like registration file
    raw = {
        "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        "name": "Agent",
        "description": "Desc",
        "services": [],
        "supportedTrust": ["reputation"],
        "active": True,
        "x402Support": False,
    }
    data_uri = encode_erc8004_json_data_uri(raw)

    with patch("agent0_sdk.core.sdk.Web3Client") as mock_web3:
        web3_instance = mock_web3.return_value
        web3_instance.chain_id = 11155111
        web3_instance.get_contract.return_value = Mock()

        def call_contract_side_effect(contract, fn_name, *args):
            if fn_name == "tokenURI":
                return data_uri
            if fn_name == "ownerOf":
                return "0x1234567890abcdef1234567890abcdef12345678"
            if fn_name == "getAgentWallet":
                return "0x0000000000000000000000000000000000000000"
            raise AssertionError(f"Unexpected contract call: {fn_name} args={args}")

        web3_instance.call_contract.side_effect = call_contract_side_effect

        sdk = SDK(chainId=11155111, signer="0x1234567890abcdef", rpcUrl="https://example.com/rpc")
        agent = sdk.loadAgent("11155111:1")
        assert agent.name == "Agent"
        assert agent.description == "Desc"

