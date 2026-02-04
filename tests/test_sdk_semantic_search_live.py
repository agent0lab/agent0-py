"""
Live (gated) SDK tests for semantic keyword search.

These tests are skipped unless RUN_LIVE_TESTS=1 (or SDK_LIVE=1) is set, to avoid
network flakiness and rate limits.
"""

from __future__ import annotations

import os
import re
import time

import pytest

from agent0_sdk import SDK
from tests.config import CHAIN_ID, RPC_URL, SUBGRAPH_URL


RUN_LIVE = os.getenv("RUN_LIVE_TESTS", "0") != "0" or os.getenv("SDK_LIVE", "0") != "0"


def _agent_id_of(item) -> str:
    # AgentSummary dataclass vs dict fallback
    if hasattr(item, "agentId"):
        return str(getattr(item, "agentId"))
    if isinstance(item, dict):
        return str(item.get("agentId") or item.get("id") or "")
    return ""


@pytest.mark.integration
def test_search_agents_keyword_live_smoke():
    if not RUN_LIVE:
        pytest.skip("Set RUN_LIVE_TESTS=1 (or SDK_LIVE=1) to enable live semantic tests")
    if not RPC_URL or not RPC_URL.strip():
        pytest.skip("RPC_URL not set")
    if not SUBGRAPH_URL or not SUBGRAPH_URL.strip():
        pytest.skip("SUBGRAPH_URL not set")

    sdk = SDK(chainId=CHAIN_ID, rpcUrl=RPC_URL)

    result = sdk.searchAgents(
        filters={"keyword": "agent"},
        options={"semanticTopK": 10},
    )
    assert isinstance(result, list)

    for item in result:
        agent_id = _agent_id_of(item)
        assert re.match(r"^\d+:\d+$", agent_id)


@pytest.mark.integration
def test_search_agents_keyword_returns_unique_ids():
    """Pagination removed: ensure keyword search returns a list with unique agentIds."""
    if not RUN_LIVE:
        pytest.skip("Set RUN_LIVE_TESTS=1 (or SDK_LIVE=1) to enable live semantic tests")
    if not RPC_URL or not RPC_URL.strip():
        pytest.skip("RPC_URL not set")
    if not SUBGRAPH_URL or not SUBGRAPH_URL.strip():
        pytest.skip("SUBGRAPH_URL not set")

    sdk = SDK(chainId=CHAIN_ID, rpcUrl=RPC_URL)
    results = sdk.searchAgents(filters={"keyword": "crypto"}, options={"semanticTopK": 50})
    ids = [_agent_id_of(i) for i in results]
    ids = [i for i in ids if i]
    assert len(set(ids)) == len(ids)
