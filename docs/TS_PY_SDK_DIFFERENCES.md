# TypeScript vs Python SDK: Subgraph differences

Focus: **how each SDK talks to the subgraph** and **what currently causes errors in Python**.

---

## 1. What’s breaking in Python (subgraph-related)

The deployed subgraph schema does **not** expose `FeedbackFile.capability`, `FeedbackFile.name`, `FeedbackFile.skill`, `FeedbackFile.task`, or `FeedbackFile.context`. It uses the spec fields: `mcpTool`, `mcpPrompt`, `mcpResource`, `a2aSkills`, `a2aContextId`, `a2aTaskId`, `oasfSkills`, `oasfDomains`, etc.

| Issue | Where in Py | What happens |
|-------|-------------|--------------|
| **Invalid FeedbackFile selection** | `subgraph_client.py`: `get_feedback_by_id`, `search_feedback` | GraphQL selection includes `capability`, `name`, `skill`, `task`, `context` under `feedbackFile { … }`. The subgraph has no such fields → **GraphQL error** (e.g. “Type 'FeedbackFile' has no field 'capability'”). |
| **Invalid feedback filters** | `subgraph_client.py`: `search_feedback` | When the user passes capabilities/skills/tasks/names, Py builds `feedbackFile_: { capability_in: [...], skill_in: [...], task_in: [...], name_in: [...] }` in the `where` clause. The subgraph doesn’t support these filters → **GraphQL error** or invalid query. |
| **Reputation summary TypeError** | `feedback_manager.py`: `_get_reputation_summary_from_subgraph` | It calls `self.searchFeedback(agentId=..., first=1000, skip=0)`. `FeedbackManager.searchFeedback()` does **not** accept `first` or `skip` (only agentId, agents, tags, reviewers, etc.) → **TypeError: searchFeedback() got an unexpected keyword argument 'first'** (and `skip`). |

---

## 2. How TypeScript avoids those errors

| Area | TS behaviour |
|------|----------------|
| **FeedbackFile selection** | Only requests fields that exist: id, feedbackId, text, proofOfPayment*, tag1, tag2, createdAt. Does **not** request capability, name, skill, task, context. No GraphQL error. |
| **Feedback filters** | Does **not** push capability/skills/tasks/names into the `where` clause (comment in code: schema doesn’t expose them). Only pushes agent_in, clientAddress_in, tags, value_gte/value_lte, isRevoked. |
| **Reputation summary** | Calls the **subgraph client** directly: `searchFeedback({ agents: [id] }, 1000, 0, ...)`, not the feedback manager’s `searchFeedback`. So first/skip are valid. |

Trade-off: TS never gets capability/skill/task/name from the subgraph, so those fields stay **undefined** on Feedback when data comes from the subgraph. Py *expects* them from the query but the query fails.

---

## 3. Other subgraph differences

| Item | TS | Py |
|------|-----|-----|
| **Feedback root** | Does not select `feedbackIndex`. | Selects **feedbackIndex** on Feedback. |
| **Reputation summary path** | Subgraph client → `searchFeedback(params, first, skip)` → aggregate. | FeedbackManager → `searchFeedback(...)` (no first/skip) → **broken** when it passes first/skip. |
| **RegistrationFile** | Fragment may omit `createdAt`. | Fragment includes **createdAt**. |

Agent search, getAgent, and schema fallbacks (hasOASF, x402Support, endpoint, agentMetadatas) are aligned; the divergence is in **feedback** (FeedbackFile + filters) and **getReputationSummary**.

---

## 4. Fixing Python (summary)

To align Py with the subgraph and remove the errors:

1. **FeedbackFile**: Stop selecting capability, name, skill, task, context. Select only fields that exist (e.g. mcpTool, mcpPrompt, mcpResource, a2aSkills, a2aContextId, a2aTaskId, oasfSkills, oasfDomains, plus id, feedbackId, text, proofOfPayment*, tag1, tag2, createdAt). Optionally map those into legacy capability/skill/task/context in the SDK.
2. **Filters**: Stop adding `feedbackFile_: { capability_in, skill_in, task_in, name_in }` to the where clause.
3. **getReputationSummary**: Do not call `self.searchFeedback(..., first=1000, skip=0)`. Either call the subgraph client’s `search_feedback(params, first, skip)` in a loop, or add first/skip to `FeedbackManager.searchFeedback` and pass them through to the subgraph client.
