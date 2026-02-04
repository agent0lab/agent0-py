"""
Unit tests for SemanticSearchClient (no network).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent0_sdk.core.semantic_search_client import SemanticSearchClient


def _mock_response(json_data):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = json_data
    return resp


def test_semantic_search_client_default_timeout_is_20s():
    client = SemanticSearchClient()
    assert client.timeout_seconds == 20.0


def test_semantic_search_client_uses_limit_not_topk_in_request_body():
    client = SemanticSearchClient(base_url="https://semantic-search.ag0.xyz", timeout_seconds=12.34)

    with patch("agent0_sdk.core.semantic_search_client.requests.post") as post:
        post.return_value = _mock_response({"results": []})
        client.search("hello", min_score=0.5, top_k=123)

        assert post.call_count == 1
        _, kwargs = post.call_args
        assert kwargs["timeout"] == 12.34
        assert kwargs["json"]["query"] == "hello"
        assert kwargs["json"]["minScore"] == 0.5
        assert kwargs["json"]["limit"] == 123
        assert "topK" not in kwargs["json"]


def test_semantic_search_client_defaults_min_score_and_limit():
    client = SemanticSearchClient(base_url="https://semantic-search.ag0.xyz", timeout_seconds=12.34)

    with patch("agent0_sdk.core.semantic_search_client.requests.post") as post:
        post.return_value = _mock_response({"results": []})
        client.search("hello")

        assert post.call_count == 1
        _, kwargs = post.call_args
        assert kwargs["json"]["query"] == "hello"
        assert kwargs["json"]["minScore"] == 0.5
        assert kwargs["json"]["limit"] == 5000
        assert "topK" not in kwargs["json"]


def test_semantic_search_client_blank_query_returns_empty_and_does_not_call_requests():
    client = SemanticSearchClient()

    with patch("agent0_sdk.core.semantic_search_client.requests.post") as post:
        assert client.search("   ") == []
        post.assert_not_called()


def test_semantic_search_client_parses_results_and_ignores_non_dict_items():
    client = SemanticSearchClient()

    with patch("agent0_sdk.core.semantic_search_client.requests.post") as post:
        post.return_value = _mock_response(
            [
                {"chainId": "11155111", "agentId": "11155111:46", "score": 0.9},
                "bad",
                None,
                {"chainId": 1, "agentId": "1:1", "score": "0.1"},
                {"chainId": 1, "agentId": "missing_colon", "score": 0.2},
            ]
        )

        results = client.search("agent")
        assert [r.agentId for r in results] == ["11155111:46", "1:1"]
