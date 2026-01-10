# Release Notes — v1.0.0

This release is a **major refactor** of the Python SDK to align with the **ERC-8004 Jan 2026 spec update** and the latest deployed contracts/subgraph behavior.

## Highlights

### ERC-8004 Jan 2026 compatibility
- **Identity Registry**
  - `tokenURI` → **`agentURI`**
  - `setTokenURI` → **`setAgentURI`**
  - Added parsing/support for `URIUpdated`
- **Reputation Registry**
  - **Removed `feedbackAuth`** from the feedback flow
  - Feedback tags moved from bytes32 → **string** (`tag1`, `tag2`)
  - Added **`endpoint`** field to feedback
- **Validation Registry**
  - Tags moved from bytes32 → **string** where applicable

### Agent wallet is now verified on-chain (`agentWallet`)
The `agentWallet` attribute is now treated as a **verified on-chain attribute** and is no longer handled as “just metadata”.

Key behavior:
- On mint/registration, `agentWallet` defaults to the **owner address**
- On transfer, `agentWallet` is reset to the **zero address**
- Updating it requires proof of control of the **new wallet** via **EIP-712 (EOA)** or **ERC-1271 (contract wallet)**.

## Breaking changes

### `Agent.setAgentWallet(...)` is now on-chain only
- Calling `setAgentWallet` **before registration** now raises an error.
- The SDK builds the correct typed data internally; for EOAs you can provide:
  - `new_wallet_signer` (private key string / eth-account account) to auto-sign
  - or omit it if the SDK signer address equals the new wallet address
- For contract wallets (ERC-1271), provide `signature` bytes (the SDK cannot generate that signature without the wallet’s signing mechanism).

### `SDK.giveFeedback(...)`
- Removed the deprecated `feedbackAuth` plumbing; feedback submission is permissionless per the updated spec.

## Subgraph compatibility improvements
Hosted subgraphs are not always upgraded in lockstep. The SDK now includes lightweight GraphQL compatibility fallbacks for:
- `responseURI` vs `responseUri`
- missing `AgentRegistrationFile.agentWallet` / `agentWalletChainId` fields

## Tests & scripts updated
- Integration scripts updated to the new `setAgentWallet` semantics and simplified signing flows.
- Search/feedback paths updated to tolerate real-world subgraph schema differences.

