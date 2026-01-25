"""
Test for Agent Search and Discovery using Subgraph
Tests various search and filtering capabilities for discovering agents and their reputation.

Flow:
1. Get a specific agent by ID
2. Search agents by name (partial match)
3. Search agents by capabilities (MCP tools)
4. Search agents by skills (A2A)
5. Search agents by ENS domain
6. Search agents by active status
7. Combine multiple filters (capabilities + skills)
8. Search agents by reputation with minimum average value
9. Search agents by reputation with specific tags
10. Search agents by reputation with capability filtering
11. Advanced: Find top-rated agents with specific skills
12. Advanced: Find agents with multiple requirements
13. Pagination test
14. Sort by activity test
15. Search agents by single owner address
16. Search agents by multiple owner addresses
17. Search agents by operator addresses
18. Combined search: owner + active status
19. Combined search: owner + name filter
"""

import logging
import time
import random
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

from agent0_sdk import SDK, SearchParams
from tests.config import CHAIN_ID, RPC_URL, AGENT_PRIVATE_KEY, SUBGRAPH_URL, AGENT_ID, print_config

RUN_LIVE_TESTS = os.getenv("RUN_LIVE_TESTS", "0") != "0"

def main():
    print("🔍 Testing Agent Search and Discovery")
    print_config()
    print("=" * 60)
    
    # Initialize SDK without signer (read-only operations)
    sdk = SDK(
        chainId=CHAIN_ID,
        rpcUrl=RPC_URL
    )
    
    print(f"\n📍 Step 1: Get Agent by ID")
    print("-" * 60)
    try:
        agent = sdk.getAgent(AGENT_ID)
        print(f"✅ Agent found: {agent.name}")
        print(f"   Description: {agent.description[:80] if agent.description else 'N/A'}...")
        print(f"   Chain ID: {agent.chainId}")
        print(f"   Active: {agent.active}")
        print(f"   ENS: {agent.ens}")
        print(f"   Agent ID: {agent.agentId}")
        # MCP and A2A support determined by endpoint presence
        if hasattr(agent, 'mcpEndpoint') and agent.mcpEndpoint:
            print(f"   MCP: {agent.mcpEndpoint}")
        if hasattr(agent, 'a2aEndpoint') and agent.a2aEndpoint:
            print(f"   A2A: {agent.a2aEndpoint}")
    except Exception as e:
        print(f"❌ Failed to get agent: {e}")
    
    print(f"\n📍 Step 2: Search Agents by Name (Partial Match)")
    print("-" * 60)
    try:
        results = sdk.searchAgents(name="Test")
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) with name matching 'Test'")
        for i, agent in enumerate(agents[:3], 1):
            agent_id = agent.get('agentId', agent.get('id', 'N/A'))
            print(f"   {i}. {agent['name']} (ID: {agent_id})")
            if agent.get('description'):
                print(f"      {agent['description'][:60]}...")
    except Exception as e:
        print(f"❌ Failed to search by name: {e}")
    
    print(f"\n📍 Step 3: Search Agents by MCP Tools (Capabilities)")
    print("-" * 60)
    try:
        # Using capabilities from test_feedback.py: data_analysis, code_generation, natural_language_understanding, problem_solving, communication
        results = sdk.searchAgents(mcpTools=["data_analysis"])
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) with 'data_analysis' capability")
        for i, agent in enumerate(agents[:3], 1):
            print(f"   {i}. {agent['name']}")
            if agent.get('mcpTools'):
                print(f"      Tools: {', '.join(agent['mcpTools'][:3])}...")
    except Exception as e:
        print(f"❌ Failed to search by capabilities: {e}")
    
    print(f"\n📍 Step 4: Search Agents by A2A Skills")
    print("-" * 60)
    try:
        # Using skills from test_feedback.py: python, javascript, machine_learning, web_development, cloud_computing
        results = sdk.searchAgents(a2aSkills=["javascript"])
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) with 'javascript' skill")
        for i, agent in enumerate(agents[:3], 1):
            print(f"   {i}. {agent['name']}")
            if agent.get('a2aSkills'):
                print(f"      Skills: {', '.join(agent['a2aSkills'][:3])}...")
    except Exception as e:
        print(f"❌ Failed to search by skills: {e}")
    
    print(f"\n📍 Step 5: Search Agents by ENS Domain")
    print("-" * 60)
    try:
        results = sdk.searchAgents(ens="test")
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) with ENS matching 'test'")
        for i, agent in enumerate(agents[:3], 1):
            print(f"   {i}. {agent['name']}")
            if agent.get('ens'):
                print(f"      ENS: {agent['ens']}")
    except Exception as e:
        print(f"❌ Failed to search by ENS: {e}")
    
    print(f"\n📍 Step 6: Search Only Active Agents")
    print("-" * 60)
    try:
        results = sdk.searchAgents(active=True, page_size=10)
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} active agent(s)")
        for i, agent in enumerate(agents[:3], 1):
            print(f"   {i}. {agent['name']} - {agent.get('totalFeedback', 0)} feedback")
    except Exception as e:
        print(f"❌ Failed to search active agents: {e}")
    
    print(f"\n📍 Step 7: Search Agents with Multiple Filters (Capabilities + Skills)")
    print("-" * 60)
    try:
        # Using capabilities and skills from test_feedback.py:
        # Capabilities: data_analysis, code_generation, natural_language_understanding, problem_solving, communication
        # Skills: python, javascript, machine_learning, web_development, cloud_computing
        results = sdk.searchAgents(
            mcpTools=["communication"],
            a2aSkills=["python"]
        )
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) with 'communication' capability AND 'python' skill")
        for i, agent in enumerate(agents[:3], 1):
            print(f"   {i}. {agent['name']}")
    except Exception as e:
        print(f"❌ Failed to search with multiple filters: {e}")
    
    print(f"\n📍 Step 8: Search Agents by Reputation (Minimum Average Value)")
    print("-" * 60)
    try:
        results = sdk.searchAgentsByReputation(minAverageValue=80)
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) with average value >= 80")
        for i, agent in enumerate(agents[:3], 1):
            # AgentSummary object - use attributes, not dict.get()
            avg_value = agent.extras.get('averageValue', 'N/A') if agent.extras else 'N/A'
            print(f"   {i}. {agent.name}")
            print(f"      Average Value: {avg_value}")
            print(f"      Agent ID: {agent.agentId}")
    except Exception as e:
        print(f"❌ Failed to search by reputation value: {e}")
    
    print(f"\n📍 Step 9: Search Agents by Reputation with Specific Tags")
    print("-" * 60)
    try:
        # Using tags that actually exist in feedback: "enterprise" appears frequently
        # Note: GraphQL query has known issue with mixing filters, so using includeRevoked=True as workaround
        # which may affect results, but at least the query will execute
        results = sdk.searchAgentsByReputation(
            tags=["enterprise"],
            minAverageValue=0,  # No threshold to see any results
            includeRevoked=True  # Workaround for GraphQL query builder issue
        )
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) with 'enterprise' tag")
        for i, agent in enumerate(agents[:3], 1):
            # AgentSummary object - use attributes
            avg_value = agent.extras.get('averageValue', 'N/A') if agent.extras else 'N/A'
            print(f"   {i}. {agent.name} - Avg: {avg_value}")
    except Exception as e:
        print(f"❌ Failed to search by reputation tags: {e}")
    
    print(f"\n📍 Step 10: Search Agents by Reputation with Capability Filtering")
    print("-" * 60)
    try:
        # Using capabilities that actually exist in feedback: code_generation, problem_solving, data_analysis
        results = sdk.searchAgentsByReputation(
            capabilities=["code_generation"],
            minAverageValue=0  # No threshold to see any results
        )
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) with 'code_generation' capability")
        for i, agent in enumerate(agents[:3], 1):
            avg_value = agent.extras.get('averageValue', 'N/A') if hasattr(agent, 'extras') and agent.extras else 'N/A'
            print(f"   {i}. {agent.name}")
            print(f"      Avg Value: {avg_value}")
    except Exception as e:
        print(f"❌ Failed to search by reputation with capabilities: {e}")
    
    print(f"\n📍 Step 11: Advanced - Find Top-Rated Agents with Specific Skills")
    print("-" * 60)
    try:
        # Using skills that actually exist in feedback: python, machine_learning, cloud_computing, web_development
        results = sdk.searchAgentsByReputation(
            skills=["python"],
            minAverageValue=0  # No threshold to see any results
        )
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) with 'python' skill")
        for i, agent in enumerate(agents[:3], 1):
            # AgentSummary object - use attributes
            avg_value = agent.extras.get('averageValue', 'N/A') if agent.extras else 'N/A'
            print(f"   {i}. {agent.name}")
            print(f"      Average Value: {avg_value}")
            if agent.a2aSkills:
                print(f"      Skills: {', '.join(agent.a2aSkills[:3])}")
    except Exception as e:
        print(f"❌ Failed advanced skill search: {e}")
    
    print(f"\n📍 Step 12: Advanced - Complex Multi-Criteria Search")
    print("-" * 60)
    try:
        results = sdk.searchAgents(name="Test", active=True, page_size=10)
        agents = results.get('items', [])
        print(f"✅ Found {len(agents)} agent(s) matching multiple criteria")
        for i, agent in enumerate(agents[:3], 1):
            print(f"   {i}. {agent['name']}")
            print(f"      Active: {agent.get('active', False)}, Feedback: {agent.get('totalFeedback', 0)}")
            if agent.get('ens'):
                print(f"      ENS: {agent['ens']}")
    except Exception as e:
        print(f"❌ Failed complex search: {e}")
    
    print(f"\n📍 Step 13: Pagination Test (First 5 Agents)")
    print("-" * 60)
    try:
        results = sdk.searchAgents(page_size=5)
        agents = results.get('items', [])
        print(f"✅ Retrieved first page: {len(agents)} agent(s)")
        for i, agent in enumerate(agents, 1):
            agent_id = agent.get('agentId', agent.get('id', 'N/A'))
            print(f"   {i}. {agent['name']} (ID: {agent_id})")
    except Exception as e:
        print(f"❌ Failed pagination test: {e}")
    
    print(f"\n📍 Step 14: Sort by Activity (Most Recent)")
    print("-" * 60)
    try:
        results = sdk.searchAgents(page_size=10, sort=["updatedAt:desc"])
        agents = results.get('items', [])
        if agents:
            print(f"✅ Retrieved {len(agents)} agents")
            print(f"   Most recent activity IDs:")
            for i, agent in enumerate(agents[:5], 1):
                agent_id = agent.get('agentId', agent.get('id', 'N/A'))
                print(f"   {i}. ID {agent_id}: {agent['name']}")
    except Exception as e:
        print(f"❌ Failed activity sort: {e}")

    print(f"\n📍 Step 15: Search Agents by Single Owner Address")
    print("-" * 60)
    try:
        # First, get an agent to extract its owner address for testing
        test_agent = sdk.getAgent(AGENT_ID)
        if hasattr(test_agent, 'owner') and test_agent.owner:
            owner_address = test_agent.owner
            print(f"   Testing with owner address: {owner_address}")

            results = sdk.searchAgents(owners=[owner_address])
            agents = results.get('items', [])
            print(f"✅ Found {len(agents)} agent(s) owned by {owner_address[:10]}...{owner_address[-8:]}")

            for i, agent in enumerate(agents[:3], 1):
                agent_id = agent.get('agentId', agent.get('id', 'N/A'))
                agent_owner = agent.get('owner', 'N/A')
                print(f"   {i}. {agent['name']} (ID: {agent_id})")
                print(f"      Owner: {agent_owner[:10]}...{agent_owner[-8:] if len(agent_owner) > 18 else agent_owner}")
        else:
            print("⚠️  Test agent doesn't have owner information")
    except Exception as e:
        print(f"❌ Failed to search by single owner: {e}")

    print(f"\n📍 Step 16: Search Agents by Multiple Owner Addresses")
    print("-" * 60)
    try:
        # Get multiple agents to collect different owner addresses
        results = sdk.searchAgents(page_size=5)
        agents = results.get('items', [])
        owner_addresses = []

        for agent in agents:
            if agent.get('owner') and agent['owner'] not in owner_addresses:
                owner_addresses.append(agent['owner'])
                if len(owner_addresses) >= 2:
                    break

        if len(owner_addresses) >= 2:
            print(f"   Testing with {len(owner_addresses)} owner addresses")
            results = sdk.searchAgents(owners=owner_addresses)
            agents = results.get('items', [])
            print(f"✅ Found {len(agents)} agent(s) owned by multiple addresses")

            for i, agent in enumerate(agents[:5], 1):
                agent_id = agent.get('agentId', agent.get('id', 'N/A'))
                agent_owner = agent.get('owner', 'N/A')
                print(f"   {i}. {agent['name']} (Owner: {agent_owner[:10]}...{agent_owner[-8:] if len(agent_owner) > 18 else agent_owner})")
        else:
            print("⚠️  Not enough different owners found for multi-owner test")
    except Exception as e:
        print(f"❌ Failed to search by multiple owners: {e}")

    print(f"\n📍 Step 17: Search Agents by Operator Addresses")
    print("-" * 60)
    try:
        # First check if any agents have operators defined
        results = sdk.searchAgents(page_size=10)
        agents = results.get('items', [])
        test_operators = []

        for agent in agents:
            if agent.get('operators') and len(agent['operators']) > 0:
                test_operators = agent['operators'][:1]  # Use first operator
                print(f"   Testing with operator: {test_operators[0][:10]}...{test_operators[0][-8:]}")
                break

        if test_operators:
            results = sdk.searchAgents(operators=test_operators)
            found_agents = results.get('items', [])
            print(f"✅ Found {len(found_agents)} agent(s) with specified operator")

            for i, agent in enumerate(found_agents[:3], 1):
                agent_id = agent.get('agentId', agent.get('id', 'N/A'))
                agent_operators = agent.get('operators', [])
                print(f"   {i}. {agent['name']} (ID: {agent_id})")
                if agent_operators:
                    print(f"      Operators: {len(agent_operators)} total")
        else:
            print("⚠️  No agents with operators found for testing")
    except Exception as e:
        print(f"❌ Failed to search by operators: {e}")

    print(f"\n📍 Step 18: Combined Search - Owner + Active Status")
    print("-" * 60)
    try:
        # Get an owner address from an active agent
        results = sdk.searchAgents(active=True, page_size=5)
        agents = results.get('items', [])

        if agents and agents[0].get('owner'):
            test_owner = agents[0]['owner']
            print(f"   Testing owner {test_owner[:10]}...{test_owner[-8:]} + active=True")

            results = sdk.searchAgents(owners=[test_owner], active=True)
            found_agents = results.get('items', [])
            print(f"✅ Found {len(found_agents)} active agent(s) owned by specified address")

            for i, agent in enumerate(found_agents[:3], 1):
                agent_id = agent.get('agentId', agent.get('id', 'N/A'))
                print(f"   {i}. {agent['name']} (ID: {agent_id})")
                print(f"      Active: {agent.get('active', False)}, Owner: {agent.get('owner', 'N/A')[:10]}...")
        else:
            print("⚠️  No active agents with owner information found")
    except Exception as e:
        print(f"❌ Failed combined owner + active search: {e}")

    print(f"\n📍 Step 19: Combined Search - Owner + Name Filter")
    print("-" * 60)
    try:
        # Get agents and find one with both name and owner
        results = sdk.searchAgents(page_size=10)
        agents = results.get('items', [])

        test_agent = None
        for agent in agents:
            if agent.get('owner') and agent.get('name'):
                test_agent = agent
                break

        if test_agent:
            test_owner = test_agent['owner']
            # Use partial name for search
            name_part = test_agent['name'][:4] if len(test_agent['name']) > 4 else test_agent['name']
            print(f"   Testing owner filter + name contains '{name_part}'")

            results = sdk.searchAgents(owners=[test_owner], name=name_part)
            found_agents = results.get('items', [])
            print(f"✅ Found {len(found_agents)} agent(s) matching both criteria")

            for i, agent in enumerate(found_agents[:3], 1):
                agent_id = agent.get('agentId', agent.get('id', 'N/A'))
                print(f"   {i}. {agent['name']} (ID: {agent_id})")
        else:
            print("⚠️  No suitable test agent found")
    except Exception as e:
        print(f"❌ Failed combined owner + name search: {e}")

    print("\n" + "=" * 60)
    print("✅ Search Tests Completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()


@pytest.mark.integration
def test_search_live():
    if not RUN_LIVE_TESTS:
        pytest.skip("Set RUN_LIVE_TESTS=1 to enable live integration tests")
    if not RPC_URL or not RPC_URL.strip():
        pytest.skip("RPC_URL not set")
    if not SUBGRAPH_URL or not SUBGRAPH_URL.strip():
        pytest.skip("SUBGRAPH_URL not set")

    main()
