"""
Integration tests: SDK telemetry (Telemetry-Events-Specs-v2).

Set in .env: AGENT0_API_KEY, optionally AGENT0_TELEMETRY_ENDPOINT (defaults to prod).
Run: pytest tests/test_telemetry_sdk.py -v

Tests that require local Supabase (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) and
ingest-telemetry running (e.g. in agent0-dashboard: npx supabase functions serve):
  - test_search_agents_returns_and_emits_telemetry (DB check: search.query)
  - test_get_agent_returns_and_emits_telemetry (DB check: agent.fetched)
  - test_load_agent_returns_and_emits_telemetry (DB check: agent.loaded, only when agent URI is HTTP/IPFS)
  - test_search_feedback_emits_telemetry (DB check: feedback.searched)
  - test_get_reputation_summary_emits_telemetry (DB check: reputation.summary.fetched)
  - test_telemetry_events_written_to_database_spec_coverage
Apply seed-telemetry-test-user.sql so the test API key exists.

Spec coverage (read-only, no signer):
  search.query, agent.fetched, agent.loaded, feedback.searched, reputation.summary.fetched
Write/lifecycle events (agent.registered, feedback.given, etc.) require signer/agent and are not covered here.
"""

import time
from datetime import datetime, timezone, timedelta

import pytest

from tests.config import (
    CHAIN_ID,
    RPC_URL,
    SUBGRAPH_URL,
    AGENT_ID,
    AGENT0_API_KEY,
    AGENT0_TELEMETRY_ENDPOINT,
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    print_config,
)
from agent0_sdk.core.sdk import SDK
from agent0_sdk.core.models import SearchOptions

HAS_API_KEY = bool(AGENT0_API_KEY and AGENT0_API_KEY.strip())
HAS_SUPABASE = bool(
    SUPABASE_URL and SUPABASE_URL.strip()
    and SUPABASE_SERVICE_ROLE_KEY
    and SUPABASE_SERVICE_ROLE_KEY.strip()
)


def assert_event_in_db(event_type: str, since: str) -> None:
    """Assert at least one telemetry event of type exists in DB after since. Only runs when HAS_SUPABASE."""
    if not HAS_SUPABASE or not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    time.sleep(6)
    try:
        from supabase import create_client
    except ImportError:
        pytest.skip("supabase package required for DB assertions (pip install supabase)")
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    resp = (
        client.table("telemetry_events")
        .select("event_type")
        .gte("timestamp", since)
        .eq("event_type", event_type)
        .limit(1)
        .execute()
    )
    if resp.data is None or len(resp.data) == 0:
        raise AssertionError(
            f'No telemetry event "{event_type}" found. '
            "Ensure Supabase and ingest-telemetry are running (e.g. in agent0-dashboard: npx supabase functions serve)."
        )


@pytest.mark.skipif(not HAS_API_KEY, reason="AGENT0_API_KEY not set")
class TestSDKWithTelemetry:
    """SDK with api_key + telemetry_endpoint."""

    def setup_method(self):
        print_config()
        self.sdk = SDK(
            chainId=CHAIN_ID,
            rpcUrl=RPC_URL,
            subgraphUrl=SUBGRAPH_URL,
            api_key=AGENT0_API_KEY,
            telemetry_endpoint=AGENT0_TELEMETRY_ENDPOINT or None,
        )

    def test_search_agents_returns_and_emits_telemetry(self):
        since = datetime.now(timezone.utc).isoformat()
        result = self.sdk.searchAgents({}, SearchOptions(sort=["updatedAt:desc"]))
        assert isinstance(result, list)
        if result:
            assert hasattr(result[0], "chainId") or "chainId" in getattr(result[0], "__dict__", {})
            assert hasattr(result[0], "agentId") or "agentId" in getattr(result[0], "__dict__", {})
        assert_event_in_db("search.query", since)

    def test_get_agent_returns_and_emits_telemetry(self):
        since = datetime.now(timezone.utc).isoformat()
        try:
            agent = self.sdk.getAgent(AGENT_ID)
            if agent:
                assert getattr(agent, "agentId", None) == AGENT_ID or agent.get("agentId") == AGENT_ID
        except Exception:
            pass  # getAgent may raise if not found
        assert_event_in_db("agent.fetched", since)

    def test_load_agent_returns_and_emits_telemetry(self):
        since = datetime.now(timezone.utc).isoformat()
        emitted = False
        try:
            agent = self.sdk.loadAgent(AGENT_ID)
            assert agent is not None
            assert getattr(agent, "agentId", None) == AGENT_ID
            emitted = True
        except Exception as e:
            msg = str(e)
            if "Unsupported URI scheme" in msg or "Data URI" in msg or "Invalid base64 payload in data URI" in msg:
                return  # Test agent may use data: URI (or malformed); skip DB assertion
            raise
        if emitted:
            assert_event_in_db("agent.loaded", since)

    def test_search_feedback_emits_telemetry(self):
        since = datetime.now(timezone.utc).isoformat()
        result = self.sdk.searchFeedback(agentId=AGENT_ID)
        assert isinstance(result, list)
        assert_event_in_db("feedback.searched", since)

    def test_get_reputation_summary_emits_telemetry(self):
        since = datetime.now(timezone.utc).isoformat()
        summary = self.sdk.getReputationSummary(AGENT_ID)
        assert summary is not None
        assert "count" in summary
        assert "averageValue" in summary
        assert_event_in_db("reputation.summary.fetched", since)

    @pytest.mark.skipif(not HAS_SUPABASE, reason="SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    def test_telemetry_events_written_to_database_spec_coverage(self):
        since_iso = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        self.sdk.searchAgents({}, SearchOptions(sort=["updatedAt:desc"]))
        self.sdk.getAgent(AGENT_ID)
        load_agent_emitted = False
        try:
            self.sdk.loadAgent(AGENT_ID)
            load_agent_emitted = True
        except Exception as e:
            msg = str(e)
            if "Unsupported URI scheme" not in msg and "Data URI" not in msg and "Invalid base64 payload in data URI" not in msg:
                raise
        self.sdk.searchFeedback(agentId=AGENT_ID)
        self.sdk.getReputationSummary(AGENT_ID)
        time.sleep(6)

        expected_types = [
            "search.query",
            "agent.fetched",
            "feedback.searched",
            "reputation.summary.fetched",
        ]
        if load_agent_emitted:
            expected_types.append("agent.loaded")

        try:
            from supabase import create_client
        except ImportError:
            pytest.skip("supabase package required for DB assertions")
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        resp = (
            client.table("telemetry_events")
            .select("event_type, payload, timestamp")
            .gte("timestamp", since_iso)
            .in_("event_type", expected_types)
            .order("timestamp", desc=True)
            .execute()
        )
        assert resp.data is not None
        if len(resp.data) == 0:
            raise AssertionError(
                "No telemetry events found. Ensure Edge Functions are served "
                "(e.g. in agent0-dashboard run: npx supabase functions serve) and "
                "ingest-telemetry is reachable at AGENT0_TELEMETRY_ENDPOINT."
            )
        types = [r["event_type"] for r in resp.data]
        for t in expected_types:
            assert t in types, f"Expected event type {t} in {types}"

        search_evt = next((e for e in resp.data if e.get("event_type") == "search.query"), None)
        if search_evt and search_evt.get("payload") and isinstance(search_evt["payload"], dict):
            assert "results" in search_evt["payload"]
            assert isinstance(search_evt["payload"]["results"], list)


class TestSDKWithoutApiKey:
    """SDK without api_key (no telemetry)."""

    def test_constructs_and_search_agents_works(self):
        sdk = SDK(
            chainId=CHAIN_ID,
            rpcUrl=RPC_URL,
            subgraphUrl=SUBGRAPH_URL,
        )
        result = sdk.searchAgents({}, SearchOptions(sort=["updatedAt:desc"]))
        assert isinstance(result, list)
