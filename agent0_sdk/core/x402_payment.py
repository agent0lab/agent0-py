"""
Build EVM x402 payment payload (EIP-3009 TransferWithAuthorization style).
Mirrors agent0-ts src/core/x402-payment.ts.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import time
from typing import Any, Dict, List, Optional, Union

from .x402_types import (
    X402Accept,
    ResourceInfo,
    RequestSnapshot,
)

# Minimal ERC-20 ABIs for x402
NAME_ABI: List[Dict[str, Any]] = [
    {"inputs": [], "name": "name", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
]
VERSION_ABI: List[Dict[str, Any]] = [
    {"inputs": [], "name": "version", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
]
BALANCE_OF_ABI: List[Dict[str, Any]] = [
    {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]

TRANSFER_WITH_AUTHORIZATION_TYPES = [
    {"name": "from", "type": "address"},
    {"name": "to", "type": "address"},
    {"name": "value", "type": "uint256"},
    {"name": "validAfter", "type": "uint256"},
    {"name": "validBefore", "type": "uint256"},
    {"name": "nonce", "type": "bytes32"},
]

V1_NETWORK_NAMES: Dict[str, str] = {
    "eip155:1": "ethereum-mainnet",
    "eip155:11155111": "ethereum-sepolia",
    "eip155:8453": "base",
    "eip155:84532": "base-sepolia",
    "eip155:43114": "avalanche",
    "eip155:43113": "avalanche-fuji",
    "eip155:4689": "iotex",
    "eip155:4690": "iotex-testnet",
}


def _random_bytes32_hex() -> str:
    b = secrets.token_bytes(32)
    return "0x" + b.hex()


def _token_address(accept: X402Accept, web3_client: Any) -> str:
    raw = accept.token or accept.asset or ""
    if not raw or not web3_client.is_address(raw):
        raise ValueError("x402: accept has no valid token/asset address")
    return web3_client.to_checksum_address(raw)


def _destination_address(accept: X402Accept, web3_client: Any) -> str:
    raw = accept.destination or accept.get("payTo") or ""
    if not raw or not web3_client.is_address(raw):
        raise ValueError("x402: accept has no valid destination/payTo address")
    return web3_client.to_checksum_address(raw)


def _value_amount(accept: X402Accept) -> str:
    v = accept.price or accept.maxAmountRequired or "0"
    return str(v)


def _to_v1_network_name(network_or_chain_id: Union[str, int]) -> str:
    s = str(network_or_chain_id)
    if s in V1_NETWORK_NAMES:
        return V1_NETWORK_NAMES[s]
    caip = s if s.startswith("eip155:") else f"eip155:{s}"
    if caip in V1_NETWORK_NAMES:
        return V1_NETWORK_NAMES[caip]
    return s


def _get_token_domain(
    token_address: str,
    chain_id: int,
    web3_client: Any,
) -> tuple:
    name, version = "Token", "2"
    contract = web3_client.get_contract(token_address, NAME_ABI + VERSION_ABI)
    try:
        name = web3_client.call_contract(contract, "name")
        if not name:
            name = "Token"
    except Exception:
        pass
    try:
        version = web3_client.call_contract(contract, "version")
        if not version:
            version = "2"
    except Exception:
        pass
    return name or "Token", version or "2"


def check_evm_balance(accept: X402Accept, web3_client: Any) -> bool:
    """Return True if signer has sufficient token balance for the accept."""
    try:
        token = _token_address(accept, web3_client)
        if not web3_client.account:
            return False
        signer = web3_client.account.address
        contract = web3_client.get_contract(token, BALANCE_OF_ABI)
        balance = web3_client.call_contract(contract, "balanceOf", signer)
        price = int(_value_amount(accept))
        if hasattr(balance, "real"):
            balance = int(balance)
        return balance >= price
    except Exception:
        return False


def build_evm_payment(
    accept: X402Accept,
    web3_client: Any,
    snapshot: Optional[RequestSnapshot] = None,
) -> str:
    """Build base64-encoded PAYMENT-SIGNATURE payload for EVM (EIP-3009)."""
    token = _token_address(accept, web3_client)
    to_addr = _destination_address(accept, web3_client)
    value = _value_amount(accept)

    chain_id = web3_client.chain_id
    domain_name, domain_version = _get_token_domain(token, chain_id, web3_client)

    if not web3_client.account:
        raise ValueError("x402: Web3Client must have an account to sign payment")
    from_addr = web3_client.account.address

    valid_after = "0"
    valid_before = str(int(time.time()) + 3600)
    nonce = _random_bytes32_hex()

    domain = {
        "name": domain_name,
        "version": domain_version,
        "chainId": chain_id,
        "verifyingContract": token,
    }
    types = {"TransferWithAuthorization": TRANSFER_WITH_AUTHORIZATION_TYPES}
    message = {
        "from": from_addr,
        "to": to_addr,
        "value": int(value),
        "validAfter": int(valid_after),
        "validBefore": int(valid_before),
        "nonce": nonce,
    }

    full_message = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            **types,
        },
        "domain": domain,
        "primaryType": "TransferWithAuthorization",
        "message": message,
    }
    signature_bytes = web3_client.sign_typed_data(full_message, web3_client.account)
    signature = "0x" + signature_bytes.hex()

    network_str = accept.network or str(chain_id)
    server_version = snapshot.x402Version if snapshot else None
    is_v2 = server_version == 2 or (
        server_version is None and bool(re.match(r"^eip155:\d+$", str(network_str)))
    )
    scheme = accept.scheme or "exact"
    pay_to = to_addr

    # Compact JSON to match TS JSON.stringify (no spaces); some servers are sensitive to payload shape.
    _compact = {"separators": (",", ":")}

    if is_v2:
        accepted = {
            "scheme": scheme,
            "network": network_str,
            "amount": value,
            "asset": token,
            "payTo": pay_to,
            "maxTimeoutSeconds": accept.get("maxTimeoutSeconds", 60),
        }
        if accept.extra:
            # Send only server-style extra (e.g. name, version); omit maxTimeoutSeconds so it's only at top level (match TS)
            accepted["extra"] = {k: v for k, v in accept.extra.items() if k != "maxTimeoutSeconds"}
        # Key order matches TS: x402Version, resource (if present), accepted, payload, extensions
        payload_v2 = {"x402Version": 2}
        if snapshot and snapshot.resource:
            payload_v2["resource"] = {
                "url": snapshot.resource.url,
                "description": snapshot.resource.description,
                "mimeType": snapshot.resource.mimeType,
            }
        payload_v2["accepted"] = accepted
        payload_v2["payload"] = {
            "signature": signature,
            "authorization": {
                "from": from_addr,
                "to": to_addr,
                "value": value,
                "validAfter": valid_after,
                "validBefore": valid_before,
                "nonce": nonce,
            },
        }
        payload_v2["extensions"] = {}
        json_str = json.dumps(payload_v2, **_compact)
    else:
        payload = {
            "x402Version": 1,
            "scheme": scheme,
            "network": _to_v1_network_name(network_str),
            "payload": {
                "signature": signature,
                "authorization": {
                    "from": from_addr,
                    "to": to_addr,
                    "value": value,
                    "validAfter": valid_after,
                    "validBefore": valid_before,
                    "nonce": nonce,
                },
            },
        }
        json_str = json.dumps(payload, **_compact)

    return base64.b64encode(json_str.encode("utf-8")).decode("ascii")
