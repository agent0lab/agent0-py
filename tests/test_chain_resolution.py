"""
Unit tests for chain resolution defaults.
"""

from __future__ import annotations

from agent0_sdk.core.indexer import AgentIndexer
from agent0_sdk.core.models import SearchFilters


class _DummyWeb3:
    def __init__(self, chain_id: int):
        self.chain_id = chain_id


def test_resolve_chains_defaults_to_1_and_sdk_chain_without_keyword():
    idx = AgentIndexer(web3_client=_DummyWeb3(chain_id=11155111), subgraph_client=None)
    out = idx._resolve_chains(SearchFilters(), keyword_present=False)
    assert out == [1, 11155111]


def test_resolve_chains_defaults_to_1_and_sdk_chain_with_keyword():
    idx = AgentIndexer(web3_client=_DummyWeb3(chain_id=11155111), subgraph_client=None)
    out = idx._resolve_chains(SearchFilters(keyword="agent"), keyword_present=True)
    assert out == [1, 11155111]


def test_resolve_chains_dedupes_when_sdk_chain_is_1():
    idx = AgentIndexer(web3_client=_DummyWeb3(chain_id=1), subgraph_client=None)
    out = idx._resolve_chains(SearchFilters(), keyword_present=False)
    assert out == [1]


def test_resolve_chains_uses_filter_as_is_when_provided():
    idx = AgentIndexer(web3_client=_DummyWeb3(chain_id=11155111), subgraph_client=None)
    out = idx._resolve_chains(SearchFilters(chains=[84532, 1, 84532]), keyword_present=True)
    assert out == [84532, 1]

