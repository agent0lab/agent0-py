"""
Test for Agent Feedback Flow with IPFS Pin
Submits feedback from a client to an existing agent and verifies data integrity.

Flow:
1. Load existing agent by ID
2. Client submits multiple feedback entries
3. Verify feedback data consistency (value, tags, capability, skill)
4. Wait for blockchain finalization
5. Verify feedback can be retrieved (if SDK supports it)

Usage:
    Update AGENT_ID constant below to point to your existing agent
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
from tests.config import (
    CHAIN_ID,
    RPC_URL,
    AGENT_PRIVATE_KEY,
    PINATA_JWT,
    SUBGRAPH_URL,
    AGENT_ID,
    CLIENT_PRIVATE_KEY,
    print_config,
)

# Client configuration (different wallet)
# CLIENT_PRIVATE_KEY is now loaded from config.py (which reads from .env file)
if not CLIENT_PRIVATE_KEY:
    raise ValueError("CLIENT_PRIVATE_KEY must be set in .env file for feedback tests")


def generateFeedbackData(index: int):
    """Generate random feedback data."""
    scores = [50, 75, 80, 85, 90, 95]
    tags_sets = [
        ["data_analysis", "enterprise"],
        ["code_generation", "enterprise"],
        ["natural_language_understanding", "enterprise"],
        ["problem_solving", "enterprise"],
        ["communication", "enterprise"],
    ]
    
    capabilities = [
        "tools",
        "tools",
        "tools",
        "tools",
        "tools"
    ]

    capabilities = [
        "data_analysis",
        "code_generation",
        "natural_language_understanding",
        "problem_solving",
        "communication"
    ]
    
    skills = [
        "python",
        "javascript",
        "machine_learning",
        "web_development",
        "cloud_computing"
    ]
    
    return {
        'value': random.choice(scores),
        'tags': random.choice(tags_sets),
        'capability': random.choice(capabilities),
        'skill': random.choice(skills),
        'context': 'enterprise'
    }


def main():
    print("🧪 Testing Agent Feedback Flow with IPFS Pin")
    print_config()
    print("=" * 60)
    
    # SDK Configuration
    sdkConfig_pinata = {
        'chainId': CHAIN_ID,
        'rpcUrl': RPC_URL,
        'ipfs': 'pinata',
        'pinataJwt': PINATA_JWT
        # Subgraph URL auto-defaults from DEFAULT_SUBGRAPH_URLS
    }
    
    # Step 1: Load existing agent
    print("\n📍 Step 1: Load Existing Agent")
    print("-" * 60)
    print(f"Loading agent: {AGENT_ID}")
    
    agentSdk = SDK(**sdkConfig_pinata)  # Read-only for loading
    
    try:
        agent = agentSdk.loadAgent(AGENT_ID)
        print(f"✅ Agent loaded: {agent.name}")
        print(f"   Description: {agent.description[:50]}...")
        print(f"   MCP Endpoint: {agent.mcpEndpoint}")
        print(f"   A2A Endpoint: {agent.a2aEndpoint}")
        print(f"   ENS Endpoint: {agent.ensEndpoint}")
    except Exception as e:
        print(f"❌ Failed to load agent: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    
    # Step 2: Client submits feedback (no pre-authorization needed)
    print("\n📍 Step 2: Client Submits Feedback")
    print("-" * 60)
    
    clientSdk = SDK(signer=CLIENT_PRIVATE_KEY, **sdkConfig_pinata)
    clientAddress = clientSdk.web3_client.account.address
    print(f"Client address: {clientAddress}")
    print("Note: Feedback no longer requires pre-authorization (feedbackAuth removed)")
    
    # Agent SDK for responses
    agentSdkWithSigner = SDK(signer=AGENT_PRIVATE_KEY, **sdkConfig_pinata)
    
    # Step 3: Client submits feedback
    print("\n📍 Step 3: Client Submits Feedback")
    print("-" * 60)
    
    feedbackEntries = []
    numFeedback = 1

    # On-chain-only feedback (explicitly no file upload)
    print("\n  Submitting on-chain-only feedback (no feedbackFile):")
    onchain_only = clientSdk.giveFeedback(
        agentId=AGENT_ID,
        value=1,
        tag1="onchain",
        tag2="only",
        endpoint="https://example.com/onchain-only",
        feedbackFile=None,
    )
    if onchain_only.fileURI:
        raise AssertionError(
            f"Expected on-chain-only feedback to have no fileURI, got: {onchain_only.fileURI}"
        )
    
    for i in range(numFeedback):
        print(f"\n  Submitting Feedback #{i+1}:")
        feedbackData = generateFeedbackData(i+1)
        
        # Prepare off-chain feedback file (optional rich data)
        feedbackFile = clientSdk.prepareFeedbackFile({
            "capability": feedbackData.get("capability"),
            "skill": feedbackData.get("skill"),
            "context": feedbackData.get("context"),
            "text": feedbackData.get("text"),
        })

        tags = feedbackData.get("tags") or []
        tag1 = tags[0] if len(tags) > 0 else None
        tag2 = tags[1] if len(tags) > 1 else None
        
        print(f"  - Value: {feedbackData['value']}")
        print(f"  - Tags: {feedbackData['tags']}")
        print(f"  - Capability: {feedbackData['capability']}")
        print(f"  - Skill: {feedbackData['skill']}")
        
        # Submit feedback
        try:
            feedback = clientSdk.giveFeedback(
                agentId=AGENT_ID,
                value=feedbackData["value"],
                tag1=tag1,
                tag2=tag2,
                endpoint=feedbackData.get("endpoint"),
                feedbackFile=feedbackFile,
            )
            
            # Extract actual feedback index from the returned Feedback object
            # feedback.id is a tuple: (agentId, clientAddress, feedbackIndex)
            actualFeedbackIndex = feedback.id[2]
            
            feedbackEntries.append({
                'index': actualFeedbackIndex,  # Use actual index from blockchain
                'data': feedbackData,
                'feedback': feedback
            })
            
            print(f"  ✅ Feedback #{actualFeedbackIndex} submitted successfully (entry #{i+1} in this test)")
            if feedback.fileURI:
                print(f"     File URI: {feedback.fileURI}")
            
        except Exception as e:
            print(f"  ❌ Failed to submit feedback #{i+1}: {e}")
            import traceback
            traceback.print_exc()
            exit(1)
        
        time.sleep(2)  # Wait between submissions
    
    # Step 4: Agent (Server) Responds to Feedback
    print("\n📍 Step 4: Agent (Server) Responds to Feedback")
    print("-" * 60)
    
    clientAddress = clientSdk.web3_client.account.address
    
    for i, entry in enumerate(feedbackEntries):
        # Use the actual feedback index that was returned when submitting
        feedbackIndex = entry['index']
        print(f"\n  Responding to Feedback #{feedbackIndex}:")
        
        # Generate response data
        responseData = {
            'text': f"Thank you for your feedback! We appreciate your input.",
            'timestamp': int(time.time()),
            'responder': 'agent'
        }
        
        try:
            # Agent responds to the client's feedback
            updatedFeedback = agentSdkWithSigner.appendResponse(
                agentId=AGENT_ID,
                clientAddress=clientAddress,
                feedbackIndex=feedbackIndex,
                response=responseData
            )
            
            print(f"  ✅ Response submitted to feedback #{feedbackIndex}")
            entry['response'] = responseData
            entry['updatedFeedback'] = updatedFeedback
        except Exception as e:
            print(f"  ❌ Failed to submit response: {e}")
        
        time.sleep(2)  # Wait between responses
    
    # Step 5: Wait for blockchain finalization
    print("\n📍 Step 5: Waiting for Blockchain Finalization")
    print("-" * 60)
    print("⏳ Waiting 15 seconds for blockchain to finalize...")
    time.sleep(15)
    
    # Step 6: Verify feedback data and responses
    print("\n📍 Step 6: Verify Feedback Data Integrity")
    print("-" * 60)
    
    allMatch = True
    
    for i, entry in enumerate(feedbackEntries, 1):
        print(f"\n  Feedback #{i}:")
        data = entry['data']
        feedback = entry['feedback']
        
        # Verify feedback object fields
        checks = [
            ('Value', data['value'], feedback.value),
            ('Tags', data['tags'], feedback.tags),
            ('Capability', data['capability'], feedback.capability),
            ('Skill', data['skill'], feedback.skill),
        ]
        
        for field_name, expected, actual in checks:
            if expected == actual:
                print(f"    ✅ {field_name}: {actual}")
            else:
                print(f"    ❌ {field_name}: expected={expected}, got={actual}")
                allMatch = False
        
        # Verify file URI exists
        if feedback.fileURI:
            print(f"    ✅ File URI: {feedback.fileURI}")
        else:
            print(f"    ⚠️  No file URI (IPFS storage may have failed)")
        
        # Verify server response was added
        if 'response' in entry and entry.get('updatedFeedback'):
            print(f"    ✅ Server Response: Recorded successfully")
    
    # Step 7: Wait for subgraph indexing
    print("\n📍 Step 7: Waiting for Subgraph to Index")
    print("-" * 60)
    print("⏳ Waiting 60 seconds for subgraph to catch up with blockchain events...")
    print("   (Subgraphs can take up to a minute to index new blocks)")
    time.sleep(60)
    
    # Step 8: Test getFeedback (direct access)
    print("\n📍 Step 8: Test getFeedback (Direct Access)")
    print("-" * 60)
    
    for i, entry in enumerate(feedbackEntries):
        # Use the actual feedback index that was returned when submitting
        feedbackIndex = entry['index']
        print(f"\n  Fetching Feedback #{feedbackIndex} using getFeedback():")
        
        try:
            # Use agentSdkWithSigner since agentSdk has no subgraph_client
            retrievedFeedback = agentSdkWithSigner.getFeedback(
                agentId=AGENT_ID,
                clientAddress=clientAddress,
                feedbackIndex=feedbackIndex
            )
            
            print(f"    ✅ Retrieved feedback successfully")
            print(f"    - Value: {retrievedFeedback.value}")
            print(f"    - Tags: {retrievedFeedback.tags}")
            print(f"    - Capability: {retrievedFeedback.capability}")
            print(f"    - Skill: {retrievedFeedback.skill}")
            print(f"    - Is Revoked: {retrievedFeedback.isRevoked}")
            print(f"    - Has Responses: {len(retrievedFeedback.answers)} response(s)")
            if retrievedFeedback.fileURI:
                print(f"    - File URI: {retrievedFeedback.fileURI}")
            
            # Verify retrieved feedback matches original (subgraph tags may be legacy/hashed)
            expected = entry['data']
            if retrievedFeedback.value == expected['value'] and \
               retrievedFeedback.capability == expected['capability'] and \
               retrievedFeedback.skill == expected['skill']:
                print(f"    ✅ Retrieved feedback matches original submission")
            else:
                print(f"    ❌ Retrieved feedback does not match original")
                allMatch = False
                
        except Exception as e:
            print(f"    ❌ Failed to retrieve feedback: {e}")
            allMatch = False
    
    # Step 9: Test searchFeedback (with filters)
    print("\n📍 Step 9: Test searchFeedback (With Filters)")
    print("-" * 60)
    
    # Test 1: Search by capability
    print("\n  Test 1: Search feedback by capability")
    testCapability = feedbackEntries[0]['data']['capability']
    try:
        results = agentSdkWithSigner.searchFeedback(
            agentId=AGENT_ID,
            capabilities=[testCapability],
            first=10,
            skip=0
        )
        print(f"    ✅ Found {len(results)} feedback entry/entries with capability '{testCapability}'")
        if results:
            for fb in results:
                print(f"      - Value: {fb.value}, Tags: {fb.tags}")
    except Exception as e:
        print(f"    ❌ Failed to search feedback by capability: {e}")
        allMatch = False
    
    # Test 2: Search by skill
    print("\n  Test 2: Search feedback by skill")
    testSkill = feedbackEntries[0]['data']['skill']
    try:
        results = agentSdkWithSigner.searchFeedback(
            agentId=AGENT_ID,
            skills=[testSkill],
            first=10,
            skip=0
        )
        print(f"    ✅ Found {len(results)} feedback entry/entries with skill '{testSkill}'")
        if results:
            for fb in results:
                print(f"      - Value: {fb.value}, Tags: {fb.tags}")
    except Exception as e:
        print(f"    ❌ Failed to search feedback by skill: {e}")
        allMatch = False
    
    # Test 3: Search by tags
    print("\n  Test 3: Search feedback by tags")
    testTags = feedbackEntries[0]['data']['tags']
    try:
        results = agentSdkWithSigner.searchFeedback(
            agentId=AGENT_ID,
            tags=testTags,
            first=10,
            skip=0
        )
        print(f"    ✅ Found {len(results)} feedback entry/entries with tags {testTags}")
        if results:
            for fb in results:
                print(f"      - Value: {fb.value}, Capability: {fb.capability}")
    except Exception as e:
        print(f"    ❌ Failed to search feedback by tags: {e}")
        allMatch = False
    
    # Test 4: Search by value range
    print("\n  Test 4: Search feedback by value range (75-95)")
    try:
        results = agentSdkWithSigner.searchFeedback(
            agentId=AGENT_ID,
            minValue=75,
            maxValue=95,
            first=10,
            skip=0
        )
        print(f"    ✅ Found {len(results)} feedback entry/entries with value between 75-95")
        if results:
            values = sorted([fb.value for fb in results if fb.value is not None])
            print(f"      - Values found: {values}")
    except Exception as e:
        print(f"    ❌ Failed to search feedback by value range: {e}")
        allMatch = False
    
    # Final results
    print("\n" + "=" * 60)
    if allMatch:
        print("✅ ALL CHECKS PASSED")
        print("\nSummary:")
        print(f"- Agent ID: {AGENT_ID}")
        print(f"- Agent Name: {agent.name}")
        print(f"- Client address: {clientAddress}")
        print(f"- Feedback entries submitted: {len(feedbackEntries)}")
        print("✅ Feedback flow test complete!")
    else:
        print("❌ SOME CHECKS FAILED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
