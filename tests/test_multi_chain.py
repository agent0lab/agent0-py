"""
Test for Multi-Chain Agent Operations
Tests all multi-chain functionality using real subgraph queries.

Flow:
1. Test getAgent() with chainId:agentId format across all chains
2. Test searchFeedback() with chainId:agentId format across all chains
3. Test unified searchAgents() with feedback filters across chains
4. Test getReputationSummary() with chainId:agentId format across all chains
5. Test various chain combinations
"""

import logging
import sys
import os
import pytest

# Configure logging: root logger at WARNING to suppress noisy dependencies
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Set debug level ONLY for agent0_sdk
logging.getLogger('agent0_sdk').setLevel(logging.DEBUG)
logging.getLogger('agent0_sdk.core').setLevel(logging.DEBUG)

from agent0_sdk import SDK, SearchFilters
from tests.config import CHAIN_ID, RPC_URL, print_config


def _search_agents(sdk: SDK, filters: SearchFilters, *, sort: list[str] | None = None):
    return sdk.searchAgents(filters=filters, options={"sort": sort or []})

RUN_LIVE_TESTS = os.getenv("RUN_LIVE_TESTS", "0") != "0"
# Supported chains for multi-chain testing
SUPPORTED_CHAINS = [11155111, 84532, 80002]  # ETH Sepolia, Base Sepolia, Polygon Amoy

# Known test agents with feedback (from discovery script)
TEST_AGENTS_WITH_FEEDBACK = {
    11155111: ["11155111:1377", "11155111:1340"],  # Both have feedback
    84532: ["84532:557", "84532:545", "84532:543", "84532:541", "84532:540", "84532:539", "84532:538", "84532:536"],  # All have feedback and averageValue=5.0
}

# Known agents with reputation (averageValue) for reputation search tests
TEST_AGENTS_WITH_REPUTATION = {
    11155111: [],  # No agents with calculated averageValue on this chain
    84532: ["84532:557", "84532:545", "84532:543", "84532:541", "84532:540", "84532:539", "84532:538", "84532:536"],  # All have averageValue=5.0
    80002: [],  # No agents with reputation on this chain
}

# Known tags that exist in feedback data
TEST_TAGS = ["price", "analysis"]


def main():
    print("🌐 Testing Multi-Chain Agent Operations")
    print_config()
    print("=" * 60)
    
    # Initialize SDK without signer (read-only operations)
    # Using default chain (ETH Sepolia)
    sdk = SDK(
        chainId=CHAIN_ID,
        rpcUrl=RPC_URL
    )
    
    print(f"\n📍 Step 1: Test getAgent() with chainId:agentId format")
    print("-" * 60)
    print("Testing getAgent() across all supported chains...")
    
    for chain_id in SUPPORTED_CHAINS:
        try:
            # First, search for agents on this chain to get a real agent ID
            params = SearchFilters()
            params.chains = [chain_id]
            search_result = _search_agents(sdk, params, sort=[])
            
            if search_result and len(search_result) > 0:
                agent_summary = search_result[0]
                # Handle both dict and AgentSummary object
                agent_id = agent_summary.get('agentId') if isinstance(agent_summary, dict) else agent_summary.agentId
                
                # Format as chainId:agentId
                if ':' in agent_id:
                    token_id = agent_id.split(':')[-1]
                else:
                    token_id = agent_id
                full_agent_id = f"{chain_id}:{token_id}"
                
                # Test getAgent with chainId:agentId format
                agent = sdk.indexer.get_agent(full_agent_id)
                
                print(f"✅ Chain {chain_id}: Found agent {agent.name}")
                print(f"   Agent ID: {agent.agentId}")
                print(f"   Chain ID: {agent.chainId} (verified)")
                print(f"   Active: {agent.active}")
            else:
                print(f"⚠️  Chain {chain_id}: No agents found")
        except Exception as e:
            print(f"❌ Chain {chain_id}: Failed - {e}")
    
    print(f"\n📍 Step 2: Test getAgent() with default chain (no chainId prefix)")
    print("-" * 60)
    try:
        # Test with just agentId (uses SDK's default chain)
        params = SearchFilters()
        params.chains = [CHAIN_ID]
        search_result = _search_agents(sdk, params, sort=[])
        
        if search_result and len(search_result) > 0:
            agent_item = search_result[0]
            # Handle both dict and AgentSummary object
            agent_id = agent_item.get('agentId') if isinstance(agent_item, dict) else agent_item.agentId
            # Remove chainId prefix if present
            if ':' in agent_id:
                token_id = agent_id.split(':')[-1]
            else:
                token_id = agent_id
            
            agent = sdk.indexer.get_agent(token_id)
            print(f"✅ Default chain: Found agent {agent.name}")
            print(f"   Agent ID: {agent.agentId}")
            print(f"   Chain ID: {agent.chainId} (should match SDK default: {CHAIN_ID})")
        else:
            print("⚠️  No agents found on default chain")
    except Exception as e:
        print(f"❌ Default chain: Failed - {e}")
    
    print(f"\n📍 Step 3: Test searchFeedback() with chainId:agentId format")
    print("-" * 60)
    print("Testing searchFeedback() across all supported chains...")
    
    for chain_id in SUPPORTED_CHAINS:
        try:
            # Use known agents with feedback if available, otherwise search for any agent
            test_agent_id = None
            if chain_id in TEST_AGENTS_WITH_FEEDBACK and TEST_AGENTS_WITH_FEEDBACK[chain_id]:
                test_agent_id = TEST_AGENTS_WITH_FEEDBACK[chain_id][0]
            else:
                # Fallback: search for any agent
                params = SearchFilters()
                params.chains = [chain_id]
                search_result = _search_agents(sdk, params, sort=[])
                
                if search_result and len(search_result) > 0:
                    agent_summary = search_result[0]
                    # Handle both dict and AgentSummary object
                    agent_id = agent_summary.get('agentId') if isinstance(agent_summary, dict) else agent_summary.agentId
                    
                    # Format as chainId:agentId
                    if ':' in agent_id:
                        token_id = agent_id.split(':')[-1]
                    else:
                        token_id = agent_id
                    test_agent_id = f"{chain_id}:{token_id}"
            
            if test_agent_id:
                # Test searchFeedback with chainId:agentId format
                feedbacks = sdk.indexer.search_feedback(
                    agentId=test_agent_id,
                    first=10,
                    skip=0
                )
                
                print(f"✅ Chain {chain_id}: Found {len(feedbacks)} feedback entries")
                print(f"   Agent ID: {test_agent_id}")
                if feedbacks:
                    print(f"   First feedback value: {feedbacks[0].value if feedbacks[0].value is not None else 'N/A'}")
                    if feedbacks[0].tags:
                        print(f"   First feedback tags: {feedbacks[0].tags}")
                else:
                    print(f"   ⚠️  No feedback found for this agent")
            else:
                print(f"⚠️  Chain {chain_id}: No agents found")
        except Exception as e:
            print(f"❌ Chain {chain_id}: Failed - {e}")
    
    print(f"\n📍 Step 4: Test searchFeedback() with default chain (no chainId prefix)")
    print("-" * 60)
    try:
        # Use known agent with feedback if available
        test_agent_id = None
        if CHAIN_ID in TEST_AGENTS_WITH_FEEDBACK and TEST_AGENTS_WITH_FEEDBACK[CHAIN_ID]:
            full_id = TEST_AGENTS_WITH_FEEDBACK[CHAIN_ID][0]
            # Extract token ID for default chain test
            test_agent_id = full_id.split(':')[-1] if ':' in full_id else full_id
        else:
            # Fallback: search for any agent
            params = SearchFilters()
            params.chains = [CHAIN_ID]
            search_result = _search_agents(sdk, params, sort=[])
            
            if search_result and len(search_result) > 0:
                agent_item = search_result[0]
                # Handle both dict and AgentSummary object
                agent_id = agent_item.get('agentId') if isinstance(agent_item, dict) else agent_item.agentId
                # Remove chainId prefix if present
                if ':' in agent_id:
                    test_agent_id = agent_id.split(':')[-1]
                else:
                    test_agent_id = agent_id
        
        if test_agent_id:
            feedbacks = sdk.indexer.search_feedback(
                agentId=test_agent_id,
                first=10,
                skip=0
            )
            
            print(f"✅ Default chain: Found {len(feedbacks)} feedback entries")
            print(f"   Agent ID: {test_agent_id}")
            if feedbacks:
                print(f"   First feedback value: {feedbacks[0].value if feedbacks[0].value is not None else 'N/A'}")
        else:
            print("⚠️  No agents found on default chain")
    except Exception as e:
        print(f"❌ Default chain: Failed - {e}")
    
    print(f"\n📍 Step 5: Test searchAgents() with feedback filters (single chains)")
    print("-" * 60)
    print("Testing searchAgents() with feedback.hasFeedback across individual chains...")
    
    for chain_id in SUPPORTED_CHAINS:
        try:
            # Use known agents with reputation for this chain
            known_agents = TEST_AGENTS_WITH_REPUTATION.get(chain_id, [])
            
            if known_agents:
                # First, verify agents exist using getAgent
                found_agents = []
                for agent_id in known_agents[:5]:
                    try:
                        agent = sdk.indexer.get_agent(agent_id)
                        found_agents.append(agent)
                    except Exception:
                        continue
                
                if found_agents:
                    # Now try unified search with feedback filters
                    result = sdk.searchAgents(
                        filters={"chains": [chain_id], "feedback": {"hasFeedback": True, "includeRevoked": False}},
                        options={"sort": []},
                    )
                    agents = result
                    
                    if agents:
                        print(f"✅ Chain {chain_id}: Found {len(agents)} agents with feedback")
                        print(f"   Verified {len(found_agents)} known agents exist via getAgent")
                        
                        # Verify all results are from the requested chain
                        all_correct_chain = all(agent.chainId == chain_id for agent in agents)
                        if all_correct_chain:
                            print(f"   ✓ All agents verified from chain {chain_id}")
                        
                        # Show first agent details
                        first_agent = agents[0]
                        avg_value = first_agent.averageValue if getattr(first_agent, "averageValue", None) is not None else 'N/A'
                        print(f"   First agent: {first_agent.name} (Avg Value: {avg_value})")
                    else:
                        print(f"⚠️  Chain {chain_id}: feedback search found 0 agents")
                        print(f"   Known agents exist: {[a.agentId for a in found_agents[:3]]}")
                else:
                    print(f"⚠️  Chain {chain_id}: Could not find any known agents via getAgent")
            else:
                # For chains without reputation data, try general feedback search
                result = sdk.searchAgents(
                    filters={"chains": [chain_id], "feedback": {"hasFeedback": True, "includeRevoked": False}},
                    options={"sort": []},
                )
                agents = result
                if agents:
                    print(f"✅ Chain {chain_id}: Found {len(agents)} agents with feedback")
                else:
                    print(f"✅ Chain {chain_id}: Found 0 agents (expected: 0 - no feedback data)")
        except Exception as e:
            print(f"❌ Chain {chain_id}: Failed - {e}")
    
    print(f"\n📍 Step 6: Test searchAgents() with feedback filters (multiple chains)")
    print("-" * 60)
    print("Testing with chain combinations...")
    
    # Test with 2 chains
    chain_pairs = [
        [11155111, 84532],
        [11155111, 80002],
        [84532, 80002],
    ]
    
    for chains in chain_pairs:
        try:
            # Collect known agents with reputation from all chains in this pair
            known_agents = []
            for cid in chains:
                known_agents.extend(TEST_AGENTS_WITH_REPUTATION.get(cid, []))
            
            # Try unified search with feedback filters
            result = sdk.searchAgents(
                filters={"chains": chains, "feedback": {"hasFeedback": True, "includeRevoked": False}},
                options={"sort": []},
            )
            
            agents = result
            successful_chains = []
            failed_chains = []
            
            chain_ids = set(agent.chainId for agent in agents)
            if agents:
                print(f"✅ Chains {chains}: Found {len(agents)} agents with feedback")
            else:
                print(f"⚠️  Chains {chains}: feedback search found 0 agents")
                if known_agents:
                    print(f"   Known agents: {known_agents[:5]}")
                else:
                    print(f"   ✅ Chains {chains}: Found 0 agents (expected: 0 - no reputation data)")
            
            print(f"   Successful chains: {successful_chains}")
            if failed_chains:
                print(f"   Failed chains: {failed_chains}")
            print(f"   Unique chains in results: {list(chain_ids)}")
            
            # Show sample agents
            if agents:
                print(f"   Sample agents:")
                for i, agent in enumerate(agents[:3], 1):
                    avg_value = agent.averageValue if getattr(agent, "averageValue", None) is not None else 'N/A'
                    print(f"      {i}. {agent.name} (Chain: {agent.chainId}, Avg: {avg_value})")
        except Exception as e:
            print(f"❌ Chains {chains}: Failed - {e}")
    
    print(f"\n📍 Step 7: Test searchAgents() with feedback filters and chains='all'")
    print("-" * 60)
    try:
        # Collect all known agents with reputation
        all_known_agents = []
        for chain_id in SUPPORTED_CHAINS:
            all_known_agents.extend(TEST_AGENTS_WITH_REPUTATION.get(chain_id, []))
        
        if all_known_agents:
            # Query for specific agents we know have reputation
            result = sdk.searchAgents(
                filters={"agentIds": all_known_agents, "chains": "all", "feedback": {"hasFeedback": True, "includeRevoked": False}},
                options={"sort": []},
            )
        else:
            # General search if no known agents
            result = sdk.searchAgents(
                filters={"chains": "all", "feedback": {"hasFeedback": True, "includeRevoked": False}},
                options={"sort": []},
            )
        
        agents = result
        successful_chains = []
        failed_chains = []
        
        chain_ids = set(agent.chainId for agent in agents)
        if agents:
            print(f"✅ Found {len(agents)} agents across all chains")
        else:
            # If search returned 0, verify agents exist and show reputation
            if all_known_agents:
                print(f"⚠️  feedback search found 0 agents")
                print(f"   Verifying {len(all_known_agents)} known agents exist...")
                reputation_found = 0
                for agent_id in all_known_agents[:5]:
                    try:
                        agent = sdk.indexer.get_agent(agent_id)
                        summary = sdk.getReputationSummary(agent_id)
                        if summary.get('count', 0) > 0:
                            reputation_found += 1
                            if reputation_found <= 3:  # Show first 3
                                print(f"   ✅ {agent_id}: {summary['count']} feedback, avg: {summary['averageValue']:.2f}")
                    except Exception:
                        continue
                if reputation_found > 0:
                    print(f"   ✓ Found reputation data for {reputation_found} agents via getReputationSummary")
            else:
                print(f"✅ Found 0 agents (expected: 0 - no reputation data)")
        print(f"   Successful chains: {successful_chains}")
        if failed_chains:
            print(f"   Failed chains: {failed_chains}")
        print(f"   Unique chains in results: {list(chain_ids)}")
        
        # Show sample agents from different chains
        if agents:
            print(f"   Sample agents:")
            for i, agent in enumerate(agents[:5], 1):
                avg_value = agent.averageValue if getattr(agent, "averageValue", None) is not None else 'N/A'
                print(f"      {i}. {agent.name} (Chain: {agent.chainId}, Avg: {avg_value})")
    except Exception as e:
        print(f"❌ All chains: Failed - {e}")
    
    print(f"\n📍 Step 8: Test searchAgents() with feedback tag filter")
    print("-" * 60)
    try:
        # Use known tags that exist in feedback data
        # Test with chains that have reputation data (84532 has agents with averageValue)
        result = sdk.searchAgents(
            filters={"chains": [84532], "feedback": {"tag": TEST_TAGS[0], "includeRevoked": False}},
            options={"sort": []},
        )
        
        agents = result
        print(f"✅ Found {len(agents)} agents with filters")
        print(f"   Filter: feedback.tag={TEST_TAGS[0]}, chains=[84532]")
        if agents:
            for i, agent in enumerate(agents[:3], 1):
                avg_value = agent.averageValue if getattr(agent, "averageValue", None) is not None else 'N/A'
                print(f"   {i}. {agent.name} (Chain: {agent.chainId}, Avg: {avg_value})")
        else:
            print(f"   ⚠️  No agents found with tag '{TEST_TAGS[0]}' (may need to check if tag filtering works)")
    except Exception as e:
        print(f"❌ Filtered multi-chain search: Failed - {e}")
    
    print(f"\n📍 Step 9: Test getReputationSummary() with chainId:agentId format")
    print("-" * 60)
    print("Testing getReputationSummary() across all supported chains...")
    
    for chain_id in SUPPORTED_CHAINS:
        try:
            # Use known agents with feedback if available
            test_agent_id = None
            if chain_id in TEST_AGENTS_WITH_FEEDBACK and TEST_AGENTS_WITH_FEEDBACK[chain_id]:
                test_agent_id = TEST_AGENTS_WITH_FEEDBACK[chain_id][0]
            else:
                # Fallback: search for agents and try each one
                params = SearchFilters()
                params.chains = [chain_id]
                search_result = _search_agents(sdk, params, sort=[])
                
                if search_result and len(search_result) > 0:
                    # Try to get reputation for each agent until we find one with feedback
                    for agent_summary in search_result:
                        # Handle both dict and AgentSummary object
                        agent_id = agent_summary.get('agentId') if isinstance(agent_summary, dict) else agent_summary.agentId
                        if ':' in agent_id:
                            token_id = agent_id.split(':')[-1]
                        else:
                            token_id = agent_id
                        test_agent_id = f"{chain_id}:{token_id}"
                        
                        try:
                            summary = sdk.getReputationSummary(test_agent_id)
                            # If we get here, we found one with feedback
                            break
                        except Exception:
                            test_agent_id = None
                            continue
            
            if test_agent_id:
                try:
                    summary = sdk.getReputationSummary(test_agent_id)
                    
                    print(f"✅ Chain {chain_id}: Got reputation summary")
                    print(f"   Agent ID: {test_agent_id}")
                    print(f"   Count: {summary['count']}")
                    print(f"   Average Value: {summary['averageValue']:.2f}")
                except Exception as e:
                    print(f"⚠️  Chain {chain_id}: Failed to get reputation for {test_agent_id}: {e}")
            else:
                print(f"⚠️  Chain {chain_id}: No agents with feedback found")
        except Exception as e:
            print(f"❌ Chain {chain_id}: Failed - {e}")
    
    print(f"\n📍 Step 10: Test getReputationSummary() with default chain (no chainId prefix)")
    print("-" * 60)
    try:
        # Use known agent with feedback if available
        test_agent_id = None
        if CHAIN_ID in TEST_AGENTS_WITH_FEEDBACK and TEST_AGENTS_WITH_FEEDBACK[CHAIN_ID]:
            full_id = TEST_AGENTS_WITH_FEEDBACK[CHAIN_ID][0]
            # Extract token ID for default chain test
            test_agent_id = full_id.split(':')[-1] if ':' in full_id else full_id
        else:
            # Fallback: search for agents and try each one
            params = SearchFilters()
            params.chains = [CHAIN_ID]
            search_result = _search_agents(sdk, params, sort=[])
            
            if search_result and len(search_result) > 0:
                # Try to get reputation for each agent until we find one with feedback
                for agent_summary in search_result:
                    # Handle both dict and AgentSummary object
                    agent_id = agent_summary.get('agentId') if isinstance(agent_summary, dict) else agent_summary.agentId
                    if ':' in agent_id:
                        test_agent_id = agent_id.split(':')[-1]
                    else:
                        test_agent_id = agent_id
                    
                    try:
                        summary = sdk.getReputationSummary(test_agent_id)
                        # If we get here, we found one with feedback
                        break
                    except Exception:
                        test_agent_id = None
                        continue
        
        if test_agent_id:
            try:
                summary = sdk.getReputationSummary(test_agent_id)
                
                print(f"✅ Default chain: Got reputation summary")
                print(f"   Agent ID: {test_agent_id}")
                print(f"   Count: {summary['count']}")
                print(f"   Average Value: {summary['averageValue']:.2f}")
            except Exception as e:
                print(f"⚠️  Default chain: Failed to get reputation for {test_agent_id}: {e}")
        else:
            print("⚠️  No agents with feedback found on default chain")
    except Exception as e:
        print(f"❌ Default chain: Failed - {e}")
    
    print(f"\n📍 Step 11: Test all three chains together")
    print("-" * 60)
    try:
        # Collect all known agents with reputation
        all_known_agents = []
        for chain_id in SUPPORTED_CHAINS:
            all_known_agents.extend(TEST_AGENTS_WITH_REPUTATION.get(chain_id, []))
        
        if all_known_agents:
            # Query for specific agents we know have reputation
            result = sdk.searchAgents(
                filters={"agentIds": all_known_agents, "chains": SUPPORTED_CHAINS, "feedback": {"hasFeedback": True, "includeRevoked": False}},
                options={"sort": []},
            )
        else:
            # General search if no known agents
            result = sdk.searchAgents(
                filters={"chains": SUPPORTED_CHAINS, "feedback": {"hasFeedback": True, "includeRevoked": False}},
                options={"sort": []},
            )
        
        agents = result
        chain_ids = set(agent.chainId for agent in agents)
        
        if agents:
            print(f"✅ All three chains: Found {len(agents)} agents")
        else:
            # If search returned 0, verify agents exist and show reputation
            if all_known_agents:
                print(f"⚠️  feedback search found 0 agents")
                print(f"   Verifying {len(all_known_agents)} known agents exist...")
                reputation_found = 0
                for agent_id in all_known_agents[:5]:
                    try:
                        agent = sdk.indexer.get_agent(agent_id)
                        summary = sdk.getReputationSummary(agent_id)
                        if summary.get('count', 0) > 0:
                            reputation_found += 1
                            if reputation_found <= 3:  # Show first 3
                                print(f"   ✅ {agent_id}: {summary['count']} feedback, avg: {summary['averageValue']:.2f}")
                    except Exception:
                        continue
                if reputation_found > 0:
                    print(f"   ✓ Found reputation data for {reputation_found} agents via getReputationSummary")
            else:
                print(f"✅ All three chains: Found 0 agents (expected: 0 - no reputation data)")
        print(f"   Unique chains in results: {list(chain_ids)}")
        
        # Group by chain
        by_chain = {}
        for agent in agents:
            chain = agent.chainId
            if chain not in by_chain:
                by_chain[chain] = []
            by_chain[chain].append(agent)
        
        for chain, chain_agents in by_chain.items():
            print(f"   Chain {chain}: {len(chain_agents)} agents")
        
        # Show sample agents
        if agents:
            print(f"   Sample agents:")
            for i, agent in enumerate(agents[:5], 1):
                avg_value = agent.extras.get('averageValue', 'N/A') if agent.extras else 'N/A'
                print(f"      {i}. {agent.name} (Chain: {agent.chainId}, Avg: {avg_value})")
    except Exception as e:
        print(f"❌ All three chains: Failed - {e}")
    
    print("\n" + "=" * 60)
    print("✅ Multi-Chain Tests Completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()


@pytest.mark.integration
def test_multi_chain_live():
    if not RUN_LIVE_TESTS:
        pytest.skip("Set RUN_LIVE_TESTS=1 to enable live integration tests")
    if not RPC_URL or not RPC_URL.strip():
        pytest.skip("RPC_URL not set")
    # Strict integration checks (do not swallow exceptions).
    sdk = SDK(chainId=CHAIN_ID, rpcUrl=RPC_URL)

    from agent0_sdk.core.contracts import DEFAULT_SUBGRAPH_URLS
    chains = list(DEFAULT_SUBGRAPH_URLS.keys())
    assert len(chains) > 0

    r = sdk.searchAgents(filters={"chains": chains}, options={"sort": []})
    assert isinstance(r, list)
    assert len(r) > 0
