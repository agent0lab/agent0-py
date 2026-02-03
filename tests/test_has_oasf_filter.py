import pytest

from agent0_sdk.core.indexer import AgentIndexer
from agent0_sdk import SearchFilters


class _Web3Stub:
    def __init__(self, chain_id: int = 11155111):
        self.chain_id = chain_id


def test_has_oasf_pushdown_build_where_v2():
    """
    Unit test: ensure hasOASF is pushed down to subgraph registrationFile_ where clause.
    This does not require a live subgraph.
    """
    idx = AgentIndexer(web3_client=_Web3Stub(), subgraph_client=None)
    where = idx._build_where_v2(SearchFilters(hasOASF=True))

    assert "registrationFile_" in where
    assert where["registrationFile_"]["hasOASF"] is True

