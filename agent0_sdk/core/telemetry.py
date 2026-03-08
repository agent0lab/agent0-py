"""
Telemetry client for SDK events (Telemetry-Events-Specs-v2).
Fire-and-forget; never blocks or raises.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

import requests

DEFAULT_TELEMETRY_ENDPOINT = (
    "https://pepzouxscqxcejwjcbro.supabase.co/functions/v1/ingest-telemetry"
)

TelemetryErrorType = str  # one of the literals below


def categorize_error(error: Optional[BaseException]) -> str:
    """Map an exception to a telemetry error type string."""
    if error is None:
        return "UNKNOWN"
    msg = str(error)
    code = ""
    if isinstance(error, BaseException) and hasattr(error, "code"):
        code = str(getattr(error, "code", ""))
    if code == "NETWORK_ERROR" or (
        "fetch" in msg.lower()
        or "network" in msg.lower()
        or "econnrefused" in msg.lower()
        or "enotfound" in msg.lower()
    ):
        return "NETWORK_ERROR"
    if "CALL_EXCEPTION" in code or "contract" in code or "revert" in code or "execution reverted" in code:
        return "CONTRACT_ERROR"
    if "revert" in msg.lower() or "contract" in msg.lower():
        return "CONTRACT_ERROR"
    if "validation" in msg.lower() or "invalid" in msg.lower() or "bad request" in msg.lower() or "VALIDATION" in code:
        return "VALIDATION_ERROR"
    if "timeout" in msg.lower() or "timed out" in msg.lower() or "ETIMEDOUT" in msg.lower():
        return "TIMEOUT"
    if "not found" in msg.lower() or "404" in msg or "NOT_FOUND" in msg:
        return "NOT_FOUND"
    if "unauthorized" in msg.lower() or "403" in msg or "permission" in msg.lower() or "UNAUTHORIZED" in msg:
        return "UNAUTHORIZED"
    if "rate limit" in msg.lower() or "429" in msg or "RATE_LIMITED" in msg:
        return "RATE_LIMITED"
    if "ipfs" in msg.lower() or "IPFS_ERROR" in msg or "pinata" in msg.lower() or "pin.fs" in msg.lower():
        return "IPFS_ERROR"
    if "subgraph" in msg.lower() or "graphql" in msg.lower() or "SUBGRAPH_ERROR" in msg:
        return "SUBGRAPH_ERROR"
    return "UNKNOWN"


def _send_request(endpoint: str, api_key: str, events: List[Dict[str, Any]]) -> None:
    """Run in background; never raise."""
    try:
        body = json.dumps({"events": events})
        requests.post(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            timeout=10,
        )
    except Exception:
        pass  # Silently ignore telemetry failures


class TelemetryClient:
    """Fire-and-forget telemetry client. Never blocks or raises."""

    def __init__(self, api_key: str, endpoint: Optional[str] = None) -> None:
        self._api_key = api_key
        self._endpoint = endpoint or DEFAULT_TELEMETRY_ENDPOINT

    def emit(self, events: List[Dict[str, Any]]) -> None:
        """Emit events (fire-and-forget). Never raises; failures are ignored."""
        if not events:
            return
        thread = threading.Thread(
            target=_send_request,
            args=(self._endpoint, self._api_key, events),
            daemon=True,
        )
        thread.start()
