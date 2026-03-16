"""
x402 payment-required types and 402 response parsing.
Mirrors agent0-ts src/core/x402-types.ts.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union


@dataclass
class ResourceInfo:
    """V2 ResourceInfo: url, optional description and mimeType (x402 spec §5.1)."""
    url: Optional[str] = None
    description: Optional[str] = None
    mimeType: Optional[str] = None


@dataclass
class X402Accept:
    """A single payment option from a 402 response (PAYMENT-REQUIRED header)."""
    price: str
    token: str
    network: Optional[str] = None
    scheme: Optional[str] = None
    description: Optional[str] = None
    maxAmountRequired: Optional[str] = None
    destination: Optional[str] = None
    asset: Optional[str] = None
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.extra.get(key, default)


@dataclass
class Parse402FromHeaderResult:
    """Result of parsing PAYMENT-REQUIRED header."""
    accepts: List[X402Accept]
    x402Version: Optional[int] = None
    resource: Optional[ResourceInfo] = None
    error: Optional[str] = None


@dataclass
class X402SettlementResponse:
    """Settlement response from PAYMENT-RESPONSE header or body after successful pay."""
    success: bool
    errorReason: Optional[str] = None
    transaction: Optional[str] = None
    network: Optional[str] = None
    payer: Optional[str] = None


@dataclass
class X402Payment:
    """Payment handle returned on 402; has pay(accept?) and optional pay_first()."""
    accepts: List[X402Accept]
    pay: Callable[..., Any]
    x402Version: Optional[int] = None
    error: Optional[str] = None
    resource: Optional[ResourceInfo] = None
    price: Optional[str] = None
    token: Optional[str] = None
    network: Optional[str] = None
    pay_first: Optional[Callable[[], Any]] = None


@dataclass
class X402RequiredResponse:
    """Response when server returns HTTP 402."""
    x402Required: bool = True
    x402Payment: Optional[X402Payment] = None


@dataclass
class RequestSnapshot:
    """Snapshot of the original request so pay() can retry with PAYMENT-SIGNATURE."""
    url: str
    method: str
    headers: Dict[str, str]
    body: Optional[Union[str, bytes]] = None
    x402Version: Optional[int] = None
    resource: Optional[ResourceInfo] = None
    error: Optional[str] = None


def isX402Required(result: Any) -> bool:
    """Type guard: result is 402 response. Returns False for None."""
    if result is None:
        return False
    if isinstance(result, dict):
        return result.get("x402Required") is True
    return getattr(result, "x402Required", None) is True


# EVM chain names/slugs: x402 spec V1 names (docs.x402.org network-and-token-support) + common slugs agents may send.
# x402 official V1 EVM names: base, base-sepolia, avalanche, avalanche-fuji, polygon, polygon-amoy, sei, sei-testnet, skale-base, skale-base-sepolia.
_EVM_NETWORK_SLUGS = frozenset([
    "base", "base-sepolia", "base-mainnet", "base-goerli",
    "ethereum", "mainnet", "ethereum-mainnet", "ethereum-sepolia", "sepolia", "goerli", "holesky",
    "polygon", "polygon-amoy", "matic",
    "arbitrum", "arbitrum-one", "arbitrum-sepolia",
    "optimism", "optimism-mainnet", "optimism-sepolia",
    "avalanche", "avalanche-fuji", "fuji", "bnb", "bnb-chain", "bsc", "bsc-testnet",
    "linea", "linea-sepolia", "zksync", "zksync-sepolia",
    "iotex", "iotex-testnet",
    "sei", "sei-testnet", "skale-base", "skale-base-sepolia",
])


def _is_evm_accept(a: Union[X402Accept, Dict[str, Any]]) -> bool:
    """True if the accept is EVM (eip155:* or numeric network or known EVM chain name)."""
    if isinstance(a, X402Accept):
        n = a.network
    elif isinstance(a, dict):
        n = a.get("network")
    else:
        n = getattr(a, "network", None)
    if n is None or n == "":
        return True
    s = str(n).strip()
    if re.match(r"^eip155:\d+$", s) or re.match(r"^\d+$", s):
        return True
    return s.lower() in _EVM_NETWORK_SLUGS


def _dict_to_accept(d: Dict[str, Any]) -> X402Accept:
    """Convert dict to X402Accept (normalize from server shape)."""
    pr = d.get("paymentRequirements")
    if pr is None or not isinstance(pr, dict):
        pr = d
    price = str(pr.get("price") or pr.get("amount") or pr.get("maxAmountRequired") or "0")
    token = str(pr.get("token") or pr.get("asset") or "")
    extra = {k: v for k, v in d.items() if k not in ("paymentRequirements",)}
    return X402Accept(
        price=price,
        token=token,
        network=pr.get("network"),
        scheme=pr.get("scheme"),
        description=pr.get("description"),
        maxAmountRequired=pr.get("maxAmountRequired"),
        destination=pr.get("destination") or pr.get("payTo"),
        asset=pr.get("asset"),
        extra=extra,
    )


def filter_evm_accepts(accepts: List[Union[X402Accept, Dict[str, Any]]]) -> List[X402Accept]:
    """Filter accepts to EVM-only (Solana and other non-EVM options removed)."""
    result: List[X402Accept] = []
    for a in accepts:
        acc = _dict_to_accept(a) if isinstance(a, dict) else a
        if _is_evm_accept(acc):
            result.append(acc)
    return result


def _normalize_accept_entry(entry: Dict[str, Any]) -> X402Accept:
    pr = entry.get("paymentRequirements")
    if pr is None or not isinstance(pr, dict):
        pr = entry
    price = str(pr.get("price") or pr.get("amount") or pr.get("maxAmountRequired") or "0")
    token = str(pr.get("token") or pr.get("asset") or "")
    # Match TS: extra = only the server's "extra" field (e.g. { name, version }), not the whole entry
    extra_raw = pr.get("extra") or entry.get("extra")
    extra = dict(extra_raw) if isinstance(extra_raw, dict) else {}
    # Preserve maxTimeoutSeconds so accept.get("maxTimeoutSeconds", 60) returns server value (TS has it from ...entry)
    for key in ("maxTimeoutSeconds",):
        if (pr.get(key) is not None) or (entry.get(key) is not None):
            extra[key] = pr.get(key) if pr.get(key) is not None else entry.get(key)
    return X402Accept(
        price=price,
        token=token,
        network=pr.get("network"),
        scheme=pr.get("scheme"),
        description=pr.get("description"),
        maxAmountRequired=pr.get("maxAmountRequired"),
        destination=pr.get("destination") or pr.get("payTo"),
        asset=pr.get("asset"),
        extra=extra,
    )


def _decode_base64(b64: str) -> str:
    return base64.b64decode(b64).decode("utf-8")


def _parse_resource_info(obj: Any) -> Optional[ResourceInfo]:
    if obj is None or not isinstance(obj, dict):
        return None
    url = obj.get("url")
    if not isinstance(url, str):
        return None
    return ResourceInfo(
        url=url,
        description=obj.get("description") if isinstance(obj.get("description"), str) else None,
        mimeType=obj.get("mimeType") if isinstance(obj.get("mimeType"), str) else None,
    )


def parse_402_from_header(header_value: Optional[str]) -> Parse402FromHeaderResult:
    """Parse PAYMENT-REQUIRED header (base64-encoded JSON with accepts array)."""
    if not header_value or not isinstance(header_value, str):
        return Parse402FromHeaderResult(accepts=[])
    try:
        json_str = _decode_base64(header_value.strip())
        json_obj = json.loads(json_str)
        if not isinstance(json_obj, dict):
            return Parse402FromHeaderResult(accepts=[])
        list_raw = json_obj.get("accepts")
        accepts = []
        if isinstance(list_raw, list):
            for e in list_raw:
                if isinstance(e, dict) and e is not None:
                    accepts.append(_normalize_accept_entry(e))
        x402_version = json_obj.get("x402Version")
        if not isinstance(x402_version, int):
            x402_version = None
        resource = _parse_resource_info(json_obj.get("resource"))
        error = json_obj.get("error")
        if not isinstance(error, str):
            error = None
        return Parse402FromHeaderResult(
            accepts=accepts,
            x402Version=x402_version,
            resource=resource,
            error=error,
        )
    except Exception:
        return Parse402FromHeaderResult(accepts=[])


def parse_402_from_body(body_text: Optional[str]) -> Parse402FromHeaderResult:
    """Parse 402 response body (JSON with accepts array)."""
    if not body_text or not isinstance(body_text, str):
        return Parse402FromHeaderResult(accepts=[])
    try:
        json_obj = json.loads(body_text.strip())
        if not isinstance(json_obj, dict):
            return Parse402FromHeaderResult(accepts=[])
        list_raw = json_obj.get("accepts")
        accepts = []
        if isinstance(list_raw, list):
            for e in list_raw:
                if isinstance(e, dict) and e is not None:
                    accepts.append(_normalize_accept_entry(e))
        x402_version = json_obj.get("x402Version")
        if not isinstance(x402_version, int):
            x402_version = None
        resource = _parse_resource_info(json_obj.get("resource"))
        error = json_obj.get("error")
        if not isinstance(error, str):
            error = None
        return Parse402FromHeaderResult(
            accepts=accepts,
            x402Version=x402_version,
            resource=resource,
            error=error,
        )
    except Exception:
        return Parse402FromHeaderResult(accepts=[])


def parse_402_from_www_authenticate(header_value: Optional[str]) -> Parse402FromHeaderResult:
    """Parse WWW-Authenticate header with x402 challenge."""
    if not header_value or not isinstance(header_value, str):
        return Parse402FromHeaderResult(accepts=[])
    m = re.search(r"\bx402\s+(.+)", header_value, re.I)
    if not m:
        return Parse402FromHeaderResult(accepts=[])
    rest = m.group(1)
    pairs: Dict[str, str] = {}
    for m2 in re.finditer(r'(\w+)\s*=\s*([^\s,]+|"[^"]*")', rest):
        key = m2.group(1).lower()
        val = m2.group(2)
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        pairs[key] = val
    address = pairs.get("address") or pairs.get("payto")
    amount = pairs.get("amount") or "0"
    chain_id = pairs.get("chainid") or pairs.get("chain_id") or ""
    token = pairs.get("token") or pairs.get("asset") or ""
    if not address or not token:
        return Parse402FromHeaderResult(accepts=[])
    price = amount
    if re.match(r"^\d*\.\d+$", amount):
        try:
            n = float(amount)
            price = str(round(n * 1e6))
        except ValueError:
            pass
    # x402 v1 uses chain names (e.g. "base-sepolia"); v2 uses CAIP-2 (eip155:chainId). Prefer explicit network.
    raw_network = pairs.get("network") or chain_id
    if not raw_network:
        network_str = None
    elif re.match(r"^eip155:\d+$", raw_network):
        network_str = raw_network
    elif re.match(r"^\d+$", raw_network.strip()):
        network_str = f"eip155:{raw_network}"
    else:
        network_str = raw_network  # chain name as-is for v1
    accept = X402Accept(
        price=price,
        token=token,
        destination=address,
        network=network_str,
        scheme="exact",
        extra={"payTo": address},
    )
    x402_version = 2 if (network_str and re.match(r"^eip155:\d+$", network_str)) else 1
    return Parse402FromHeaderResult(accepts=[accept], x402Version=x402_version)


def parse_402_accepts_from_header(header_value: Optional[str]) -> List[X402Accept]:
    """Parse PAYMENT-REQUIRED header; return accepts list only."""
    return parse_402_from_header(header_value).accepts


def parse_402_settlement_from_header(header_value: Optional[str]) -> Optional[X402SettlementResponse]:
    """Parse PAYMENT-RESPONSE header (base64-encoded JSON) after successful pay."""
    if not header_value or not isinstance(header_value, str):
        return None
    try:
        json_str = _decode_base64(header_value.strip())
        json_obj = json.loads(json_str)
        if not isinstance(json_obj, dict):
            return None
        return X402SettlementResponse(
            success=json_obj.get("success") is True,
            errorReason=json_obj.get("errorReason") if isinstance(json_obj.get("errorReason"), str) else None,
            transaction=json_obj.get("transaction") if isinstance(json_obj.get("transaction"), str) else None,
            network=json_obj.get("network") if isinstance(json_obj.get("network"), str) else None,
            payer=json_obj.get("payer") if isinstance(json_obj.get("payer"), str) else None,
        )
    except Exception:
        return None
