# Release Notes — 1.4.0

This release improves dashboard ergonomics for feedback browsing and analytics.

## ERC-8004 Jan23 alignment (spec + ABIs)

This release also aligns the SDK with the updated ERC-8004 spec (`int128` reputation values, `services` registration files) and the Jan 23 2026 ABIs.

### Breaking changes

- **Off-chain feedback file format is now spec-only**
  - Feedback files written by the SDK include the ERC-8004 envelope fields and use the spec structure (nested `mcp` / `a2a` / `oasf` objects).
  - Legacy flat fields (e.g. `skill`, `task`, `context`, `capability`, `name`) are no longer supported/produced as a compatibility layer.

- **Agent wallet read API**
  - **Rename:** SDK method `Agent.getAgentWallet()` is now `Agent.getWallet()` (reads the verified wallet from chain).
  - Under the hood the contract call is `IdentityRegistry.getAgentWallet(agentId) -> address` (Jan 2026 ABI); the SDK treats the **zero address** as “unset”.

### Notable changes

- **Reputation value type**
  - Reputation registry values are now treated as `(value:int128, valueDecimals:uint8)` (previously `int256` in older ABIs/docs).
  - Value encoding clamps to the contract bound: `abs(value) <= 1e38`.

- **Registration file shape**
  - SDK-generated registration files now emit `services` (spec key). The SDK continues to accept legacy `endpoints` when reading.
  - Registration output uses `x402Support` (camelCase, spec key). The SDK continues to accept legacy `x402support` when reading.

- **Default trust model**
  - When creating a new agent, if no trust model is provided, the SDK defaults to `reputation`.

## Transactions (write calls): submitted-by-default lifecycle handles

**Breaking change:** write methods now return a **transaction handle** immediately after submission (tx hash available), instead of returning a “successful” result before the tx is mined.

This makes the lifecycle explicit:
- **submitted**: you have a tx hash (broadcast/accepted), but it may still revert
- **confirmed**: you explicitly wait for mining/confirmations and get the final result

```python
# submitted-by-default
tx = sdk.giveFeedback(agentId="11155111:123", value=85, tag1="quality", tag2="latency")
print(tx.tx_hash)

# explicitly await confirmation (defaults to 1 confirmation)
mined = tx.wait_confirmed(timeout=180, confirmations=1)
feedback = mined.result
receipt = mined.receipt
```

## Feedback search

### `SDK.searchFeedback()` now supports reviewer-only and multi-agent queries

**Non-breaking change:** `agentId` is now optional.

**New:** `agents: List[AgentId]` lets you search across multiple agents in one call.

This enables the “Feedback Given” use case (query **all feedback written by a wallet** across all agents) without needing to know which agents were reviewed.

```python
# Unchanged: search feedback for a specific agent
for_agent = sdk.searchFeedback(agentId="11155111:123")

# NEW: search feedback given by a reviewer wallet (across all agents; subgraph required)
given = sdk.searchFeedback(
    reviewers=["0x742d35cc6634c0532925a3b844bc9e7595f0beb7"]
)

# NEW: search feedback across multiple agents
multi = sdk.searchFeedback(
    agents=["11155111:123", "11155111:456", "11155111:789"]
)
```

### Safety: empty searches are rejected

Because `agentId` is now optional, `sdk.searchFeedback()` with no filters would otherwise be possible. In 1.4.0 the SDK raises if you provide **no filters**, to avoid accidentally querying arbitrary global feedback.


## TypeScript SDK note: fixed gas limit for `giveFeedback`

The TypeScript SDK sets a fixed gas limit of **300,000** for `giveFeedback` transactions to bypass unreliable `eth_estimateGas` behavior (notably for calls with multiple dynamic `string` parameters) and avoid failures before the wallet confirmation prompt.





