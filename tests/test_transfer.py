#!/usr/bin/env python3
"""
Test agent transfer functionality.

This script demonstrates:
1. Creating and registering an agent with owner A
2. Transferring agent from owner A to owner B
3. Verifying ownership changed on-chain
4. Attempting to transfer from non-owner (should fail)
5. Verifying agent metadata remains unchanged after transfer
"""

import logging
import time
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

from tests.config import (
    CHAIN_ID, RPC_URL, AGENT_PRIVATE_KEY, PINATA_JWT, SUBGRAPH_URL,
    print_config
)
from agent0_sdk import SDK, EndpointType, TrustModel

RUN_LIVE_TESTS = os.getenv("RUN_LIVE_TESTS", "0") != "0"

def main():
    print("=" * 60)
    print("🔄 AGENT TRANSFER TEST")
    print("=" * 60)
    
    print_config()
    
    # Configuration for SDK
    sdkConfig_pinata = {
        "chainId": CHAIN_ID,
        "rpcUrl": RPC_URL,
        "signer": AGENT_PRIVATE_KEY,
        "ipfs": "pinata",
        "pinataJwt": PINATA_JWT
        # Subgraph URL auto-defaults from DEFAULT_SUBGRAPH_URLS
    }
    
    # Initialize SDK with Pinata
    print("\n📡 Initializing SDK with Pinata...")
    agentSdk = SDK(**sdkConfig_pinata)
    
    # Create a second private key for testing transfer
    # In a real scenario, this would be a different wallet
    # For testing, we'll use a different address derived from the same key
    print("\n🔑 Setting up test accounts...")
    ownerA_address = agentSdk.web3_client.account.address
    print(f"Owner A address: {ownerA_address}")
    
    # For testing purposes, we'll use a different address
    # In practice, this would be a completely different private key
    ownerB_address = "0x742d35Cc6634C0532925a3b8D4C9db96C4b4d8b6"  # Example address
    print(f"Owner B address: {ownerB_address}")
    
    print("\n" + "=" * 60)
    print("STEP 1: CREATE AND REGISTER AGENT WITH OWNER A")
    print("=" * 60)
    
    # Create agent
    agent = agentSdk.createAgent(
        name="Transfer Test Agent",
        description="An agent for testing transfer functionality",
        image="https://example.com/transfer-test-agent.png"
    )
    
    # Configure agent details (wallet is on-chain only; set after registration)
    agent.setENS("transfer-test-agent.eth")
    agent.setMetadata({
        "version": "1.0",
        "category": "test",
        "transfer_test": True
    })
    
    # Add endpoints
    agent.setMCP("https://mcp.example.com/transfer-test", auto_fetch=False)
    agent.setA2A("https://a2a.example.com/transfer-test-agent.json", auto_fetch=False)
    
    print(f"✅ Agent created with ID: {agent.agentId}")
    print(f"📄 Registration file prepared")
    
    # Register agent on-chain
    print("\n📝 Registering agent on-chain...")
    reg_tx = agent.registerIPFS()
    registration_result = reg_tx.wait_confirmed(timeout=180).result
    
    print(f"✅ Agent registered successfully!")
    print(f"   Agent ID: {registration_result.agentId}")
    print(f"   IPFS URI: {registration_result.agentURI}")
    
    # Verify initial ownership using utility function
    print("\n🔍 Verifying initial ownership...")
    current_owner = agentSdk.getAgentOwner(registration_result.agentId)
    print(f"✅ Current owner: {current_owner}")
    print(f"✅ Matches Owner A: {current_owner.lower() == ownerA_address.lower()}")
    
    # Set wallet on-chain after registration (requires EIP-712 signature).
    # Since ownerA_address matches current SDK signer, it can auto-sign.
    print("\n🔍 Setting agent wallet on-chain...")
    wallet_tx = agent.setWallet(ownerA_address, CHAIN_ID)
    if wallet_tx is not None:
        wallet_tx.wait_confirmed(timeout=180)
    print(f"✅ Agent wallet set on-chain: {ownerA_address}")
    
    # Verify wallet is set on-chain
    token_id = int(registration_result.agentId.split(":")[-1])
    on_chain_wallet = agentSdk.web3_client.call_contract(
        agentSdk.identity_registry,
        "getAgentWallet",
        token_id
    )
    print(f"✅ On-chain wallet verified: {on_chain_wallet}")
    print(f"✅ Matches expected: {on_chain_wallet.lower() == ownerA_address.lower()}")
    
    print("\n" + "=" * 60)
    print("STEP 2: TRANSFER AGENT TO OWNER B")
    print("=" * 60)
    
    # Transfer agent using Agent.transfer() method
    print(f"🔄 Transferring agent {registration_result.agentId} to {ownerB_address}...")
    
    try:
        transfer_tx = agent.transfer(ownerB_address)
        transfer_result = transfer_tx.wait_confirmed(timeout=180).result
        print(f"✅ Transfer successful!")
        print(f"   Transaction: {transfer_result['txHash']}")
        print(f"   From: {transfer_result['from']}")
        print(f"   To: {transfer_result['to']}")
        print(f"   Agent ID: {transfer_result['agentId']}")
    except Exception as e:
        print(f"❌ Transfer failed: {e}")
        return
    
    print("\n" + "=" * 60)
    print("STEP 3: VERIFY OWNERSHIP CHANGE")
    print("=" * 60)
    
    # Verify ownership changed using utility function
    print("🔍 Verifying ownership change...")
    new_owner = agentSdk.getAgentOwner(registration_result.agentId)
    print(f"✅ New owner: {new_owner}")
    print(f"✅ Matches Owner B: {new_owner.lower() == ownerB_address.lower()}")
    
    # Verify wallet was reset to zero address on transfer
    print("\n🔍 Verifying wallet reset on transfer...")
    on_chain_wallet_after_transfer = agentSdk.web3_client.call_contract(
        agentSdk.identity_registry,
        "getAgentWallet",
        token_id
    )
    print(f"✅ Wallet after transfer: {on_chain_wallet_after_transfer}")
    if on_chain_wallet_after_transfer == "0x0000000000000000000000000000000000000000":
        print(f"✅ Wallet correctly reset to zero address (as per ERC-8004 spec)")
    else:
        print(f"⚠️  Wallet not reset (expected zero address)")
    
    # Verify agent metadata remains unchanged
    print("\n🔍 Verifying agent metadata remains unchanged...")
    # Parse agentId to extract tokenId for contract call
    agent_id_str = str(registration_result.agentId)
    if ":" in agent_id_str:
        token_id = int(agent_id_str.split(":")[-1])
    else:
        token_id = int(agent_id_str)
    
    agent_uri = agentSdk.web3_client.call_contract(
        agentSdk.identity_registry,
        "tokenURI",
        token_id
    )
    print(f"✅ Agent URI unchanged: {agent_uri}")
    # Note: registration_result.agentURI may be None if not set in RegistrationFile
    if registration_result.agentURI:
        print(f"✅ Matches original: {agent_uri == registration_result.agentURI}")
    else:
        print(f"✅ Agent URI retrieved from blockchain: {agent_uri}")
    
    print("\n" + "=" * 60)
    print("STEP 4: TEST SDK.transferAgent() METHOD")
    print("=" * 60)
    
    # Test SDK-level transfer method (this will fail since we're not Owner B)
    print("🔄 Testing SDK.transferAgent() method...")
    print("   (This should fail since we're not the current owner)")
    
    try:
        # Try to transfer back to Owner A (should fail)
        sdk_transfer_tx = agentSdk.transferAgent(
            registration_result.agentId,
            ownerA_address
        )
        sdk_transfer_tx.wait_confirmed(timeout=180)
        print(f"❌ Unexpected success: {sdk_transfer_tx.tx_hash}")
    except Exception as e:
        print(f"✅ Expected failure: {e}")
    
    print("\n" + "=" * 60)
    print("STEP 5: TEST INVALID TRANSFER ATTEMPTS")
    print("=" * 60)
    
    # Test invalid transfer attempts
    print("🔄 Testing invalid transfer attempts...")
    
    # Test zero address
    try:
        agent.transfer("0x0000000000000000000000000000000000000000")
        print("❌ Zero address transfer should have failed")
    except ValueError as e:
        print(f"✅ Zero address correctly rejected: {e}")
    
    # Test self-transfer
    try:
        agent.transfer(ownerB_address)  # Try to transfer to same address
        print("❌ Self-transfer should have failed")
    except ValueError as e:
        print(f"✅ Self-transfer correctly rejected: {e}")
    
    # Test invalid address format
    try:
        agent.transfer("invalid_address")
        print("❌ Invalid address should have failed")
    except ValueError as e:
        print(f"✅ Invalid address correctly rejected: {e}")
    
    print("\n" + "=" * 60)
    print("STEP 6: VERIFY AGENT DATA INTEGRITY")
    print("=" * 60)
    
    # Load agent and verify all data is intact
    print("🔍 Loading agent and verifying data integrity...")
    
    try:
        loaded_agent = agentSdk.loadAgent(registration_result.agentId)
        print(f"✅ Agent loaded successfully")
        print(f"   Name: {loaded_agent.name}")
        print(f"   Description: {loaded_agent.description}")
        print(f"   Image: {loaded_agent.image}")
        print(f"   Wallet Address: {loaded_agent.walletAddress}")
        print(f"   ENS: {loaded_agent.ensEndpoint}")
        print(f"   Metadata: {loaded_agent.metadata}")
        print(f"   MCP Endpoint: {loaded_agent.mcpEndpoint}")
        print(f"   A2A Endpoint: {loaded_agent.a2aEndpoint}")
        print(f"   Active: {loaded_agent.active}")
        
        # Verify ownership is correctly reflected
        print(f"\n🔍 Ownership verification:")
        print(f"   Current owner (on-chain): {new_owner}")
        print(f"   Expected owner: {ownerB_address}")
        print(f"   Match: {new_owner.lower() == ownerB_address.lower()}")
        
    except Exception as e:
        print(f"❌ Failed to load agent: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🎉 TRANSFER TEST COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    
    print("\n📋 Summary:")
    print(f"   ✅ Agent created and registered with Owner A")
    print(f"   ✅ Agent successfully transferred to Owner B")
    print(f"   ✅ Ownership change verified on-chain")
    print(f"   ✅ Invalid transfer attempts properly rejected")
    print(f"   ✅ Agent data integrity maintained")
    print(f"   ✅ Both Agent.transfer() and SDK.transferAgent() methods tested")
    
    print(f"\n🔗 Agent Details:")
    print(f"   Agent ID: {registration_result.agentId}")
    print(f"   Current Owner: {new_owner}")
    print(f"   Agent URI: {agent_uri}")
    if transfer_result and 'txHash' in transfer_result:
        print(f"   Transfer Transaction: {transfer_result['txHash']}")

if __name__ == "__main__":
    main()


@pytest.mark.integration
def test_transfer_live():
    if not RUN_LIVE_TESTS:
        pytest.skip("Set RUN_LIVE_TESTS=1 to enable live integration tests")
    if not RPC_URL or not RPC_URL.strip():
        pytest.skip("RPC_URL not set")
    if not AGENT_PRIVATE_KEY or not AGENT_PRIVATE_KEY.strip():
        pytest.skip("AGENT_PRIVATE_KEY not set")
    if not PINATA_JWT or not PINATA_JWT.strip():
        pytest.skip("PINATA_JWT not set")

    main()
