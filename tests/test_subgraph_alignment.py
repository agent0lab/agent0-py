"""
Tests for subgraph alignment: FeedbackFile spec fields only, no invalid filters,
getReputationSummary via subgraph client (no first/skip on searchFeedback).
Feedback model uses spec-aligned fields (mcpTool, a2aSkills, a2aTaskId, etc.); legacy fields removed.

See docs/TS_PY_SDK_DIFFERENCES.md for context.
"""

import os
import pytest
from unittest.mock import MagicMock

from agent0_sdk.core.feedback_manager import FeedbackManager
from agent0_sdk.core.web3_client import Web3Client

# Live subgraph: run when SUBGRAPH_URL is set (or RUN_LIVE_TESTS=1)
RUN_LIVE_SUBGRAPH = os.getenv("RUN_LIVE_TESTS", "0") == "1" or bool(os.getenv("SUBGRAPH_URL", "").strip())


@pytest.fixture
def mock_web3():
    w = MagicMock(spec=Web3Client)
    w.chain_id = 8453
    return w


@pytest.fixture
def feedback_manager_with_subgraph(mock_web3):
    """FeedbackManager with indexer + subgraph_client so getReputationSummary uses subgraph path."""
    mock_subgraph = MagicMock()
    mock_subgraph.search_feedback.return_value = []
    mock_indexer = MagicMock()
    mock_indexer._get_subgraph_client_for_chain = MagicMock(return_value=mock_subgraph)
    return FeedbackManager(
        web3_client=mock_web3,
        subgraph_client=mock_subgraph,
        indexer=mock_indexer,
    )


def test_get_reputation_summary_subgraph_path_returns_summary(feedback_manager_with_subgraph):
    """getReputationSummary (subgraph path) no longer raises TypeError; returns dict with agentId, count, averageValue."""
    result = feedback_manager_with_subgraph.getReputationSummary("8453:1", tag1=None, tag2=None)
    assert result["agentId"] == "8453:1"
    assert result["count"] == 0
    assert "averageValue" in result
    assert "filters" in result
    assert feedback_manager_with_subgraph.subgraph_client.search_feedback.called


def test_get_reputation_summary_subgraph_path_paginates(feedback_manager_with_subgraph):
    """When subgraph returns a full page, getReputationSummary calls search_feedback again with increased skip."""
    feedback_manager_with_subgraph.subgraph_client.search_feedback.side_effect = [
        [{"id": "8453:1:0xabc:0", "value": "80", "tag1": None, "tag2": None, "feedbackFile": {}, "responses": [], "isRevoked": False, "createdAt": 123, "feedbackURI": None}] * 1000,
        [],
    ]
    result = feedback_manager_with_subgraph.getReputationSummary("8453:1")
    assert result["count"] == 1000
    assert feedback_manager_with_subgraph.subgraph_client.search_feedback.call_count == 2
    first_call = feedback_manager_with_subgraph.subgraph_client.search_feedback.call_args_list[0]
    second_call = feedback_manager_with_subgraph.subgraph_client.search_feedback.call_args_list[1]
    assert first_call[1]["skip"] == 0
    assert second_call[1]["skip"] == 1000


def test_subgraph_row_to_feedback_spec_fields(mock_web3):
    """From subgraph, Feedback is built with spec-aligned FeedbackFile fields (mcpTool, a2aSkills, etc.)."""
    mock_sub = MagicMock()
    manager = FeedbackManager(web3_client=mock_web3, subgraph_client=mock_sub)
    fb_data = {
        "id": "8453:99:0x1234567890123456789012345678901234567890:1",
        "value": "75",
        "tag1": "tag1",
        "tag2": None,
        "feedbackURI": None,
        "endpoint": None,
        "isRevoked": False,
        "createdAt": 1000,
        "feedbackFile": {
            "mcpTool": "tools",
            "mcpPrompt": None,
            "mcpResource": None,
            "a2aSkills": ["skill-a"],
            "a2aContextId": "ctx-1",
            "a2aTaskId": "task-1",
            "oasfSkills": ["oasf-skill"],
            "oasfDomains": ["domain-a"],
            "text": "Great",
        },
        "responses": [],
    }
    feedback = manager._subgraph_row_to_feedback(fb_data)
    assert feedback.mcpTool == "tools"
    assert feedback.a2aSkills == ["skill-a"]
    assert feedback.a2aContextId == "ctx-1"
    assert feedback.a2aTaskId == "task-1"
    assert feedback.oasfSkills == ["oasf-skill"]
    assert feedback.oasfDomains == ["domain-a"]
    assert feedback.value == 75.0
    assert feedback.agentId == "8453:99"
    assert feedback.reviewer == "0x1234567890123456789012345678901234567890"
    assert feedback.tags == ["tag1"]
    assert feedback.text == "Great"


# --- Live subgraph tests (parity with TS: same SUBGRAPH_URL default in config, same Feedback spec fields) ---
# Run with: RUN_LIVE_TESTS=1 pytest tests/test_subgraph_alignment.py -v
# Both Py and TS use spec-aligned Feedback (mcpTool, a2aSkills, ...); no legacy capability/skill/task/context.
SPEC_FIELDS = {"mcpTool", "mcpPrompt", "mcpResource", "a2aSkills", "a2aContextId", "a2aTaskId", "oasfSkills", "oasfDomains"}


@pytest.mark.skipif(not RUN_LIVE_SUBGRAPH, reason="RUN_LIVE_TESTS=1 or SUBGRAPH_URL required for live subgraph")
def test_live_subgraph_search_feedback_returns_spec_aligned_feedback():
    """Against live subgraph: searchFeedback succeeds and returned Feedback has spec fields (no GraphQL errors)."""
    from agent0_sdk import SDK
    from tests.config import CHAIN_ID, RPC_URL, SUBGRAPH_URL, AGENT_ID

    sdk = SDK(
        chainId=CHAIN_ID,
        rpcUrl=RPC_URL,
        subgraphOverrides={CHAIN_ID: SUBGRAPH_URL},
    )
    assert sdk.subgraph_client is not None
    feedbacks = sdk.searchFeedback(agentId=AGENT_ID)
    assert isinstance(feedbacks, list)
    for fb in feedbacks:
        # Feedback model has spec-aligned fields (mcpTool, a2aSkills, etc.); legacy fields removed
        for attr in SPEC_FIELDS:
            assert hasattr(fb, attr), f"Feedback missing spec field {attr}"


@pytest.mark.skipif(not RUN_LIVE_SUBGRAPH, reason="RUN_LIVE_TESTS=1 or SUBGRAPH_URL required for live subgraph")
def test_live_subgraph_get_reputation_summary_succeeds():
    """Against live subgraph: getReputationSummary succeeds (no TypeError from first/skip)."""
    from agent0_sdk import SDK
    from tests.config import CHAIN_ID, RPC_URL, SUBGRAPH_URL, AGENT_ID

    sdk = SDK(
        chainId=CHAIN_ID,
        rpcUrl=RPC_URL,
        subgraphOverrides={CHAIN_ID: SUBGRAPH_URL},
    )
    result = sdk.getReputationSummary(AGENT_ID)
    assert isinstance(result, dict)
    assert result.get("agentId") == AGENT_ID
    assert "count" in result
    assert "averageValue" in result
