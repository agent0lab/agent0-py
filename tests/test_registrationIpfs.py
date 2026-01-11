"""
Real Test for Agent Registration with IPFS Pin (using Pinata)
Creates an agent, updates it on-chain, deletes it, reloads it, and verifies data integrity.
"""

import logging
import time
import random
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
from config import CHAIN_ID, RPC_URL, AGENT_PRIVATE_KEY, CLIENT_PRIVATE_KEY, PINATA_JWT, print_config
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
        'walletAddress': f"0x{'a' * 40}",
        'walletChainId': random.choice([1, 11155111, 8453, 137, 42161]),  # Mainnet, Sepolia, Base, Polygon, Arbitrum
        'active': True,
        'x402support': False,
        'reputation': random.choice([True, False]),
        'cryptoEconomic': random.choice([True, False]),
        'teeAttestation': random.choice([True, False])
    }


def main():
    print("🧪 Testing Agent Registration with IPFS Pin")
    print_config()
    
    # SDK Configuration with Pinata IPFS
    sdkConfig = {
        'chainId': CHAIN_ID,
        'rpcUrl': RPC_URL,
        'ipfs': 'pinata',
        'pinataJwt': PINATA_JWT
    }
    
    sdk = SDK(signer=AGENT_PRIVATE_KEY, **sdkConfig)
    testData = generateRandomData()
    
    agent = sdk.createAgent(
        name=testData['name'],
        description=testData['description'],
        image=testData['image']
    )
    
    agent.setMCP(testData['mcpEndpoint'], testData['mcpVersion'])
    agent.setA2A(testData['a2aEndpoint'], testData['a2aVersion'])
    agent.setENS(testData['ensName'], testData['ensVersion'])
    # OASF skills/domains (validated against bundled taxonomy)
    agent.addSkill("advanced_reasoning_planning/strategic_planning", validate_oasf=True)
    agent.addDomain("finance_and_business/investment_services", validate_oasf=True)
    # Note: setAgentWallet() is on-chain only; do NOT call it before registration.
    agent.setActive(testData['active'])
    agent.setX402Support(testData['x402support'])
    agent.setTrust(
        reputation=testData['reputation'],
        cryptoEconomic=testData['cryptoEconomic'],
        teeAttestation=testData['teeAttestation']
    )
    
    print(f"\n✅ Created: {testData['name']}")
    
    agent.registerIPFS()
    agentId = agent.agentId
    print(f"✅ Registered: ID={agentId}")
    
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
    # Note: After registration, setAgentWallet() requires EIP-712 signature from the NEW wallet.
    # For testing, set the wallet to a second address derived from CLIENT_PRIVATE_KEY and let SDK sign.
    if not CLIENT_PRIVATE_KEY:
        raise ValueError("CLIENT_PRIVATE_KEY must be set in .env file for this test")

    second_wallet_account = Account.from_key(CLIENT_PRIVATE_KEY)
    second_wallet_address = second_wallet_account.address
    print(f"✅ Using second wallet address (from CLIENT_PRIVATE_KEY): {second_wallet_address}")
    agent.setAgentWallet(
        second_wallet_address,
        random.choice([1, 11155111, 8453, 137, 42161]),
        new_wallet_signer=CLIENT_PRIVATE_KEY,
    )
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
    
    agent.registerIPFS()
    print(f"✅ Updated & re-registered")
    
    # Capture updated state before deletion
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
    
    reloadedAgentId = agent.agentId
    del agent
    # Wait for blockchain transaction to be mined (Sepolia takes ~15 seconds)
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
    
    # Override expected values for fields that should match the updated state
    # Wallet was set on-chain to second_wallet_address (from CLIENT_PRIVATE_KEY)
    expectedState['walletAddress'] = second_wallet_address
    # When wallet is set on-chain, walletChainId will be the current chain (where the update happened)
    # This is different from the original registration file's chain ID
    expectedState['walletChainId'] = sdk.chainId  # Current chain where wallet was updated
    
    allMatch = True
    for field, expected in expectedState.items():
        actual = reloadedState.get(field)
        
        # Handle type casting for metadata fields (on-chain values are strings)
        if field == 'metadata' and isinstance(actual, dict) and isinstance(expected, dict):
            # Try to cast string values back to their original types
            normalized_actual = {}
            for k, v in actual.items():
                if k in expected:
                    expected_val = expected[k]
                    # If expected is int or float, try to cast
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

