from __future__ import annotations

from dataclasses import dataclass

from agent0_sdk.core.indexer import AgentIndexer
from agent0_sdk.core.models import SearchOptions
from agent0_sdk import SearchFilters


class _Web3Stub:
    def __init__(self, chain_id: int = 11155111):
        self.chain_id = chain_id


class _SubgraphStub:
    def __init__(self, chain_id: int):
        self.chain_id = chain_id
        self.calls: list[tuple[int, int]] = []  # (first, skip)

    def get_agents_v2(self, *, where, first: int, skip: int, order_by: str, order_direction: str):
        self.calls.append((first, skip))
        # two pages: 1000 + 10, then stop
        if skip == 0:
            return [self._agent_dict(i) for i in range(1000)]
        if skip == 1000:
            return [self._agent_dict(i) for i in range(1000, 1010)]
        return []

    def _agent_dict(self, i: int) -> dict:
        return {
            "id": f"{self.chain_id}:{i}",
            "chainId": self.chain_id,
            "owner": "0x0000000000000000000000000000000000000000",
            "operators": [],
            "agentWallet": None,
            "totalFeedback": 0,
            "createdAt": 0,
            "updatedAt": 10_000 - i,
            "lastActivity": 0,
            "agentURI": None,
            "agentURIType": None,
            "registrationFile": {
                "name": f"agent-{i}",
                "description": "",
                "supportedTrusts": [],
                "a2aSkills": [],
                "mcpTools": [],
                "mcpPrompts": [],
                "mcpResources": [],
                "oasfSkills": [],
                "oasfDomains": [],
                "active": True,
                "x402Support": False,
            },
        }


def test_search_agents_fetches_all_pages(monkeypatch):
    """
    Unit test: the unified no-keyword search path loops `skip += batch` until exhaustion.
    """
    stub = _SubgraphStub(chain_id=11155111)
    idx = AgentIndexer(web3_client=_Web3Stub(chain_id=11155111), subgraph_client=stub)

    # Avoid metadata/feedback prefilters for this test.
    monkeypatch.setattr(idx, "_prefilter_by_metadata", lambda filters, chains: None)
    monkeypatch.setattr(idx, "_prefilter_by_feedback", lambda filters, chains, candidate: (None, {}))
    monkeypatch.setattr(idx, "_get_subgraph_client_for_chain", lambda chain_id: stub)

    results = idx.search_agents(SearchFilters(), SearchOptions(sort=["updatedAt:desc"]))

    assert len(results) == 1010
    assert stub.calls == [(1000, 0), (1000, 1000)]

