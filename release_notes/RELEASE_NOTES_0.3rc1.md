# Release Notes - Agent0 Python SDK v0.3rc1

## 🎉 Multi-Chain Support

This release introduces comprehensive multi-chain support, allowing you to query and interact with agents across multiple blockchain networks simultaneously.

## What's New

### Multi-Chain Functionality

The SDK now supports querying agents across multiple chains in a single operation. This enables:
- **Cross-chain agent discovery**: Find agents deployed on different networks
- **Unified search interface**: Search across all supported chains with one call
- **Chain-agnostic agent IDs**: Use `chainId:agentId` format to specify which chain an agent is on

### Supported Networks

The SDK currently supports the following testnet networks:

- **Ethereum Sepolia** (Chain ID: `11155111`)
- **Base Sepolia** (Chain ID: `84532`)
- **Polygon Amoy** (Chain ID: `80002`)

Each network has its own subgraph endpoint and contract addresses configured automatically.

## Default Chain

When you initialize the SDK, you specify a **default chain**:

```python
from agent0_sdk import SDK

# Initialize SDK with Ethereum Sepolia as default chain
sdk = SDK(
    chainId=11155111,  # This becomes the default chain
    rpcUrl="https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY"
)
```

The default chain is used when:
1. You provide an `agentId` without a `chainId` prefix (e.g., `"1234"` instead of `"11155111:1234"`)
2. You call functions without specifying a chain parameter
3. The SDK needs to determine which chain to query for operations

**Example:**
```python
# Uses default chain (11155111)
agent = sdk.getAgent("1234")  # Equivalent to "11155111:1234"

# Explicitly specify a different chain
agent = sdk.getAgent("84532:1234")  # Base Sepolia
```

## Multi-Chain Functions

The following functions now support multi-chain operations:

### 1. `getAgent(agentId)`

Retrieves a single agent by ID, supporting both default chain and explicit chain specification.

**Usage:**
```python
# Using default chain
agent = sdk.getAgent("1234")  # Uses SDK's default chain

# Explicitly specify chain
agent = sdk.getAgent("84532:1234")  # Base Sepolia
agent = sdk.getAgent("80002:5678")  # Polygon Amoy
```

**Agent ID Format:**
- `"agentId"` - Uses SDK's default chain
- `"chainId:agentId"` - Uses the specified chain (e.g., `"84532:1234"`)

### 2. `searchFeedback(agentId, ...)`

Searches for feedback entries for a specific agent, supporting both default chain and explicit chain specification.

**Usage:**
```python
# Using default chain
feedbacks = sdk.searchFeedback("1234", first=10)

# Explicitly specify chain
feedbacks = sdk.searchFeedback("84532:1234", first=10)
```

**Parameters:**
- `agentId`: Agent ID in format `"agentId"` (default chain) or `"chainId:agentId"` (specific chain)
- All other parameters work the same as before

### 3. `searchAgentsByReputation(..., chains=None)`

Searches for agents filtered by reputation criteria across one or more chains.

**Usage:**
```python
# Single chain (uses SDK's default chain)
result = sdk.searchAgentsByReputation(
    minAverageScore=80,
    page_size=20
)

# Single specific chain
result = sdk.searchAgentsByReputation(
    minAverageScore=80,
    page_size=20,
    chains=[84532]  # Base Sepolia
)

# Multiple chains
result = sdk.searchAgentsByReputation(
    minAverageScore=80,
    page_size=20,
    chains=[11155111, 84532]  # ETH Sepolia and Base Sepolia
)

# All supported chains
result = sdk.searchAgentsByReputation(
    minAverageScore=80,
    page_size=20,
    chains="all"  # Searches all configured chains
)
```

**Parameters:**
- `chains`: 
  - `None` (default) - Uses SDK's default chain
  - `[chainId1, chainId2, ...]` - List of specific chain IDs to search
  - `"all"` - Searches all configured chains in parallel

**Response:**
```python
{
    "items": [AgentSummary, ...],  # Agents from all requested chains
    "nextCursor": "20",  # Pagination cursor
    "meta": {
        "chains": [11155111, 84532],  # Chains that were queried
        "successfulChains": [11155111, 84532],  # Chains that returned results
        "failedChains": [],  # Chains that failed (if any)
        "totalResults": 15,  # Total agents found
        "timing": {"totalMs": 234}  # Query time in milliseconds
    }
}
```

### 4. `getReputationSummary(agentId)`

Gets reputation summary for an agent, supporting both default chain and explicit chain specification.

**Usage:**
```python
# Using default chain
summary = sdk.getReputationSummary("1234")

# Explicitly specify chain
summary = sdk.getReputationSummary("84532:1234")
```

**Response:**
```python
{
    "agentId": "84532:1234",
    "count": 5,
    "averageScore": 4.2,
    "filters": {...}
}
```

### 5. `searchAgents(..., params.chains=None)`

Searches for agents with various filters, supporting multi-chain search.

**Usage:**
```python
from agent0_sdk import SearchParams

params = SearchParams()
params.chains = [11155111, 84532]  # Search multiple chains
# Or
params.chains = "all"  # Search all chains

result = sdk.searchAgents(params, page_size=50)
```

**Note:** This function already supported multi-chain via `params.chains` in previous versions.

## Migration Guide

### From v0.2.2 to v0.3rc1

**No breaking changes!** All existing code continues to work without modification.

**New capabilities:**
1. Use `chainId:agentId` format for any function that accepts `agentId`
2. Use `chains` parameter in `searchAgentsByReputation()` to search multiple chains
3. Use `chains="all"` to search all configured chains

**Example migration:**
```python
# Before (v0.2.2) - only default chain
agent = sdk.getAgent("1234")
result = sdk.searchAgentsByReputation(minAverageScore=80)

# After (v0.3rc1) - multi-chain support
agent = sdk.getAgent("84532:1234")  # Explicit chain
result = sdk.searchAgentsByReputation(
    minAverageScore=80,
    chains=[11155111, 84532]  # Multiple chains
)
```

## Performance Considerations

- **Parallel queries**: When searching multiple chains, queries are executed in parallel using `asyncio`
- **Timeout**: Individual subgraph requests have a 10-second timeout
- **Aggregation**: Results from multiple chains are aggregated, sorted, and paginated client-side
- **Caching**: Subgraph clients are cached per chain to avoid redundant initialization

## Bug Fixes

- Fixed variable name collision in `searchAgentsByReputation()` multi-chain path that caused incorrect parameter passing
- Fixed `totalFeedback` type conversion issue (BigInt from GraphQL now properly converted to int)
- Added `totalFeedback_gt: 0` filter to reputation search to only return agents with feedback

## Technical Details

### Agent ID Format

The SDK supports two agent ID formats:

1. **Agent ID only**: `"1234"`
   - Uses SDK's default chain
   - Automatically constructs `"{defaultChainId}:1234"` for subgraph queries

2. **Chain ID prefix**: `"84532:1234"`
   - Explicitly specifies the chain
   - Format: `"{chainId}:{agentId}"`

### Chain Resolution

When you provide an `agentId` without a `chainId` prefix:
1. The SDK uses its default `chainId` (from initialization)
2. Constructs the full `"{defaultChainId}:{agentId}"` format
3. Queries the appropriate subgraph for that chain

### Subgraph Client Management

- Each chain has its own subgraph client instance
- Clients are cached and reused for efficiency
- Subgraph URLs are resolved in this order:
  1. Chain-specific override (from `subgraphOverrides` in SDK constructor)
  2. Default URL from `DEFAULT_SUBGRAPH_URLS`
  3. Environment variable `SUBGRAPH_URL_{chainId}`

## Examples

### Example 1: Get agent from specific chain
```python
from agent0_sdk import SDK

sdk = SDK(chainId=11155111, rpcUrl="...")

# Get agent from Base Sepolia (different from default)
agent = sdk.getAgent("84532:557")
print(f"Agent: {agent.name} on chain {agent.chainId}")
```

### Example 2: Search reputation across all chains
```python
result = sdk.searchAgentsByReputation(
    minAverageScore=80,
    page_size=50,
    chains="all"
)

print(f"Found {len(result['items'])} agents across all chains")
for agent in result['items']:
    print(f"  {agent.name} (Chain: {agent.chainId}, Score: {agent.extras.get('averageScore')})")
```

### Example 3: Get feedback from multiple chains
```python
# Get feedback from Base Sepolia agent
feedbacks = sdk.searchFeedback("84532:557", first=10)

for fb in feedbacks:
    print(f"Score: {fb.score}, Tags: {fb.tags}")
```

### Example 4: Multi-chain agent search
```python
from agent0_sdk import SearchParams

params = SearchParams()
params.chains = [11155111, 84532, 80002]  # All three chains
params.active = True

result = sdk.searchAgents(params, page_size=100)
print(f"Found {len(result['items'])} active agents across 3 chains")
```

## Installation

```bash
pip install agent0-sdk==0.3rc1
```

## What's Next

This is a release candidate for v0.3.0. We're gathering feedback on the multi-chain API before finalizing the stable release.

---

DOCS yet to be updated

