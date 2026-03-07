"""
ERC-8004 on-chain registration file support.

The spec allows `agentURI` / ERC-721 `tokenURI` to be a base64-encoded JSON data URI:
  data:application/json;base64,eyJ0eXBlIjoi...

We also accept optional parameters such as `;charset=utf-8` as long as `;base64,` is present.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict, Optional, Tuple


DEFAULT_MAX_BYTES = 256 * 1024  # 256 KiB


def _parse_data_uri(uri: str) -> Optional[Tuple[Optional[str], str, bool]]:
    """
    Returns (media_type, data_payload, is_base64) or None if not a data URI.
    """
    if not isinstance(uri, str):
        return None
    if not uri.startswith("data:"):
        return None

    comma = uri.find(",")
    if comma < 0:
        return None

    meta = uri[len("data:") : comma]  # <mediatype>[;<param>]*
    data = uri[comma + 1 :]

    parts = [p for p in meta.split(";") if p]
    media_type: Optional[str] = None
    params = parts

    if parts and "/" in parts[0]:
        media_type = parts[0]
        params = parts[1:]

    is_base64 = any(p.lower() == "base64" for p in params)
    return (media_type, data, is_base64)


def is_erc8004_json_data_uri(uri: str) -> bool:
    parsed = _parse_data_uri(uri)
    if not parsed:
        return False
    media_type, data, is_base64 = parsed
    if not is_base64:
        return False
    if not data:
        return False
    if not media_type:
        return False
    return media_type.lower() == "application/json"


def _normalize_base64(payload: str) -> str:
    # Remove ASCII whitespace defensively.
    s = re.sub(r"[ \t\r\n]+", "", payload)
    # Accept base64url by normalizing.
    s = s.replace("-", "+").replace("_", "/")

    # Add missing padding.
    mod = len(s) % 4
    if mod == 2:
        s += "=="
    elif mod == 3:
        s += "="
    elif mod == 1:
        raise ValueError("Invalid base64 length")

    if not re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", s):
        raise ValueError("Invalid base64 characters")
    return s


def decode_erc8004_json_data_uri(uri: str, max_bytes: int = DEFAULT_MAX_BYTES) -> Dict[str, Any]:
    parsed = _parse_data_uri(uri)
    if not parsed:
        raise ValueError("Not a data URI")

    media_type, payload, is_base64 = parsed
    if not media_type or media_type.lower() != "application/json":
        raise ValueError(f"Unsupported data URI media type: {media_type or '(missing)'}")
    if not is_base64:
        raise ValueError("Unsupported data URI encoding: expected ;base64")

    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError(f"Invalid max_bytes: {max_bytes}")

    approx_decoded = (len(payload) * 3) // 4 + 4
    if approx_decoded > max_bytes:
        raise ValueError(f"Data URI payload too large (approx {approx_decoded} bytes > max {max_bytes})")

    try:
        b64 = _normalize_base64(payload)
        decoded = base64.b64decode(b64, validate=True)
    except Exception as e:
        raise ValueError(f"Invalid base64 payload in data URI: {e}")

    if len(decoded) > max_bytes:
        raise ValueError(f"Data URI payload too large ({len(decoded)} bytes > max {max_bytes})")

    try:
        obj: Any = json.loads(decoded.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid JSON in data URI: {e}")

    if not isinstance(obj, dict):
        raise ValueError("Invalid registration file format: expected a JSON object")
    return obj


def encode_erc8004_json_data_uri(obj: Dict[str, Any]) -> str:
    if not isinstance(obj, dict):
        raise ValueError("encode_erc8004_json_data_uri expects a dict")
    s = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    b = s.encode("utf-8")
    payload = base64.b64encode(b).decode("ascii")
    return f"data:application/json;base64,{payload}"

