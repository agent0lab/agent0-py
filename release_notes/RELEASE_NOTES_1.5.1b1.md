# Release Notes — 1.5.1b1 (pre-release)

This is a **pre-release patch** on top of `1.5.0b1`. It focuses on improving defaults and simplifying the public search API surface.

## Breaking / API Changes

- **Pagination removed from search APIs**
  - `SDK.searchAgents()` now returns a plain `List[AgentSummary]` (no `{ "items": ..., "nextCursor": ... }` wrapper).
  - `SearchOptions` no longer includes `pageSize` or `cursor`.
  - If you previously paginated manually, you can now just call `searchAgents()` and process the full result set.

## Changed

- **Semantic keyword search defaults**
  - When keyword search triggers the semantic prefilter, the SDK now applies sensible defaults when not provided:
    - `semanticMinScore`: `0.5`
    - `semanticTopK`: `5000` (sent as `limit` to the semantic endpoint)

- **Internal “fetch all” behavior**
  - Subgraph pagination (`first` / `skip`) is still used internally, but it is no longer exposed in the SDK’s public API.

## Docs & Tests

- Updated docs/examples to remove pagination parameters and to reflect list return types.
- Added/updated tests to verify internal batching and “fetch all” behavior.

