"""
Test Endpoint Crawler with Real Public MCP and A2A Servers
Tests against actual public servers provided by the user.
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent0_sdk.core.endpoint_crawler import EndpointCrawler
import json

RUN_LIVE_TESTS = os.getenv("RUN_LIVE_TESTS", "0") != "0"

def main():
    print("🧪 Testing Endpoint Crawler with Real Public Servers")
    print("=" * 70)
    
    crawler = EndpointCrawler(timeout=10)  # Longer timeout for real servers
    
    # Real public endpoints
    test_cases = [
        {
            "type": "A2A",
            "endpoint": "https://hello-world-gxfr.onrender.com",
            "description": "Real A2A Hello World Server"
        },
        {
            "type": "MCP",
            "endpoint": "https://mcp.atlassian.com/v1/forge/mcp",
            "description": "Atlassian MCP Server (requires authentication, will fail gracefully)"
        }
    ]
    
    successful_tests = []
    failed_tests = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📍 Test {i}: {test_case['type']} Endpoint")
        print("-" * 70)
        print(f"URL: {test_case['endpoint']}")
        print(f"Description: {test_case['description']}")
        print()
        
        if test_case['type'] == 'A2A':
            capabilities = crawler.fetch_a2a_capabilities(test_case['endpoint'])
            if capabilities:
                print("✅ SUCCESS! Fetched A2A capabilities:")
                print(json.dumps(capabilities, indent=2))
                successful_tests.append(test_case)
            else:
                print("❌ Failed to fetch A2A capabilities")
                failed_tests.append(test_case)
        
        elif test_case['type'] == 'MCP':
            capabilities = crawler.fetch_mcp_capabilities(test_case['endpoint'])
            if capabilities:
                print("✅ SUCCESS! Fetched MCP capabilities:")
                print(json.dumps(capabilities, indent=2))
                successful_tests.append(test_case)
            else:
                print("❌ Failed to fetch MCP capabilities")
                failed_tests.append(test_case)
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 Summary")
    print("-" * 70)
    print(f"✅ Successful: {len(successful_tests)}")
    print(f"❌ Failed: {len(failed_tests)}")
    
    if successful_tests:
        print("\n✅ Successfully tested endpoints:")
        for test in successful_tests:
            print(f"   - {test['type']}: {test['endpoint']}")
    
    if failed_tests:
        print("\n⚠️  Failed endpoints:")
        for test in failed_tests:
            print(f"   - {test['type']}: {test['endpoint']}")
    
    print("\n" + "=" * 70)
    if successful_tests:
        print("🎉 Endpoint crawler is working with real public servers!")
    else:
        print("⚠️  No capabilities fetched. Check endpoints or network connection.")
    print("=" * 70)

if __name__ == "__main__":
    main()


@pytest.mark.integration
def test_real_public_servers_live():
    if not RUN_LIVE_TESTS:
        pytest.skip("Set RUN_LIVE_TESTS=1 to enable live integration tests")
    main()

