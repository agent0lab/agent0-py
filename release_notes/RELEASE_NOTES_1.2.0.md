# Release Notes — 1.2.0

## Breaking changes

### Reputation: `score` → `value`

The ReputationRegistry model migrated from `score (0–100)` to a decimal **`value`** stored on-chain as `(int256 value, uint8 valueDecimals)`.

This Python SDK release introduces a **hard break**:

- `giveFeedback(agentId, score, ...)` → `giveFeedback(agentId, value, ...)`
  - `value` accepts `int | float | str`
  - `str` is recommended for exact decimal inputs
  - `float` inputs are supported and **rounded** to fit up to 18 decimals
- Feedback search:
  - `minScore/maxScore` → `minValue/maxValue`
- Reputation search:
  - `minAverageScore` → `minAverageValue`
- Feedback model:
  - `Feedback.score` → `Feedback.value`
- Reputation summary:
  - `{ count, averageScore }` → `{ count, averageValue }`

### Subgraph schema alignment

This SDK version expects the updated subgraph schema:

- `Feedback.value`
- `AgentStats.averageFeedbackValue`






