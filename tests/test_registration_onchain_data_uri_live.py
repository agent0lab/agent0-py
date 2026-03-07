import os
import pytest

from agent0_sdk import SDK


RUN_LIVE_TESTS = os.getenv("RUN_LIVE_TESTS", "0") != "0"


@pytest.mark.integration
def test_registration_onchain_data_uri_live():
    """
    Live integration test for fully on-chain registration (ERC-8004 data URI).
    Intended for Base Sepolia (84532) when run with:
      RUN_LIVE_TESTS=1 CHAIN_ID=84532 RPC_URL=... AGENT_PRIVATE_KEY=...
    """
    if not RUN_LIVE_TESTS:
        pytest.skip("Set RUN_LIVE_TESTS=1 to enable live integration tests")

    chain_id = int(os.getenv("CHAIN_ID", "0") or "0")
    rpc_url = os.getenv("RPC_URL", "")
    pk = os.getenv("AGENT_PRIVATE_KEY", "")
    if chain_id == 0:
        pytest.skip("CHAIN_ID not set")
    if not rpc_url.strip():
        pytest.skip("RPC_URL not set")
    if not pk.strip():
        pytest.skip("AGENT_PRIVATE_KEY not set")

    sdk = SDK(chainId=chain_id, rpcUrl=rpc_url, signer=pk)
    suffix = os.urandom(4).hex()
    agent = sdk.createAgent(
        name=f"OnChain Agent {suffix}",
        description=f"OnChain registration {suffix}",
    )
    agent.setActive(True)
    agent.setTrust(reputation=True)

    tx = agent.registerOnChain()
    reg = tx.wait_confirmed(timeout=180).result
    assert reg.agentId
    assert reg.agentURI
    assert str(reg.agentURI).startswith("data:application/json")

    loaded = sdk.loadAgent(reg.agentId)
    assert loaded.name == f"OnChain Agent {suffix}"
    assert loaded.description == f"OnChain registration {suffix}"

