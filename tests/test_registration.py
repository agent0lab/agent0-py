"""
Test for Agent Registration with HTTP URI
Creates an agent, registers it with a mock HTTP URI, updates it, and verifies data integrity.

Flow:
1. Register agent on-chain with mock URI (obtain agentId)
2. Prepare registration file with obtained agentId
3. Print registration file JSON for developer to host
4. Update agent and verify consistency
"""

import logging
import time
import random
import json
import sys

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

from agent0_sdk import SDK
from tests.config import CHAIN_ID, RPC_URL, AGENT_PRIVATE_KEY, CLIENT_PRIVATE_KEY, print_config
from eth_account import Account


def generateRandomData():
    """Generate random test data for the agent."""
    randomSuffix = random.randint(1000, 9999)
    timestamp = int(time.time())
    
    return {
        'name': f"Test Agent {randomSuffix}",
        'description': f"Created at {timestamp}",
        'image': f"https://example.com/image_{randomSuffix}.png",
        'mcpEndpoint': f"https://api.example.com/mcp/{randomSuffix}",
        # Latest MCP spec version (per ERC-8004 registration file examples)
        'mcpVersion': "2025-06-18",
        'a2aEndpoint': f"https://api.example.com/a2a/{randomSuffix}.json",
        # Latest A2A spec version (per ERC-8004 registration file examples)
        'a2aVersion': "0.3.0",
        'ensName': f"test{randomSuffix}.eth",
        # Latest ENS endpoint version (per ERC-8004 registration file examples)
        'ensVersion': "v1",
        'active': False,
        'x402support': True,
        'reputation': random.choice([True, False]),
        'cryptoEconomic': random.choice([True, False]),
        'teeAttestation': random.choice([True, False])
    }


def main():
    print("🧪 Testing Agent Registration with HTTP URI")
    print_config()
    
    # SDK Configuration - no IPFS
    sdkConfig = {
        'chainId': CHAIN_ID,
        'rpcUrl': RPC_URL
    }
    
    sdk = SDK(signer=AGENT_PRIVATE_KEY, **sdkConfig)
    testData = generateRandomData()
    
    # Step 1: Register agent on-chain with mock HTTP URI
    print("\n📍 Step 1: Register Agent on-Chain with Mock URI")
    print("-" * 60)
    
    agent = sdk.createAgent(
        name=testData['name'],
        description=testData['description'],
        image=testData['image']
    )
    
    # Register with mock URI to get agentId
    mockUri = "https://example.com/agents/registration.json"
    agent.register(mockUri)
    agentId = agent.agentId
    print(f"✅ Registered: ID={agentId}")
    print(f"   Mock URI: {mockUri}")
    
    # Step 2: Configure agent with all details
    print("\n📍 Step 2: Configure Agent Details")
    print("-" * 60)
    print(f"✅ Created: {testData['name']}")
    
    agent.setMCP(testData['mcpEndpoint'], testData['mcpVersion'])
    agent.setA2A(testData['a2aEndpoint'], testData['a2aVersion'])
    agent.setENS(testData['ensName'], testData['ensVersion'])
    # OASF skills/domains (validated against bundled taxonomy)
    agent.addSkill("advanced_reasoning_planning/strategic_planning", validate_oasf=True)
    agent.addDomain("finance_and_business/investment_services", validate_oasf=True)
    # Note: setWallet() is on-chain only and requires the NEW wallet to sign.
    # For testing, use CLIENT_PRIVATE_KEY as the second wallet and let the SDK build/sign the typed data.
    if not CLIENT_PRIVATE_KEY:
        raise ValueError("CLIENT_PRIVATE_KEY must be set in .env file for this test")
    
    # Create account from CLIENT_PRIVATE_KEY to get address and sign (second wallet)
    second_wallet_account = Account.from_key(CLIENT_PRIVATE_KEY)
    second_wallet_address = second_wallet_account.address
    print(f"✅ Using second wallet address (from CLIENT_PRIVATE_KEY): {second_wallet_address}")

    # Set agent wallet (SDK builds + signs typed data using CLIENT_PRIVATE_KEY)
    # Store walletChainId as current chain for local bookkeeping
    agent.setWallet(second_wallet_address, sdk.chainId, new_wallet_signer=CLIENT_PRIVATE_KEY)
    agent.setActive(testData['active'])
    agent.setX402Support(testData['x402support'])
    agent.setTrust(
        reputation=testData['reputation'],
        cryptoEconomic=testData['cryptoEconomic'],
        teeAttestation=testData['teeAttestation']
    )
    
    # Step 3: Get registration file and print it
    print("\n📍 Step 3: Registration File for Hosting")
    print("-" * 60)
    
    registrationFile = agent.getRegistrationFile()
    registrationJson = json.dumps(registrationFile.to_dict(), indent=2)
    
    print("Registration file JSON (host this at the URL you specified):")
    print("\n" + registrationJson)
    
    # Save to file
    filename = f"agent_registration_{agentId.replace(':', '_')}.json"
    with open(filename, 'w') as f:
        f.write(registrationJson)
    print(f"\n✅ Saved to: {filename}")
    
    capturedState = {
        'agentId': agent.agentId,
        'agentURI': agent.agentURI,
        'name': agent.name,
        'description': agent.description,
        'image': agent.image,
        'walletAddress': agent.walletAddress,
        'walletChainId': agent.walletChainId,
        'active': agent.active,
        'x402support': agent.x402support,
        'mcpEndpoint': agent.mcpEndpoint,
        'a2aEndpoint': agent.a2aEndpoint,
        'ensEndpoint': agent.ensEndpoint,
        'metadata': agent.metadata.copy()
    }
    
    # Step 4: Update agent
    print("\n📍 Step 4: Update Agent")
    print("-" * 60)
    
    agent.updateInfo(
        name=testData['name'] + " UPDATED",
        description=testData['description'] + " - UPDATED",
        image=f"https://example.com/image_{random.randint(1000, 9999)}_updated.png"
    )
    agent.setMCP(
        f"https://api.example.com/mcp/{random.randint(10000, 99999)}",
        "2025-06-18",
    )
    agent.setA2A(
        f"https://api.example.com/a2a/{random.randint(10000, 99999)}.json",
        "0.3.0",
    )
    # Keep using the second wallet. This should be a no-op (wallet already set), but exercises the flow.
    agent.setWallet(second_wallet_address, sdk.chainId, new_wallet_signer=CLIENT_PRIVATE_KEY)
    agent.setENS(f"{testData['ensName']}.updated", "v1")
    # Update OASF skills/domains as well (validated)
    agent.addSkill("advanced_reasoning_planning/strategic_planning", validate_oasf=True)
    agent.addDomain("finance_and_business/investment_services", validate_oasf=True)
    agent.setActive(False)
    agent.setX402Support(True)
    agent.setTrust(
        reputation=random.choice([True, False]),
        cryptoEconomic=random.choice([True, False]),
        teeAttestation=random.choice([True, False])
    )
    agent.setMetadata({
        "testKey": "testValue",
        "timestamp": int(time.time()),
        "customField": "customValue",
        "anotherField": "anotherValue",
        "numericField": random.randint(1000, 9999)
    })
    
    # Update registration file and re-register
    registrationFileUpdated = agent.getRegistrationFile()
    registrationJsonUpdated = json.dumps(registrationFileUpdated.to_dict(), indent=2)
    
    filenameUpdated = f"agent_registration_{agentId.replace(':', '_')}_updated.json"
    with open(filenameUpdated, 'w') as f:
        f.write(registrationJsonUpdated)
    
    agent.register(mockUri)
    print(f"✅ Updated & re-registered")
    print(f"   Updated registration file: {filenameUpdated}")
    
    # Capture updated state
    updatedState = {
        'name': agent.name,
        'description': agent.description,
        'image': agent.image,
        'walletAddress': agent.walletAddress,
        'walletChainId': agent.walletChainId,
        'active': agent.active,
        'x402support': agent.x402support,
        'mcpEndpoint': agent.mcpEndpoint,
        'a2aEndpoint': agent.a2aEndpoint,
        'ensEndpoint': agent.ensEndpoint,
        'metadata': agent.metadata.copy()
    }
    
    # Step 5: Reload and verify
    print("\n📍 Step 5: Reload and Verify")
    print("-" * 60)
    
    reloadedAgentId = agent.agentId
    del agent
    print("⏳ Waiting for blockchain transaction to be mined (15 seconds)...")
    time.sleep(15)
    reloadedAgent = sdk.loadAgent(reloadedAgentId)
    print(f"✅ Reloaded from blockchain")
    
    reloadedState = {
        'name': reloadedAgent.name,
        'description': reloadedAgent.description,
        'image': reloadedAgent.image,
        'walletAddress': reloadedAgent.walletAddress,
        'walletChainId': reloadedAgent.walletChainId,
        'active': reloadedAgent.active,
        'x402support': reloadedAgent.x402support,
        'mcpEndpoint': reloadedAgent.mcpEndpoint,
        'a2aEndpoint': reloadedAgent.a2aEndpoint,
        'ensEndpoint': reloadedAgent.ensEndpoint,
        'metadata': reloadedAgent.metadata.copy()
    }
    
    expectedState = updatedState
    # Wallet was set on-chain to the second wallet address (verified)
    expectedState['walletAddress'] = second_wallet_address
    expectedState['walletChainId'] = sdk.chainId
    
    allMatch = True
    for field, expected in expectedState.items():
        actual = reloadedState.get(field)
        
        # Handle type casting for metadata fields
        if field == 'metadata' and isinstance(actual, dict) and isinstance(expected, dict):
            normalized_actual = {}
            for k, v in actual.items():
                if k in expected:
                    expected_val = expected[k]
                    if isinstance(expected_val, int):
                        try:
                            normalized_actual[k] = int(v) if isinstance(v, str) else v
                        except (ValueError, TypeError):
                            normalized_actual[k] = v
                    elif isinstance(expected_val, float):
                        try:
                            normalized_actual[k] = float(v) if isinstance(v, str) else v
                        except (ValueError, TypeError):
                            normalized_actual[k] = v
                    else:
                        normalized_actual[k] = v
                else:
                    normalized_actual[k] = v
            actual = normalized_actual
        
        if actual == expected:
            print(f"✅ {field}: {actual}")
        else:
            print(f"❌ {field}: expected={expected}, got={actual}")
            allMatch = False
    
    if allMatch:
        print("\n✅ ALL CHECKS PASSED")
    else:
        print("\n❌ SOME CHECKS FAILED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
